"""Binary sensor for XiaoZhi ESP32 integration."""
from __future__ import annotations

import logging
from typing import Any, Dict

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_ON, STATE_OFF
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from .const import DOMAIN, CONNECTED, DISCONNECTED

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the XiaoZhi ESP32 binary sensor."""
    websocket = hass.data[DOMAIN][config_entry.entry_id].get("websocket")
    
    if not websocket:
        _LOGGER.error("找不到WebSocket服务实例")
        return
    
    # 添加设备连接状态传感器
    async_add_entities([XiaozhiConnectionSensor(hass, config_entry, websocket)])
    
    @callback
    def device_connected_callback(device_id: str) -> None:
        """当新设备连接时添加对应的传感器。"""
        # 这里可以添加其他设备特定的传感器
        pass
    
    # 监听websocket中的设备连接事件
    websocket.device_connected_callback = device_connected_callback


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
        
        # 注册事件监听器
        self._async_update_callback_listener = None
        
    async def async_added_to_hass(self) -> None:
        """Register callbacks when entity is added."""
        await super().async_added_to_hass()
        
        # 监听设备状态变化事件
        @callback
        def _async_update_callback(event) -> None:
            """Handle device state changes."""
            device_id = event.data.get("device_id")
            state = event.data.get("state")
            
            if state == CONNECTED:
                self._attr_is_on = True
                self.async_write_ha_state()
            elif state == DISCONNECTED:
                self._attr_is_on = False
                self.async_write_ha_state()
        
        self.hass.bus.async_listen("xiaozhi_device_state_changed", _async_update_callback)
        
        # 初始化状态为已连接的设备列表
        connected_devices = [
            device_id for device_id, device in self.websocket.devices.items()
            if device.get("connected", False)
        ]
        
        if connected_devices:
            self._attr_is_on = True
            self.async_write_ha_state()
    
    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # 只要组件加载了就认为传感器可用
        return True
    
    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the state attributes."""
        return {
            "connected_devices": [
                device_id for device_id, device in self.websocket.devices.items()
                if device.get("connected", False)
            ],
            "total_connections": len(self.websocket.connections),
            "websocket_port": self.websocket.port,
            "websocket_path": self.websocket.websocket_path,
        }
    
    @property
    def icon(self) -> str:
        """Return the icon to use in the frontend."""
        return "mdi:microphone-message" if self.is_on else "mdi:microphone-off" 