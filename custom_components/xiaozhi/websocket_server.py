"""XiaoZhi ESP32 WebSocket服务。"""
import asyncio
import json
import logging
import aiohttp
import traceback
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

"""
小智ESP32设备WebSocket协议说明：

1. 建立连接: 
   - 设备通过WebSocket连接到服务器
   - 设备发送hello消息，包含transport和audio_params信息
   - 服务器必须回复包含transport="websocket"的hello响应

2. 通信格式:
   - 二进制数据: 音频数据，通常是Opus编码
   - 文本消息: JSON格式，必须包含type字段

3. 消息类型:
   - hello: 握手消息
   - listen: 录音状态控制
   - abort: 中止当前对话
   - tts: 文本转语音消息
   - voice: 语音识别请求
   - recognition_result: 语音识别结果

4. 错误处理:
   - ESP32设备端对消息格式有严格要求，缺少字段可能导致崩溃
   - 必须正确处理二进制数据和文本消息
"""

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
            import websockets
            # 检查websockets库版本
            websockets_version = getattr(websockets, "__version__", "unknown")
            _LOGGER.info("使用websockets库版本: %s", websockets_version)
            
            # 适配不同版本的websockets库
            if websockets_version.startswith("10.") or websockets_version.startswith("11."):
                # 10.x, 11.x 版本API
                self.server = await websockets.serve(
                    self.handle_connection, "0.0.0.0", self.port, ping_interval=30
                )
            elif hasattr(websockets, "server") and hasattr(websockets.server, "serve"):
                # 如果确实有server子模块
                self.server = await websockets.server.serve(
                    self.handle_connection, "0.0.0.0", self.port, ping_interval=30
                )
            elif hasattr(websockets, "Server"):
                # 15.x 版本使用Server类
                from websockets.server import serve
                self.server = await serve(
                    self.handle_connection, "0.0.0.0", self.port, ping_interval=30
                )
            else:
                # 其他版本尝试直接调用
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
            traceback.print_exc()
            raise

    async def stop(self) -> None:
        """停止WebSocket服务器。"""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            self.server = None
            _LOGGER.info("WebSocket服务器已停止")

    async def handle_connection(self, websocket) -> None:
        """处理新的WebSocket连接。"""
        device_id = None
        
        # 获取path从websocket对象
        path = websocket.path
        
        if path != self.websocket_path:
            _LOGGER.warning("收到无效路径的连接请求: %s", path)
            await websocket.close(1008, "无效的WebSocket路径")
            return

        try:
            # 从headers获取设备信息
            headers = websocket.request_headers
            _LOGGER.debug("收到连接请求 headers: %s", headers)
            
            # 尝试从header获取设备ID (符合小智规范)
            device_id = headers.get("Device-Id")
            auth_token = headers.get("Authorization")
            protocol_version = headers.get("Protocol-Version")
            client_id = headers.get("Client-Id")
            
            _LOGGER.debug("连接信息: device_id=%s, protocol=%s, client=%s", 
                         device_id, protocol_version, client_id)
            
            # 等待hello消息
            initial_message = await websocket.recv()
            _LOGGER.debug("收到初始消息: %s", initial_message)
            
            try:
                data = json.loads(initial_message)
                message_type = data.get("type")
                
                # 如果是hello消息，则处理
                if message_type == "hello":
                    # 打印完整的hello消息内容以便调试
                    _LOGGER.info("收到hello消息: %s", json.dumps(data))
                    
                    # 如果header中没有设备ID，尝试从消息中获取
                    if not device_id:
                        device_id = data.get("device_id")
                    
                    if not device_id:
                        _LOGGER.warning("无法获取设备ID")
                        await websocket.close(1008, "缺少设备ID")
                        return

                    _LOGGER.info("设备 %s 已连接", device_id)

                    # 存储连接和设备信息
                    self.connections[device_id] = websocket
                    self.device_ids.add(device_id)

                    # 发送符合小智规范的hello响应 - 关键修改：完全符合小智协议
                    response = {
                        "type": "hello",
                        "transport": "websocket",  # 添加transport字段
                        "audio_params": {          # 添加audio_params字段
                            "sample_rate": 16000,
                            "format": "opus",
                            "channels": 1
                        },
                        "status": "ok"
                    }
                    _LOGGER.debug("发送hello响应: %s", json.dumps(response))
                    await websocket.send(json.dumps(response))

                    # 触发设备连接回调
                    if self.on_device_connected:
                        self.on_device_connected(device_id)

                    # 开始处理消息
                    await self._handle_messages(device_id, websocket)
                else:
                    _LOGGER.warning("首条消息不是hello类型: %s", message_type)
                    await websocket.close(1008, "期望hello消息")
            except json.JSONDecodeError:
                _LOGGER.warning("收到无效的JSON消息: %s", initial_message)
                await websocket.close(1008, "无效的JSON格式")
            except Exception as exc:
                _LOGGER.error("处理连接消息时出错: %s", exc)
                traceback.print_exc()  # 打印详细错误信息
                await websocket.close(1011, "服务器内部错误")
        except ConnectionClosed:
            _LOGGER.info("连接被关闭")
        except Exception as exc:
            _LOGGER.error("处理WebSocket连接时出错: %s", exc)
            traceback.print_exc()  # 打印详细错误信息
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
                    # 判断是文本消息还是二进制消息
                    if isinstance(message, str):
                        # 处理文本消息
                        data = json.loads(message)
                        message_type = data.get("type", "unknown")
                        _LOGGER.debug("收到来自设备 %s 的文本消息: %s", device_id, message_type)
                        
                        # 根据消息类型处理
                        if message_type == "start_listen":
                            # 开始监听处理
                            await self._handle_start_listen(device_id, data)
                        elif message_type == "stop_listen":
                            # 停止监听处理
                            await self._handle_stop_listen(device_id, data)
                        elif message_type == "wakeword_detected":
                            # 唤醒词检测处理
                            await self._handle_wakeword_detected(device_id, data)
                        elif message_type == "auth": 
                            # 处理认证消息 - 小智协议使用auth类型消息
                            await self._handle_auth_message(device_id, data, websocket)
                        elif message_type == "voice":
                            # 处理语音消息
                            await self._handle_voice_message(device_id, data, websocket)
                        elif message_type == "abort":
                            # 中止处理
                            await self._handle_abort(device_id, data)
                        elif message_type == "ping":
                            # 心跳响应
                            await websocket.send(json.dumps({"type": "pong"}))
                        else:
                            _LOGGER.warning("未识别的消息类型: %s", message_type)
                    else:
                        # 处理二进制数据 (音频数据)
                        _LOGGER.debug("收到来自设备 %s 的二进制数据，长度: %d", device_id, len(message))
                        await self._handle_binary_message(device_id, message)
                        
                except json.JSONDecodeError:
                    _LOGGER.warning("收到无效的JSON消息")
                except Exception as exc:
                    _LOGGER.error("处理消息时出错: %s", exc)
                    traceback.print_exc()
        except ConnectionClosed:
            _LOGGER.info("设备 %s 的连接已关闭", device_id)
        except Exception as exc:
            _LOGGER.error("_handle_messages 出错: %s", exc)
            traceback.print_exc()

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
        """转发语音请求到外部服务。"""
        if not self.forward_url:
            _LOGGER.error("未配置转发URL")
            await websocket.send(json.dumps({
                "type": WS_MSG_TYPE_ERROR,
                "error": "missing_forward_url",
                "message": "未配置转发URL"
            }))
            return
            
        try:
            # 客户端会话
            session = async_get_clientsession(self.hass)
            
            # 将Forward URL从ws开头转换为http开头用于aiohttp请求
            http_url = self.forward_url.replace("ws://", "http://").replace("wss://", "https://")
            
            # 发送请求
            _LOGGER.debug("转发请求到: %s", http_url)
            
            # 对于不同类型的消息使用不同的处理逻辑
            message_type = data.get("type", "")
            
            if message_type == "voice":
                # 处理语音识别请求
                audio_data = data.get("data")
                format_type = data.get("format", "opus")
                
                # 组装请求数据
                payload = {
                    "audio_data": audio_data,
                    "format": format_type,
                    "device_id": device_id
                }
                
                async with session.post(f"{http_url}/recognize", json=payload) as response:
                    if response.status == 200:
                        result = await response.json()
                        
                        # 返回结果给设备
                        response_message = {
                            "type": WS_MSG_TYPE_RECOGNITION_RESULT,
                            "text": result.get("text", ""),
                            "is_final": True
                        }
                        await websocket.send(json.dumps(response_message))
                    else:
                        error_text = await response.text()
                        _LOGGER.error("转发请求失败: %s - %s", response.status, error_text)
                        await websocket.send(json.dumps({
                            "type": WS_MSG_TYPE_ERROR,
                            "error": ERR_SERVER_ERROR,
                            "message": f"转发服务返回错误: {response.status}"
                        }))
            else:
                # 其他类型的请求转发
                async with session.post(f"{http_url}/forward", json=data) as response:
                    if response.status == 200:
                        result = await response.json()
                        await websocket.send(json.dumps(result))
                    else:
                        error_text = await response.text()
                        _LOGGER.error("转发请求失败: %s - %s", response.status, error_text)
                        await websocket.send(json.dumps({
                            "type": WS_MSG_TYPE_ERROR,
                            "error": ERR_SERVER_ERROR,
                            "message": f"转发服务返回错误: {response.status}"
                        }))
                        
        except aiohttp.ClientError as exc:
            _LOGGER.error("HTTP请求错误: %s", exc)
            await websocket.send(json.dumps({
                "type": WS_MSG_TYPE_ERROR,
                "error": ERR_SERVER_ERROR,
                "message": f"HTTP请求错误: {str(exc)}"
            }))
        except Exception as exc:
            _LOGGER.error("转发请求时出错: %s", exc)
            traceback.print_exc()
            await websocket.send(json.dumps({
                "type": WS_MSG_TYPE_ERROR,
                "error": ERR_SERVER_ERROR,
                "message": f"转发请求时出错: {str(exc)}"
            }))

    async def send_tts_message(self, device_id: str, message: str) -> None:
        """发送TTS消息到设备。"""
        try:
            if device_id not in self.connections:
                _LOGGER.warning("设备 %s 未连接，无法发送TTS消息", device_id)
                return

            websocket = self.connections[device_id]
            
            # 首先发送TTS开始消息
            await websocket.send(
                json.dumps({
                    "type": "tts", 
                    "state": "sentence_start", 
                    "message": message
                })
            )
            
            # 假设TTS处理完成，发送结束消息
            await websocket.send(
                json.dumps({
                    "type": "tts", 
                    "state": "sentence_end"
                })
            )
            
            _LOGGER.debug("已发送TTS消息到设备 %s: %s", device_id, message)
        except Exception as exc:
            _LOGGER.error("发送TTS消息时出错: %s", exc)
            traceback.print_exc()

    def get_connected_devices(self) -> List[str]:
        """获取已连接设备列表。"""
        return list(self.device_ids)

    async def _handle_start_listen(self, device_id: str, data: Dict) -> None:
        """处理开始监听消息。"""
        _LOGGER.debug("处理开始监听消息: %s", data)
        # 在这里可以添加开始监听的逻辑
        # 如果是代理模式，可以将消息转发到外部服务
        
    async def _handle_stop_listen(self, device_id: str, data: Dict) -> None:
        """处理停止监听消息。"""
        _LOGGER.debug("处理停止监听消息: %s", data)
        # 在这里可以添加停止监听的逻辑
        
    async def _handle_wakeword_detected(self, device_id: str, data: Dict) -> None:
        """处理唤醒词检测消息。"""
        _LOGGER.debug("处理唤醒词检测消息: %s", data)
        # 可以触发Home Assistant事件或启动语音处理流程
        
    async def _handle_abort(self, device_id: str, data: Dict) -> None:
        """处理中止消息。"""
        _LOGGER.debug("处理中止消息: %s", data)
        # 中止当前正在进行的处理
        
    async def _handle_binary_message(self, device_id: str, data: bytes) -> None:
        """处理二进制音频数据。"""
        _LOGGER.debug("收到来自设备 %s 的二进制数据，长度: %d字节", device_id, len(data))
        
        try:
            # 判断是否为代理模式
            if self.proxy_mode and self.forward_url:
                # 代理模式下，转发到外部服务
                await self._forward_binary_data(device_id, data)
            else:
                # 本地处理模式，将二进制数据转换为语音命令
                websocket = self.connections.get(device_id)
                if not websocket:
                    _LOGGER.error("设备 %s 未连接，无法处理音频数据", device_id)
                    return
                
                # 使用Home Assistant语音助手Pipeline处理
                if self.pipeline_id:
                    try:
                        _LOGGER.debug("提交二进制音频数据到Pipeline: %s", self.pipeline_id)
                        # 提交音频数据到Pipeline
                        result = await assist_pipeline.async_pipeline_from_audio(
                            self.hass,
                            data,  # 直接使用二进制数据
                            pipeline_id=self.pipeline_id,
                            language="zh-CN",
                        )
                        
                        if result and result.response:
                            _LOGGER.debug("语音识别结果: %s", result.response)
                            
                            # 返回识别结果
                            await websocket.send(json.dumps({
                                "type": WS_MSG_TYPE_RECOGNITION_RESULT,
                                "text": result.response,
                                "status": "success"
                            }))
                        else:
                            _LOGGER.warning("语音助手Pipeline没有返回结果")
                            await websocket.send(json.dumps({
                                "type": WS_MSG_TYPE_ERROR,
                                "error": "no_response",
                                "message": "语音助手没有返回响应"
                            }))
                    except Exception as exc:
                        _LOGGER.error("处理音频数据出错: %s", exc)
                        traceback.print_exc()
                        await websocket.send(json.dumps({
                            "type": WS_MSG_TYPE_ERROR,
                            "error": "processing_error",
                            "message": f"音频处理错误: {str(exc)}"
                        }))
                else:
                    _LOGGER.error("未配置语音助手Pipeline")
        except Exception as exc:
            _LOGGER.error("处理二进制数据时出错: %s", exc)
            traceback.print_exc()
    
    async def _forward_binary_data(self, device_id: str, data: bytes) -> None:
        """转发二进制数据到外部服务。"""
        if not self.forward_url:
            _LOGGER.error("未配置转发URL")
            return
            
        try:
            # 使用HTTP请求而不是WebSocket
            session = async_get_clientsession(self.hass)
            
            # 将WebSocket URL转换为HTTP URL
            http_url = self.forward_url
            if http_url.startswith("ws://"):
                http_url = http_url.replace("ws://", "http://")
            elif http_url.startswith("wss://"):
                http_url = http_url.replace("wss://", "https://")
            
            # 构建完整的请求URL
            request_url = f"{http_url.rstrip('/')}/voice_recognition"
            
            _LOGGER.debug("使用HTTP POST发送音频数据到: %s", request_url)
            
            # 构建请求头
            headers = {
                "Content-Type": "audio/opus",
                "Device-Id": device_id
            }
            
            # 发送POST请求
            async with session.post(
                request_url,
                data=data,
                headers=headers,
                timeout=10.0
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    _LOGGER.debug("收到识别结果: %s", result)
                    
                    # 获取连接的WebSocket
                    websocket = self.connections.get(device_id)
                    if websocket:
                        # 返回识别结果
                        await websocket.send(json.dumps({
                            "type": WS_MSG_TYPE_RECOGNITION_RESULT,
                            "text": result.get("text", ""),
                            "status": "success"
                        }))
                    else:
                        _LOGGER.warning("无法发送识别结果，设备可能已断开连接")
                else:
                    _LOGGER.error("HTTP请求失败: %d - %s", 
                                 response.status, await response.text())
        except Exception as exc:
            _LOGGER.error("转发二进制数据时出错: %s", exc)
            traceback.print_exc()
    
    async def _process_audio_locally(self, device_id: str, audio_data: bytes) -> None:
        """本地处理音频数据。"""
        try:
            if not self.pipeline_id:
                _LOGGER.error("未配置语音助手Pipeline")
                return
                
            # 调用Home Assistant的语音助手Pipeline处理音频
            # 实际实现...
            _LOGGER.debug("使用Pipeline %s 处理音频数据", self.pipeline_id)
        except Exception as exc:
            _LOGGER.error("本地处理音频数据时出错: %s", exc)
            traceback.print_exc()

    async def _handle_auth_message(self, device_id: str, data: Dict, websocket) -> None:
        """处理auth认证消息。"""
        try:
            # 从消息中获取device-id
            device_id_from_msg = data.get("device-id")
            
            if device_id_from_msg and device_id_from_msg != device_id:
                # 如果消息中的device-id与连接保存的不同，更新device_id
                _LOGGER.info("设备ID已更新: %s -> %s", device_id, device_id_from_msg)
                
                # 更新连接信息
                if device_id in self.connections:
                    del self.connections[device_id]
                if device_id in self.device_ids:
                    self.device_ids.remove(device_id)
                
                device_id = device_id_from_msg
                self.connections[device_id] = websocket
                self.device_ids.add(device_id)
            
            # 返回认证成功响应
            await websocket.send(json.dumps({
                "type": "auth",
                "status": "ok"
            }))
            
            _LOGGER.debug("设备 %s 认证成功", device_id)
        except Exception as exc:
            _LOGGER.error("处理认证消息时出错: %s", exc)
            await websocket.send(json.dumps({
                "type": "auth", 
                "status": "error",
                "message": f"认证处理错误: {str(exc)}"
            })) 