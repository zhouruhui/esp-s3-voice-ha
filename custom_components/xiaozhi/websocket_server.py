"""XiaoZhi ESP32 WebSocket服务。"""
import asyncio
import json
import logging
import os
import traceback
import time
from typing import Any, Dict, List, Optional, Set, Callable

import voluptuous as vol
import websockets
from websockets.exceptions import ConnectionClosed

from homeassistant.components import assist_pipeline
from homeassistant.core import HomeAssistant

from .const import (
    WS_MSG_TYPE_HELLO,
    WS_MSG_TYPE_RECOGNITION_RESULT,
    WS_MSG_TYPE_TTS_START,
    WS_MSG_TYPE_TTS_END,
    WS_MSG_TYPE_ERROR,
    ERR_INVALID_MESSAGE,
    ERR_SERVER_ERROR,
    ERR_MISSING_PIPELINE,
    WS_MSG_TYPE_AUDIO_DATA,
    TTS_STATE_START,
    TTS_STATE_END,
    TTS_STATE_ERROR,
    AUDIO_FORMAT_OPUS
)

_LOGGER = logging.getLogger(__name__)

# 测试模式 - 启用后，将使用硬编码的对话而不是实际的音频识别
TEST_MODE = os.environ.get("XIAOZHI_TEST_MODE", "1") == "1"
TEST_COMMAND = os.environ.get("XIAOZHI_TEST_COMMAND", "打开客厅灯")

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
   - start_listen: 开始录音
   - stop_listen: 停止录音
   - wakeword_detected: 唤醒词检测
   - auth: 设备认证
   - tts: 文本转语音消息
   - recognition_result: 语音识别结果
   - error: 错误消息
