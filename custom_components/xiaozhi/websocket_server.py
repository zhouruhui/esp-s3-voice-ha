"""WebSocket server for XiaoZhi ESP32 integration."""
import asyncio
import json
import logging
from typing import Any, Dict, Optional, Set
import uuid

import aiohttp
from aiohttp import web, WSMsgType
from homeassistant.components import assist_pipeline
from homeassistant.components.assist_pipeline import Pipeline, PipelineEvent, PipelineEventType
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)

MSG_TYPE_CONNECT = "connect"
MSG_TYPE_DISCONNECT = "disconnect"
MSG_TYPE_PING = "ping"
MSG_TYPE_PONG = "pong"
MSG_TYPE_COMMAND = "command"
MSG_TYPE_TEXT = "text"
MSG_TYPE_AUDIO = "audio"
MSG_TYPE_ERROR = "error"
MSG_TYPE_SPEECH_START = "speech_start"
MSG_TYPE_SPEECH_END = "speech_end"
MSG_TYPE_INTENT = "intent"
MSG_TYPE_TTS = "tts"


class XiaozhiWebSocket:
    """WebSocket server for XiaoZhi ESP32 devices."""

    def __init__(
        self,
        hass: HomeAssistant,
        port: int,
        websocket_path: str,
        pipeline_id: str,
        forward_url: Optional[str] = None
    ) -> None:
        """Initialize the WebSocket server."""
        self.hass = hass
        self.port = port
        self.websocket_path = websocket_path if websocket_path.startswith("/") else f"/{websocket_path}"
        self.pipeline_id = pipeline_id
        self.forward_url = forward_url
        self.runner = None
        self.site = None
        self.app = web.Application()
        self.connections: Dict[str, Dict[str, Any]] = {}
        self.devices: Dict[str, Dict[str, Any]] = {}
        self.loop = asyncio.get_event_loop()
        self.active_pipelines: Dict[str, Dict[str, Any]] = {}
        self.session = async_get_clientsession(hass)
        # 用于外部注册回调
        self.device_connected_callback = None

    async def start(self) -> None:
        """Start the WebSocket server."""
        try:
            self.app.router.add_route("GET", self.websocket_path, self.websocket_handler)
            
            # 设置runner和site
            self.runner = web.AppRunner(self.app)
            await self.runner.setup()
            self.site = web.TCPSite(self.runner, "0.0.0.0", self.port)
            
            try:
                await self.site.start()
                _LOGGER.info("XiaoZhi WebSocket server started on port %s", self.port)
            except OSError as err:
                _LOGGER.error("无法启动WebSocket服务器: %s", err)
                self.runner = None
                if "address already in use" in str(err).lower():
                    _LOGGER.error("端口 %s 已被占用，请选择其他端口", self.port)
                raise
        except Exception as exc:
            _LOGGER.error("启动WebSocket服务器时发生未知错误: %s", exc)
            raise

    async def stop(self) -> None:
        """Stop the WebSocket server."""
        try:
            if self.site:
                await self.site.stop()
                self.site = None
            
            if self.runner:
                await self.runner.cleanup()
                self.runner = None
            
            # 关闭所有连接
            for conn_id, conn_data in list(self.connections.items()):
                ws = conn_data.get("websocket")
                if ws and not ws.closed:
                    await ws.close()
            
            self.connections = {}
            self.devices = {}
            
            _LOGGER.info("XiaoZhi WebSocket服务器已停止")
        except Exception as exc:
            _LOGGER.error("停止WebSocket服务器时出错: %s", exc)

    async def websocket_handler(self, request: web.Request) -> web.WebSocketResponse:
        """Handle WebSocket connections."""
        try:
            ws = web.WebSocketResponse()
            await ws.prepare(request)
            
            conn_id = str(uuid.uuid4())
            remote_ip = request.remote
            
            self.connections[conn_id] = {
                "websocket": ws,
                "remote_ip": remote_ip,
                "device_id": None,
                "last_activity": self.hass.loop.time(),
            }
            
            _LOGGER.info("新WebSocket连接: %s (IP: %s)", conn_id, remote_ip)
            
            try:
                async for msg in ws:
                    if msg.type == WSMsgType.TEXT:
                        await self._handle_text_message(conn_id, msg.data)
                    elif msg.type == WSMsgType.BINARY:
                        await self._handle_binary_message(conn_id, msg.data)
                    elif msg.type == WSMsgType.ERROR:
                        _LOGGER.error("WebSocket连接错误: %s", ws.exception())
                        break
            except asyncio.CancelledError:
                _LOGGER.info("WebSocket连接被取消: %s", conn_id)
            except Exception as exc:
                _LOGGER.error("处理WebSocket消息时出错: %s", exc)
            finally:
                if conn_id in self.connections:
                    try:
                        device_id = self.connections[conn_id].get("device_id")
                        if device_id and device_id in self.devices:
                            self.devices[device_id]["connected"] = False
                            # 通知设备状态变化
                            self.hass.bus.async_fire(
                                "xiaozhi_device_state_changed",
                                {"device_id": device_id, "state": "disconnected"}
                            )
                        del self.connections[conn_id]
                        
                        _LOGGER.info("WebSocket连接已关闭: %s", conn_id)
                    except Exception as exc:
                        _LOGGER.error("清理连接时出错: %s", exc)
            
            return ws
        except Exception as exc:
            _LOGGER.error("WebSocket处理程序出错: %s", exc)
            raise web.HTTPInternalServerError()

    async def _handle_text_message(self, conn_id: str, message: str) -> None:
        """Handle text messages from the client."""
        if conn_id not in self.connections:
            _LOGGER.warning("收到来自未知连接的消息: %s", conn_id)
            return
        
        try:
            data = json.loads(message)
            msg_type = data.get("type")
            
            if not msg_type:
                _LOGGER.warning("收到无类型的消息: %s", message)
                return
            
            # 更新最后活动时间
            self.connections[conn_id]["last_activity"] = self.hass.loop.time()
            
            if msg_type == MSG_TYPE_CONNECT:
                await self._handle_connect(conn_id, data)
            elif msg_type == MSG_TYPE_PING:
                await self._send_text_response(conn_id, {"type": MSG_TYPE_PONG})
            elif msg_type == MSG_TYPE_TEXT:
                await self._handle_text_command(conn_id, data)
            elif msg_type == MSG_TYPE_COMMAND:
                await self._handle_command(conn_id, data)
            elif msg_type == MSG_TYPE_SPEECH_END:
                await self._handle_speech_end(conn_id, data)
            else:
                _LOGGER.warning("未知消息类型: %s", msg_type)
                
                # 如果设置了转发URL，转发消息
                if self.forward_url:
                    await self._forward_message(conn_id, data)
                
        except json.JSONDecodeError:
            _LOGGER.warning("无效的JSON消息: %s", message)
        except Exception as e:
            _LOGGER.error("处理文本消息时出错: %s", e)
    
    async def _handle_binary_message(self, conn_id: str, data: bytes) -> None:
        """Handle binary messages (audio data) from the client."""
        if conn_id not in self.connections:
            _LOGGER.warning("收到来自未知连接的音频数据: %s", conn_id)
            return
        
        try:
            device_id = self.connections[conn_id].get("device_id")
            if not device_id:
                _LOGGER.warning("收到未注册设备的音频数据")
                return
            
            # 更新最后活动时间
            self.connections[conn_id]["last_activity"] = self.hass.loop.time()
            
            # 检查是否有活动的语音管道
            if conn_id not in self.active_pipelines:
                # 创建新的语音识别管道
                try:
                    pipeline_id = self.pipeline_id
                    pipeline = await assist_pipeline.async_get_pipeline(self.hass, pipeline_id)
                    
                    if not pipeline:
                        _LOGGER.error("无法获取语音助手Pipeline: %s", pipeline_id)
                        await self._send_text_response(conn_id, {
                            "type": MSG_TYPE_ERROR, 
                            "error": "找不到语音助手Pipeline"
                        })
                        return
                    
                    conversation_id = f"xiaozhi_{device_id}_{uuid.uuid4().hex[:8]}"
                    
                    pipeline_events = []
                    audio_buffer = bytearray()
                    
                    self.active_pipelines[conn_id] = {
                        "pipeline": pipeline,
                        "conversation_id": conversation_id,
                        "events": pipeline_events,
                        "audio_buffer": audio_buffer,
                        "stt_done": False,
                        "intent_done": False,
                    }
                    
                    # 开始执行语音助手Pipeline
                    pipeline_runner = await pipeline.async_run(
                        conversation_id=conversation_id,
                        device_id=device_id,
                        start_stage="stt",
                        end_stage="tts",
                        event_callback=lambda event: self._pipeline_event_callback(conn_id, event),
                    )
                    
                    self.active_pipelines[conn_id]["runner"] = pipeline_runner
                    
                    # 通知客户端语音识别开始
                    await self._send_text_response(conn_id, {"type": MSG_TYPE_SPEECH_START})
                except Exception as exc:
                    _LOGGER.error("初始化Pipeline时出错: %s", exc)
                    await self._send_text_response(conn_id, {
                        "type": MSG_TYPE_ERROR, 
                        "error": f"初始化Pipeline失败: {exc}"
                    })
                    return
            
            # 将音频数据添加到活动的管道
            if self.active_pipelines[conn_id].get("runner"):
                try:
                    runner = self.active_pipelines[conn_id]["runner"]
                    await runner.stt_stream.async_put_audio_stream(data)
                    
                    # 如果设置了转发URL，转发音频数据
                    if self.forward_url:
                        await self._forward_audio(conn_id, data)
                except Exception as exc:
                    _LOGGER.error("处理音频数据时出错: %s", exc)
                    # 清理管道资源
                    self._cleanup_pipeline(conn_id)
        except Exception as exc:
            _LOGGER.error("处理二进制消息时出错: %s", exc)

    async def _handle_connect(self, conn_id: str, data: Dict[str, Any]) -> None:
        """Handle device connection."""
        try:
            device_id = data.get("device_id")
            if not device_id:
                await self._send_text_response(conn_id, {
                    "type": MSG_TYPE_ERROR, 
                    "error": "缺少device_id"
                })
                return
            
            # 更新连接信息
            self.connections[conn_id]["device_id"] = device_id
            
            # 更新设备状态
            self.devices[device_id] = {
                "conn_id": conn_id,
                "connected": True,
                "last_seen": self.hass.loop.time(),
            }
            
            # 通知设备状态变化
            self.hass.bus.async_fire(
                "xiaozhi_device_state_changed",
                {"device_id": device_id, "state": "connected"}
            )
            
            await self._send_text_response(conn_id, {
                "type": MSG_TYPE_CONNECT,
                "status": "connected",
                "server_id": "home_assistant"
            })
            
            _LOGGER.info("设备已连接: %s (连接ID: %s)", device_id, conn_id)
            
            # 调用连接回调
            if self.device_connected_callback:
                try:
                    self.device_connected_callback(device_id)
                except Exception as exc:
                    _LOGGER.error("设备连接回调出错: %s", exc)
        except Exception as exc:
            _LOGGER.error("处理连接请求时出错: %s", exc)

    async def _handle_text_command(self, conn_id: str, data: Dict[str, Any]) -> None:
        """Handle text command from device."""
        try:
            device_id = self.connections[conn_id].get("device_id")
            if not device_id:
                _LOGGER.warning("收到未注册设备的文本命令")
                return
            
            text = data.get("text", "")
            if not text:
                return
            
            _LOGGER.debug("收到文本命令: %s", text)
            
            # 使用对话Pipeline处理文本命令
            try:
                pipeline_id = self.pipeline_id
                pipeline = await assist_pipeline.async_get_pipeline(self.hass, pipeline_id)
                
                if not pipeline:
                    _LOGGER.error("无法获取语音助手Pipeline: %s", pipeline_id)
                    await self._send_text_response(conn_id, {
                        "type": MSG_TYPE_ERROR, 
                        "error": "找不到语音助手Pipeline"
                    })
                    return
                
                conversation_id = f"xiaozhi_text_{device_id}_{uuid.uuid4().hex[:8]}"
                
                # 直接从文本开始处理
                result = await pipeline.async_run(
                    text=text,
                    conversation_id=conversation_id,
                    device_id=device_id,
                    start_stage="intent",
                    end_stage="tts",
                )
                
                # 处理结果
                if result:
                    if result.intent_response:
                        await self._send_text_response(conn_id, {
                            "type": MSG_TYPE_INTENT,
                            "intent": result.intent_response.response.speech.plain.text,
                        })
                    
                    if result.tts_output and result.tts_output.get("audio"):
                        # 发送TTS音频数据
                        ws = self.connections[conn_id].get("websocket")
                        if ws and not ws.closed:
                            await ws.send_bytes(result.tts_output["audio"])
            except Exception as exc:
                _LOGGER.error("处理文本命令时出错: %s", exc)
                await self._send_text_response(conn_id, {
                    "type": MSG_TYPE_ERROR, 
                    "error": f"处理文本命令失败: {exc}"
                })
        except Exception as exc:
            _LOGGER.error("处理文本命令时出错: %s", exc)

    async def _handle_command(self, conn_id: str, data: Dict[str, Any]) -> None:
        """Handle command from device."""
        try:
            device_id = self.connections[conn_id].get("device_id")
            if not device_id:
                _LOGGER.warning("收到未注册设备的命令")
                return
            
            command = data.get("command")
            if not command:
                return
            
            # 处理特定命令
            if command == "stop_listening":
                # 停止当前活动的语音管道
                if conn_id in self.active_pipelines:
                    try:
                        runner = self.active_pipelines[conn_id].get("runner")
                        if runner:
                            await runner.stop()
                        del self.active_pipelines[conn_id]
                    except Exception as exc:
                        _LOGGER.error("停止监听时出错: %s", exc)
                
                await self._send_text_response(conn_id, {
                    "type": MSG_TYPE_COMMAND,
                    "command": "stop_listening",
                    "status": "ok"
                })
            elif command == "get_status":
                # 发送状态信息
                await self._send_text_response(conn_id, {
                    "type": MSG_TYPE_COMMAND,
                    "command": "status",
                    "status": "ok",
                    "server_id": "home_assistant",
                    "device_id": device_id
                })
            else:
                # 如果设置了转发URL，转发命令
                if self.forward_url:
                    await self._forward_message(conn_id, data)
                else:
                    _LOGGER.warning("未知命令: %s", command)
        except Exception as exc:
            _LOGGER.error("处理命令时出错: %s", exc)

    async def _handle_speech_end(self, conn_id: str, data: Dict[str, Any]) -> None:
        """Handle speech end notification."""
        try:
            if conn_id not in self.active_pipelines:
                return
            
            # 通知语音管道音频流结束
            runner = self.active_pipelines[conn_id].get("runner")
            if runner:
                try:
                    await runner.stt_stream.async_end_stream()
                    self.active_pipelines[conn_id]["stt_done"] = True
                except Exception as exc:
                    _LOGGER.error("结束语音流时出错: %s", exc)
                    # 强制清理管道
                    self._cleanup_pipeline(conn_id)
        except Exception as exc:
            _LOGGER.error("处理语音结束通知时出错: %s", exc)

    async def _pipeline_event_callback(self, conn_id: str, event: PipelineEvent) -> None:
        """Handle events from the pipeline."""
        try:
            if conn_id not in self.active_pipelines:
                return
            
            # 存储事件
            self.active_pipelines[conn_id]["events"].append(event)
            
            if event.type == PipelineEventType.STT_END:
                self.active_pipelines[conn_id]["stt_done"] = True
                text = event.data.get("stt_output", {}).get("text")
                
                if text:
                    await self._send_text_response(conn_id, {
                        "type": MSG_TYPE_TEXT,
                        "text": text,
                    })
            
            elif event.type == PipelineEventType.INTENT_END:
                self.active_pipelines[conn_id]["intent_done"] = True
                intent_response = event.data.get("intent_response")
                
                if intent_response and hasattr(intent_response, "response") and hasattr(intent_response.response, "speech"):
                    speech_text = intent_response.response.speech.plain.text
                    await self._send_text_response(conn_id, {
                        "type": MSG_TYPE_INTENT,
                        "intent": speech_text,
                    })
            
            elif event.type == PipelineEventType.TTS_END:
                # TTS处理完成
                tts_output = event.data.get("tts_output")
                if tts_output and tts_output.get("audio"):
                    # 发送TTS音频数据
                    ws = self.connections[conn_id].get("websocket")
                    if ws and not ws.closed:
                        await ws.send_bytes(tts_output["audio"])
                
                # 清理管道资源
                self._cleanup_pipeline(conn_id)
            
            elif event.type == PipelineEventType.RUN_END:
                # 清理管道资源
                self._cleanup_pipeline(conn_id)
            
            elif event.type == PipelineEventType.ERROR:
                # 发生错误
                error_info = event.data.get("error", "未知错误")
                _LOGGER.error("Pipeline执行错误: %s", error_info)
                await self._send_text_response(conn_id, {
                    "type": MSG_TYPE_ERROR,
                    "error": f"Pipeline错误: {error_info}"
                })
                # 清理管道资源
                self._cleanup_pipeline(conn_id)
        except Exception as exc:
            _LOGGER.error("Pipeline事件回调处理时出错: %s", exc)
            # 清理资源，防止资源泄漏
            self._cleanup_pipeline(conn_id)

    def _cleanup_pipeline(self, conn_id: str) -> None:
        """Clean up pipeline resources."""
        try:
            if conn_id in self.active_pipelines:
                runner = self.active_pipelines[conn_id].get("runner")
                if runner:
                    asyncio.create_task(runner.stop())
                del self.active_pipelines[conn_id]
        except Exception as exc:
            _LOGGER.error("清理Pipeline资源时出错: %s", exc)

    async def _send_text_response(self, conn_id: str, response: Dict[str, Any]) -> None:
        """Send text response to the client."""
        try:
            if conn_id not in self.connections:
                return
            
            ws = self.connections[conn_id].get("websocket")
            if ws and not ws.closed:
                try:
                    await ws.send_str(json.dumps(response))
                except Exception as e:
                    _LOGGER.error("发送响应时出错: %s", e)
        except Exception as exc:
            _LOGGER.error("发送文本响应时出错: %s", exc)

    async def send_tts_message(self, device_id: str, message: str) -> None:
        """Send TTS message to a device."""
        try:
            # 查找设备连接
            conn_id = None
            for device_id_key, device_data in self.devices.items():
                if device_id_key == device_id and device_data.get("connected"):
                    conn_id = device_data.get("conn_id")
                    break
            
            if not conn_id:
                _LOGGER.warning("找不到连接的设备: %s", device_id)
                return
            
            # 使用Pipeline生成TTS
            try:
                pipeline_id = self.pipeline_id
                pipeline = await assist_pipeline.async_get_pipeline(self.hass, pipeline_id)
                
                if not pipeline:
                    _LOGGER.error("无法获取语音助手Pipeline: %s", pipeline_id)
                    return
                
                # 直接执行TTS
                result = await pipeline.async_run(
                    text=message,
                    conversation_id=f"xiaozhi_tts_{device_id}_{uuid.uuid4().hex[:8]}",
                    device_id=device_id,
                    start_stage="tts",
                    end_stage="tts",
                )
                
                if result and result.tts_output and result.tts_output.get("audio"):
                    # 发送TTS音频数据
                    ws = self.connections[conn_id].get("websocket")
                    if ws and not ws.closed:
                        # 首先发送TTS开始通知
                        await self._send_text_response(conn_id, {
                            "type": MSG_TYPE_TTS, 
                            "status": "start"
                        })
                        
                        # 发送音频数据
                        await ws.send_bytes(result.tts_output["audio"])
                        
                        # 发送TTS结束通知
                        await self._send_text_response(conn_id, {
                            "type": MSG_TYPE_TTS, 
                            "status": "end"
                        })
                    else:
                        _LOGGER.warning("设备WebSocket连接已关闭")
                else:
                    _LOGGER.error("生成TTS音频失败")
            except Exception as exc:
                _LOGGER.error("处理TTS请求时出错: %s", exc)
        except Exception as exc:
            _LOGGER.error("发送TTS消息时出错: %s", exc)

    async def _forward_message(self, conn_id: str, data: Dict[str, Any]) -> None:
        """Forward message to external service."""
        if not self.forward_url:
            return
        
        try:
            async with self.session.post(
                self.forward_url, 
                json=data, 
                headers={"Content-Type": "application/json"}
            ) as resp:
                if resp.status != 200:
                    _LOGGER.warning("转发消息失败: %s", await resp.text())
                    return
                
                # 处理响应
                response_data = await resp.json()
                await self._send_text_response(conn_id, response_data)
        except Exception as e:
            _LOGGER.error("转发消息时出错: %s", e)

    async def _forward_audio(self, conn_id: str, audio_data: bytes) -> None:
        """Forward audio data to external service."""
        if not self.forward_url:
            return
        
        try:
            audio_forward_url = f"{self.forward_url}/audio"
            async with self.session.post(
                audio_forward_url, 
                data=audio_data, 
                headers={"Content-Type": "audio/raw"}
            ) as resp:
                if resp.status != 200:
                    _LOGGER.warning("转发音频失败: %s", await resp.text())
        except Exception as e:
            _LOGGER.error("转发音频时出错: %s", e) 