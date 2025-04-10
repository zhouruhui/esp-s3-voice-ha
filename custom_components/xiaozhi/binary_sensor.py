"""Binary sensor for XiaoZhi ESP32 integration."""
from __future__ import annotations

import logging
from typing import Any, Dict

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from .const import (
    DOMAIN, 
    CONNECTED, 
    DISCONNECTED, 
    DEVICE_CLASS_CONNECTIVITY,
    DATA_WEBSOCKET,
    EVENT_DEVICE_CONNECTED,
    EVENT_DEVICE_DISCONNECTED
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the XiaoZhi ESP32 binary sensor."""
    try:
        if config_entry.entry_id not in hass.data.get(DOMAIN, {}):
            _LOGGER.error("集成没有正确初始化")
            return
            
        websocket = hass.data[DOMAIN][config_entry.entry_id].get(DATA_WEBSOCKET)
        
        if not websocket:
            _LOGGER.error("找不到WebSocket服务实例")
            return
        
        # 添加设备连接状态传感器
        async_add_entities([XiaozhiConnectionSensor(hass, config_entry, websocket)])
        
    except Exception as exc:
        _LOGGER.error("设置XiaoZhi ESP32 binary sensor时出错: %s", exc)


class XiaozhiConnectionSensor(BinarySensorEntity):
    """Binary sensor for XiaoZhi ESP32 connection status."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    
    def __init__(
        self, 
        hass: HomeAssistant, 
        config_entry: ConfigEntry,
        websocket: Any
    ) -> None:
        """Initialize the connection sensor."""
        self.hass = hass
        self.config_entry = config_entry
        self.websocket = websocket
        
        name = config_entry.data.get("name", "XiaoZhi ESP32")
        self._attr_unique_id = f"{config_entry.entry_id}_connection"
        self._attr_name = "连接状态"
        self._attr_should_poll = False
        
        # 设置设备信息
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry.entry_id)},
            name=name,
            manufacturer="XiaoZhi",
            model="ESP32 语音助手",
            sw_version="1.0.0",
        )
        
        # 默认状态为未连接
        self._attr_is_on = False
        
    async def async_added_to_hass(self) -> None:
        """Register callbacks when entity is added."""
        try:
            await super().async_added_to_hass()
            
            # 监听设备连接事件
            @callback
            def device_connected(event) -> None:
                """处理设备连接事件"""
                self._attr_is_on = True
                self.async_write_ha_state()
            
            # 监听设备断开连接事件
            @callback
            def device_disconnected(event) -> None:
                """处理设备断开连接事件"""
                self._attr_is_on = False
                self.async_write_ha_state()
            
            # 注册事件监听器
            self.async_on_remove(
                self.hass.bus.async_listen(EVENT_DEVICE_CONNECTED, device_connected)
            )
            self.async_on_remove(
                self.hass.bus.async_listen(EVENT_DEVICE_DISCONNECTED, device_disconnected)
            )
            
            # 初始化状态：检查是否有已连接的设备
            if hasattr(self.websocket, 'device_ids') and len(self.websocket.device_ids) > 0:
                self._attr_is_on = True
                self.async_write_ha_state()
                
        except Exception as exc:
            _LOGGER.error("添加传感器到hass时出错: %s", exc)
    
    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # 只要组件加载了就认为传感器可用
        return True
    
    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the state attributes."""
        try:
            # 获取设备的连接信息
            if hasattr(self.websocket, 'device_ids') and hasattr(self.websocket, 'connections'):
                return {
                    "connected_devices": list(self.websocket.device_ids),
                    "total_connections": len(self.websocket.connections),
                    "websocket_port": self.websocket.port,
                    "websocket_path": self.websocket.websocket_path,
                }
            return {}
        except Exception as exc:
            _LOGGER.error("获取传感器属性时出错: %s", exc)
            return {
                "error": f"获取属性时出错: {exc}"
            }
    
    @property
    def icon(self) -> str:
        """Return the icon to use in the frontend."""
        return "mdi:microphone-message" if self.is_on else "mdi:microphone-off" 