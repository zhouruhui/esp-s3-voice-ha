"""XiaoZhi ESP32 WebSocket服务。"""
import asyncio
import json
import logging
import aiohttp
from typing import Any, Dict, List, Optional, Set, Callable

import voluptuous as vol
import websockets
from websockets.exceptions import ConnectionClosed

from homeassistant.components import assist_pipeline
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    WS_MSG_TYPE_HELLO,
    WS_MSG_TYPE_RECOGNITION_RESULT,
    WS_MSG_TYPE_TTS_START,
    WS_MSG_TYPE_TTS_END,
    WS_MSG_TYPE_ERROR,
    ERR_INVALID_MESSAGE,
    ERR_SERVER_ERROR
)

_LOGGER = logging.getLogger(__name__)

class XiaozhiWebSocket:
    """WebSocket服务器组件，处理与ESP32设备的通信。"""

    def __init__(
        self,
        hass: HomeAssistant,
        port: int,
        websocket_path: str,
        pipeline_id: Optional[str] = None,
        forward_url: Optional[str] = None,
        proxy_mode: bool = False,
    ) -> None:
        """初始化WebSocket服务器。"""
        self.hass = hass
        self.port = port
        self.websocket_path = websocket_path
        self.pipeline_id = pipeline_id
        self.forward_url = forward_url
        self.proxy_mode = proxy_mode
        self.server = None
        self.connections: Dict[str, Any] = {}
        self.device_ids: Set[str] = set()
        
        # 回调函数
        self.on_device_connected: Optional[Callable[[str], None]] = None
        self.on_device_disconnected: Optional[Callable[[str], None]] = None

    async def start(self) -> None:
        """启动WebSocket服务器。"""
        try:
            self.server = await websockets.serve(
                self.handle_connection, "0.0.0.0", self.port, ping_interval=30
            )
            _LOGGER.info(
                "XiaoZhi WebSocket服务已启动, 监听 0.0.0.0:%s%s",
                self.port,
                self.websocket_path,
            )
        except Exception as exc:
            _LOGGER.error("启动WebSocket服务器时出错: %s", exc)
            raise

    async def stop(self) -> None:
        """停止WebSocket服务器。"""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            self.server = None
            _LOGGER.info("WebSocket服务器已停止")

    async def handle_connection(self, websocket, path) -> None:
        """处理新的WebSocket连接。"""
        device_id = None
        
        if path != self.websocket_path:
            _LOGGER.warning("收到无效路径的连接请求: %s", path)
            await websocket.close(1008, "无效的WebSocket路径")
            return

        try:
            # 等待初始连接消息，以获取设备ID
            initial_message = await websocket.recv()
            try:
                data = json.loads(initial_message)
                device_id = data.get("device_id")

                if not device_id:
                    _LOGGER.warning("收到没有设备ID的连接消息: %s", initial_message)
                    await websocket.close(1008, "缺少设备ID")
                    return

                _LOGGER.info("设备 %s 已连接", device_id)

                # 存储连接和设备信息
                self.connections[device_id] = websocket
                self.device_ids.add(device_id)

                # 通知连接成功
                response = {"type": "connection", "status": "connected"}
                await websocket.send(json.dumps(response))

                # 触发设备连接回调
                if self.on_device_connected:
                    self.on_device_connected(device_id)

                # 开始处理消息
                await self._handle_messages(device_id, websocket)
            except json.JSONDecodeError:
                _LOGGER.warning("收到无效的JSON消息: %s", initial_message)
                await websocket.close(1008, "无效的JSON格式")
            except Exception as exc:
                _LOGGER.error("处理连接消息时出错: %s", exc)
                await websocket.close(1011, "服务器内部错误")
        except ConnectionClosed:
            pass
        except Exception as exc:
            _LOGGER.error("处理WebSocket连接时出错: %s", exc)
        finally:
            await self._cleanup_connection(device_id)

    async def _cleanup_connection(self, device_id: Optional[str]) -> None:
        """清理断开的连接。"""
        if device_id:
            if device_id in self.connections:
                del self.connections[device_id]
            if device_id in self.device_ids:
                self.device_ids.remove(device_id)
            
            # 触发设备断开连接回调
            if self.on_device_disconnected:
                self.on_device_disconnected(device_id)
                
            _LOGGER.info("设备 %s 已断开连接", device_id)

    async def _handle_messages(self, device_id: str, websocket) -> None:
        """处理来自设备的WebSocket消息。"""
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    message_type = data.get("type", "unknown")

                    _LOGGER.debug("收到来自设备 %s 的消息: %s", device_id, message_type)

                    # 根据消息类型处理
                    if message_type == "voice":
                        await self._handle_voice_message(device_id, data, websocket)
                    elif message_type == "ping":
                        await websocket.send(json.dumps({"type": "pong"}))
                    else:
                        _LOGGER.warning("未知消息类型: %s", message_type)

                except json.JSONDecodeError:
                    _LOGGER.warning("收到无效的JSON消息: %s", message)
                except Exception as exc:
                    _LOGGER.error("处理消息时出错: %s", exc)
        except ConnectionClosed:
            _LOGGER.info("设备 %s 的连接已关闭", device_id)
        except Exception as exc:
            _LOGGER.error("_handle_messages 出错: %s", exc)

    async def _handle_voice_message(self, device_id: str, data: Dict, websocket) -> None:
        """处理语音消息。"""
        try:
            audio_format = data.get("format", "wav")
            audio_data = data.get("data")
            language = data.get("language", "zh-CN")
            
            if not audio_data:
                _LOGGER.warning("语音消息中没有音频数据")
                await websocket.send(json.dumps({
                    "type": WS_MSG_TYPE_ERROR,
                    "error": ERR_INVALID_MESSAGE,
                    "message": "缺少音频数据"
                }))
                return
                
            # 代理模式 - 转发到外部服务
            if self.proxy_mode and self.forward_url:
                await self._forward_voice_request(device_id, data, websocket)
                return
                
            # 本地处理模式 - 使用Home Assistant语音助手
            if not self.pipeline_id:
                _LOGGER.error("未配置语音助手Pipeline")
                await websocket.send(json.dumps({
                    "type": WS_MSG_TYPE_ERROR,
                    "error": "missing_pipeline",
                    "message": "未配置语音助手Pipeline"
                }))
                return
            
            _LOGGER.debug("正在处理来自设备 %s 的语音请求", device_id)
            
            try:
                # 使用语音助手处理语音请求
                pipeline_input = {
                    "audio": audio_data,
                    "language": language,
                }
                
                _LOGGER.debug("提交语音处理请求到Pipeline: %s", self.pipeline_id)
                
                # 提交请求到语音助手Pipeline
                result = await assist_pipeline.async_pipeline_from_audio(
                    self.hass,
                    bytes.fromhex(audio_data),
                    pipeline_id=self.pipeline_id,
                    language=language,
                )
                
                # 检查处理结果
                if not result or not result.response:
                    _LOGGER.warning("语音助手没有返回响应")
                    await websocket.send(json.dumps({
                        "type": WS_MSG_TYPE_ERROR,
                        "error": "no_response",
                        "message": "语音助手没有返回响应"
                    }))
                    return
                
                # 返回处理结果
                _LOGGER.debug("语音处理返回: %s", result.response)
                
                await websocket.send(json.dumps({
                    "type": WS_MSG_TYPE_RECOGNITION_RESULT,
                    "text": result.response,
                    "status": "success"
                }))
                
            except Exception as exc:
                _LOGGER.error("语音处理请求出错: %s", exc)
                await websocket.send(json.dumps({
                    "type": WS_MSG_TYPE_ERROR,
                    "error": "processing_error",
                    "message": f"语音处理错误: {str(exc)}"
                }))
        except Exception as exc:
            _LOGGER.error("处理语音消息时出错: %s", exc)
            
    async def _forward_voice_request(self, device_id: str, data: Dict, websocket) -> None:
        """转发语音请求到外部服务"""
        try:
            _LOGGER.debug("转发来自设备 %s 的语音请求到: %s", device_id, self.forward_url)
            
            # 创建会话
            session = async_get_clientsession(self.hass)
            
            # 准备请求数据
            request_data = {
                "type": "voice",
                "device_id": device_id,
                "data": data.get("data"),
                "format": data.get("format", "wav"),
                "language": data.get("language", "zh-CN")
            }
            
            # 发送请求到转发URL
            async with session.post(
                self.forward_url, 
                json=request_data,
                timeout=10
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    _LOGGER.error(
                        "转发请求失败，状态码: %s, 错误: %s", 
                        response.status, error_text
                    )
                    await websocket.send(json.dumps({
                        "type": WS_MSG_TYPE_ERROR,
                        "error": "forward_failed",
                        "message": f"转发请求失败: {response.status}"
                    }))
                    return
                    
                # 解析响应
                try:
                    response_data = await response.json()
                    _LOGGER.debug("转发服务返回: %s", response_data)
                    
                    # 转发响应回设备
                    await websocket.send(json.dumps({
                        "type": WS_MSG_TYPE_RECOGNITION_RESULT,
                        "text": response_data.get("text", ""),
                        "status": "success"
                    }))
                except Exception as exc:
                    _LOGGER.error("解析转发响应时出错: %s", exc)
                    await websocket.send(json.dumps({
                        "type": WS_MSG_TYPE_ERROR,
                        "error": "invalid_response",
                        "message": "无法解析服务器响应"
                    }))
        except asyncio.TimeoutError:
            _LOGGER.error("转发请求超时")
            await websocket.send(json.dumps({
                "type": WS_MSG_TYPE_ERROR,
                "error": "timeout",
                "message": "转发请求超时"
            }))
        except Exception as exc:
            _LOGGER.error("转发语音请求时出错: %s", exc)
            await websocket.send(json.dumps({
                "type": WS_MSG_TYPE_ERROR,
                "error": ERR_SERVER_ERROR,
                "message": f"转发请求错误: {str(exc)}"
            }))

    async def send_tts_message(self, device_id: str, message: str) -> None:
        """发送TTS消息到设备。"""
        try:
            if device_id not in self.connections:
                _LOGGER.warning("设备 %s 未连接，无法发送TTS消息", device_id)
                return

            websocket = self.connections[device_id]
            await websocket.send(
                json.dumps({"type": WS_MSG_TYPE_TTS_START, "message": message})
            )
            _LOGGER.debug("已发送TTS消息到设备 %s: %s", device_id, message)
        except Exception as exc:
            _LOGGER.error("发送TTS消息时出错: %s", exc)

    def get_connected_devices(self) -> List[str]:
        """获取已连接设备列表。"""
        return list(self.device_ids) 