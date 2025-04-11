"""XiaoZhi ESP32 voice assistant integration."""
import logging
from typing import Any, Optional

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
from homeassistant.components import assist_pipeline
from homeassistant.helpers.network import get_url
from homeassistant.exceptions import HomeAssistantError

from .const import (
    DOMAIN,
    PLATFORMS,
    CONF_WEBSOCKET_PORT,
    CONF_WEBSOCKET_PATH,
    CONF_PIPELINE_ID,
    SERVICE_SEND_TTS,
    SERVICE_GET_CONFIG,
    ATTR_DEVICE_ID,
    ATTR_MESSAGE,
    ATTR_CONFIG_ENTRY_ID,
    ATTR_FALLBACK_URL,
    DATA_WEBSOCKET,
    EVENT_DEVICE_CONNECTED,
    EVENT_DEVICE_DISCONNECTED,
)

_LOGGER = logging.getLogger(__name__)

SEND_TTS_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Required(ATTR_MESSAGE): cv.string,
    }
)

GET_DEVICE_CONFIG_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Optional(ATTR_DEVICE_ID): cv.string,
        vol.Optional(ATTR_FALLBACK_URL): cv.string,
    }
)

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the XiaoZhi ESP32 component."""
    hass.data.setdefault(DOMAIN, {})
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up XiaoZhi ESP32 from a config entry."""
    _LOGGER.info("设置 XiaoZhi ESP32 语音助手")
    
    try:
        # 存储配置
        config = entry.data
        
        # 获取配置项
        pipeline_id = config.get(CONF_PIPELINE_ID)
        port = config.get(CONF_WEBSOCKET_PORT)
        websocket_path = config.get(CONF_WEBSOCKET_PATH)
        
        # 检查Pipeline配置
        if not pipeline_id:
            _LOGGER.error("需要指定语音助手Pipeline")
            return False
            
        # 检查Pipeline是否存在
        try:
            pipelines = await assist_pipeline.async_get_pipelines(hass)
            pipeline_exists = any(p.id == pipeline_id for p in pipelines)
            
            if not pipeline_exists:
                _LOGGER.error("指定的语音助手Pipeline不存在: %s", pipeline_id)
                return False
        except Exception as exc:
            _LOGGER.error("检查Pipeline时出错: %s", exc)
            return False
            
        # 初始化WebSocket服务
        try:
            from .websocket_server import XiaozhiWebSocket
            
            websocket = XiaozhiWebSocket(
                hass=hass, 
                port=port, 
                websocket_path=websocket_path,
                pipeline_id=pipeline_id,
            )
            
            await websocket.start()
        except Exception as exc:
            _LOGGER.error("启动WebSocket服务时出错: %s", exc)
            return False
        
        # 存储WebSocket实例以便后续使用
        hass.data[DOMAIN][entry.entry_id] = {
            DATA_WEBSOCKET: websocket,
        }
        
        _LOGGER.info("XiaoZhi ESP32助手服务已启动，监听端口 %s，路径 %s", 
                    port, websocket_path)
        
        # 注册设备连接/断开连接事件处理
        @callback
        def on_device_connected(device_id: str) -> None:
            """当设备连接时触发事件。"""
            hass.bus.async_fire(
                EVENT_DEVICE_CONNECTED,
                {"device_id": device_id}
            )
            
        @callback
        def on_device_disconnected(device_id: str) -> None:
            """当设备断开连接时触发事件。"""
            hass.bus.async_fire(
                EVENT_DEVICE_DISCONNECTED,
                {"device_id": device_id}
            )
            
        # 注册事件处理器到WebSocket服务
        websocket.on_device_connected = on_device_connected
        websocket.on_device_disconnected = on_device_disconnected
        
        # 注册服务
        hass.services.async_register(
            DOMAIN,
            SERVICE_SEND_TTS,
            _async_send_tts,
            schema=SEND_TTS_SCHEMA,
        )
        
        hass.services.async_register(
            DOMAIN,
            SERVICE_GET_CONFIG,
            _get_device_config,
            schema=GET_DEVICE_CONFIG_SCHEMA,
        )
        
        # 设置平台
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        
        return True
    except Exception as exc:
        _LOGGER.error("设置XiaoZhi ESP32集成时出错: %s", exc)
        return False

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    try:
        # 卸载平台
        unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
        
        # 停止WebSocket服务
        if entry.entry_id in hass.data[DOMAIN]:
            websocket = hass.data[DOMAIN][entry.entry_id].get(DATA_WEBSOCKET)
            if websocket:
                await websocket.stop()
            
            # 移除服务和数据
            hass.services.async_remove(DOMAIN, SERVICE_SEND_TTS)
            hass.services.async_remove(DOMAIN, SERVICE_GET_CONFIG)
            hass.data[DOMAIN].pop(entry.entry_id)
        
        return unload_ok
    except Exception as exc:
        _LOGGER.error("卸载XiaoZhi ESP32集成时出错: %s", exc)
        return False