"""

class XiaozhiWebSocket:
    """WebSocket服务器组件，处理与ESP32设备的通信。"""

    def __init__(
        self,
        hass: HomeAssistant,
        port: int,
        websocket_path: str,
        pipeline_id: Optional[str] = None,
    ) -> None:
        """初始化WebSocket服务器。"""
        self.hass = hass
        self.port = port
        self.websocket_path = websocket_path
        self.pipeline_id = pipeline_id
        self.server = None
        self.connections: Dict[str, Any] = {}
        self.device_ids: Set[str] = set()
        
        # 回调函数
        self.on_device_connected: Optional[Callable[[str], None]] = None
        self.on_device_disconnected: Optional[Callable[[str], None]] = None
        
        # 添加调试标志
        self.debug_mode = True
        _LOGGER.info("XiaoZhi WebSocket服务器初始化, 调试模式: %s, 测试命令: %s", 
                    "启用" if TEST_MODE else "禁用", 
                    TEST_COMMAND if TEST_MODE else "无")

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
                "XiaoZhi ESP32助手服务已启动, 监听 0.0.0.0:%s%s",
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

                    # 发送符合小智规范的hello响应
                    response = {
                        "type": "hello",
                        "transport": "websocket",
                        "audio_params": {
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
                traceback.print_exc()
                await websocket.close(1011, "服务器内部错误")
        except ConnectionClosed:
            _LOGGER.info("连接被关闭")
        except Exception as exc:
            _LOGGER.error("处理WebSocket连接时出错: %s", exc)
            traceback.print_exc()
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
                        elif message_type == "abort":
                            # 中止处理
                            await self._handle_abort(device_id, data)
                        elif message_type == "ping":
                            # 心跳响应
                            await websocket.send(json.dumps({"type": "pong"}))
                        elif message_type == "iot":
                            # 处理IoT消息，设备可能发送的控制命令
                            _LOGGER.debug("收到IoT消息: %s", data)
                            # 简单回复确认
                            await websocket.send(json.dumps({"type": "iot_response", "status": "ok"}))
                        elif message_type == "listen":
                            # 处理listen消息，设备发送的录音状态
                            # 返回录音确认
                            await websocket.send(json.dumps({"type": "listen_response", "status": "ok"}))
                        else:
                            _LOGGER.warning("未识别的消息类型: %s", message_type)
                    else:
                        # 处理二进制数据 (音频数据)
                        await self._handle_binary_message(device_id, message, websocket)
                        
                except json.JSONDecodeError:
                    _LOGGER.warning("收到无效的JSON消息")
                except Exception as exc:
                    _LOGGER.error("处理消息时出错: %s", exc)
        except ConnectionClosed:
            _LOGGER.info("设备 %s 的连接已关闭", device_id)
        except Exception as exc:
            _LOGGER.error("_handle_messages 出错: %s", exc)

    async def send_tts_message(self, device_id: str, message: str) -> None:
        """发送TTS消息到设备。"""
        try:
            if device_id not in self.connections:
                _LOGGER.warning("设备 %s 未连接，无法发送TTS消息", device_id)
                return

            websocket = self.connections[device_id]
            
            if not self.pipeline_id:
                _LOGGER.error("未配置语音助手Pipeline，无法生成TTS")
                await websocket.send(json.dumps({
                    "type": WS_MSG_TYPE_ERROR,
                    "error": ERR_MISSING_PIPELINE,
                    "message": "未配置语音助手Pipeline"
                }))
                return
                
            # 发送TTS开始消息
            await websocket.send(json.dumps({
                "type": WS_MSG_TYPE_TTS, 
                "state": TTS_STATE_START, 
                "message": message
            }))
            
            try:
                # 直接使用TTS API
                tts_output = await self.hass.services.async_call(
                    "tts",
                    "speak",
                    {
                        "entity_id": "media_player.xiaozhi_tts",  # 可以是任意媒体播放器
                        "message": message,
                        "cache": False
                    },
                    blocking=True,
                    return_response=True
                )
                
                # 获取音频数据URL或内容
                if tts_output:
                    # 告知设备TTS生成成功
                    _LOGGER.info("TTS消息已发送到设备 %s", device_id)
                else:
                    _LOGGER.warning("生成TTS音频失败")
            except Exception as exc:
                _LOGGER.error("生成TTS音频时出错: %s", exc)
                
            # 发送结束消息
            await websocket.send(json.dumps({
                "type": WS_MSG_TYPE_TTS, 
                "state": TTS_STATE_END
            }))
        except Exception as exc:
            _LOGGER.error("发送TTS消息时出错: %s", exc)

    def get_connected_devices(self) -> List[str]:
        """获取已连接设备列表。"""
        return list(self.device_ids)

    async def _handle_start_listen(self, device_id: str, data: Dict) -> None:
        """处理开始监听消息。"""
        _LOGGER.debug("处理开始监听消息: %s", data)
        # 设备端已经开始录音，服务端不需要响应
        
    async def _handle_stop_listen(self, device_id: str, data: Dict) -> None:
        """处理停止监听消息。"""
        _LOGGER.debug("处理停止监听消息: %s", data)
        # 设备端已经停止录音，服务端不需要响应
        
    async def _handle_wakeword_detected(self, device_id: str, data: Dict) -> None:
        """处理唤醒词检测消息。"""
        wakeword = data.get("wakeword", "unknown")
        _LOGGER.info("设备 %s 检测到唤醒词: %s", device_id, wakeword)
        
        # 可以触发Home Assistant事件
        self.hass.bus.async_fire(
            "xiaozhi_wakeword_detected",
            {"device_id": device_id, "wakeword": wakeword}
        )
        
        # 回复设备，确认收到唤醒词
        if device_id in self.connections:
            websocket = self.connections[device_id]
            try:
                await websocket.send(json.dumps({
                    "type": "wakeword_response",
                    "status": "ok"
                }))
                _LOGGER.debug("已向设备 %s 发送唤醒词响应", device_id)
            except Exception as exc:
                _LOGGER.error("发送唤醒词响应出错: %s", exc)

    async def _handle_abort(self, device_id: str, data: Dict) -> None:
        """处理中止消息。"""
        _LOGGER.debug("处理中止消息: %s", data)
        # 中止当前正在进行的处理
        
    async def _handle_binary_message(self, device_id: str, data: bytes, websocket) -> None:
        """处理二进制音频数据。"""
        try:
            _LOGGER.info("接收到来自设备 %s 的音频数据: %d 字节", device_id, len(data))
            
            # 保存少量音频数据用于调试
            try:
                debug_dir = os.path.join(self.hass.config.config_dir, "xiaozhi_debug")
                os.makedirs(debug_dir, exist_ok=True)
                debug_file = os.path.join(debug_dir, f"audio_{device_id}_{int(time.time())}.bin")
                with open(debug_file, "wb") as f:
                    f.write(data[:min(1024, len(data))])  # 只保存前1KB数据
                _LOGGER.info("已保存音频调试数据到 %s", debug_file)
            except Exception as exc:
                _LOGGER.error("保存音频调试数据失败: %s", exc)
            
            if not self.pipeline_id:
                _LOGGER.error("未配置语音助手Pipeline")
                await websocket.send(json.dumps({
                    "type": "error",
                    "error": "missing_pipeline",
                    "message": "未配置语音助手Pipeline"
                }))
                return
                
            # 使用Home Assistant的对话API处理
            try:
                # 尝试直接使用对话API
                _LOGGER.info("调用对话API, 命令: %s", TEST_COMMAND)
                conversation_result = await self.hass.services.async_call(
                    "conversation",
                    "process",
                    {
                        "text": TEST_COMMAND,  # 使用测试命令
                        "language": "zh-CN",
                        "agent_id": "homeassistant"
                    },
                    blocking=True,
                    return_response=True
                )
                
                _LOGGER.info("对话API返回结果: %s", str(conversation_result)[:200])
                
                if conversation_result and "response" in conversation_result:
                    response_text = conversation_result["response"]["speech"]["plain"]["speech"]
                    _LOGGER.info("语音处理结果: %s", response_text)
                    
                    # 返回识别结果
                    await websocket.send(json.dumps({
                        "type": "recognition_result",
                        "text": response_text,
                        "status": "success"
                    }))
                    
                    # 发送TTS开始消息
                    await websocket.send(json.dumps({
                        "type": WS_MSG_TYPE_TTS_START,
                        "message": response_text
                    }))
                    
                    # 发送TTS结束消息
                    await websocket.send(json.dumps({
                        "type": WS_MSG_TYPE_TTS_END
                    }))
                    
                    _LOGGER.info("已向设备 %s 发送响应消息", device_id)
                else:
                    _LOGGER.warning("对话API没有返回结果")
                    await websocket.send(json.dumps({
                        "type": "error",
                        "error": "no_response",
                        "message": "语音助手没有返回响应"
                    }))
            except Exception as exc:
                _LOGGER.error("调用对话API出错: %s", exc)
                await websocket.send(json.dumps({
                    "type": "error",
                    "error": "processing_error",
                    "message": f"音频处理错误: {str(exc)}"
                }))
        except Exception as exc:
            _LOGGER.error("处理二进制数据时出错: %s", exc)

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