async def _async_send_tts(hass: HomeAssistant, service_call: ServiceCall) -> None:
    """发送TTS消息到设备服务。"""
    try:
        device_id = service_call.data.get(ATTR_DEVICE_ID)
        message = service_call.data.get(ATTR_MESSAGE)
        
        if not device_id or not message:
            _LOGGER.error("发送TTS服务调用缺少必要参数")
            return
        
        # 查找WebSocket服务实例
        websocket = None
        for entry_data in hass.data[DOMAIN].values():
            if DATA_WEBSOCKET in entry_data:
                websocket = entry_data[DATA_WEBSOCKET]
                break
        
        if not websocket:
            _LOGGER.error("无法找到WebSocket服务实例")
            return
        
        # 发送TTS消息
        await websocket.send_tts_message(device_id, message)
    except Exception as exc:
        _LOGGER.error("发送TTS消息时出错: %s", exc)

async def _get_device_config(hass: HomeAssistant, service_call: ServiceCall) -> None:
    """生成设备配置信息。"""
    try:
        config_entry_id = service_call.data.get(ATTR_CONFIG_ENTRY_ID)
        device_id = service_call.data.get(ATTR_DEVICE_ID, "xiaozhi_device")
        fallback_url = service_call.data.get(ATTR_FALLBACK_URL)
        
        if config_entry_id not in hass.data[DOMAIN]:
            _LOGGER.error("找不到指定的配置条目ID: %s", config_entry_id)
            return
        
        entry_data = hass.data[DOMAIN][config_entry_id]
        websocket = entry_data.get(DATA_WEBSOCKET)
        
        if not websocket:
            _LOGGER.error("无法找到WebSocket服务实例")
            return
        
        # 获取Home Assistant外部URL
        try:
            external_url = get_url(hass, prefer_external=True)
        except Exception:
            external_url = fallback_url
            
        if not external_url:
            _LOGGER.error("无法获取Home Assistant外部URL，且未提供备选URL")
            return
        
        # 构建WebSocket URL
        ws_path = websocket.websocket_path.lstrip("/")
        websocket_url = f"{external_url.rstrip('/')}/{ws_path}"
        
        # 将http改为ws，https改为wss
        websocket_url = websocket_url.replace("http://", "ws://").replace("https://", "wss://")
        
        # 生成配置信息
        config_info = {
            "device_id": device_id,
            "websocket_url": websocket_url,
            "reconnect_interval": 5000,
            "ping_interval": 30000
        }
        
        # 在日志中显示配置信息，实际应用中应该创建通知或UI显示
        _LOGGER.info("XiaoZhi ESP32设备配置信息:")
        _LOGGER.info("设备ID: %s", config_info["device_id"])
        _LOGGER.info("WebSocket URL: %s", config_info["websocket_url"])
        _LOGGER.info("重连间隔(ms): %s", config_info["reconnect_interval"])
        _LOGGER.info("心跳间隔(ms): %s", config_info["ping_interval"])
        _LOGGER.info("请将此配置信息用于ESP32固件编译")
    except Exception as exc:
        _LOGGER.error("获取设备配置时出错: %s", exc) 