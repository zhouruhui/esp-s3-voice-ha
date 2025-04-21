"""设备状态传感器。"""
import logging
from typing import Optional, List

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    DOMAIN,
    DATA_WEBSOCKET,
    EVENT_DEVICE_CONNECTED,
    EVENT_DEVICE_DISCONNECTED,
    DEVICE_CLASS_CONNECTIVITY,
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """设置二进制传感器实体。"""
    if not config_entry.entry_id or config_entry.entry_id not in hass.data[DOMAIN]:
        _LOGGER.error("无效的配置条目ID")
        return

    websocket = hass.data[DOMAIN][config_entry.entry_id].get(DATA_WEBSOCKET)
    if not websocket:
        _LOGGER.error("找不到WebSocket服务实例")
        return

    # 创建设备连接传感器
    sensors = []
    
    # 为所有已连接设备创建传感器
    for device_id in websocket.get_connected_devices():
        sensor = XiaozhiDeviceConnectionSensor(
            device_id=device_id, 
            entry_id=config_entry.entry_id,
            websocket=websocket,
        )
        sensors.append(sensor)
    
    # 监听新设备连接事件，动态添加传感器
    @callback
    def device_connected(event):
        """当新设备连接时创建传感器。"""
        device_id = event.data.get("device_id")
        if not device_id:
            return
            
        # 检查传感器是否已存在
        for sensor in sensors:
            if sensor.device_id == device_id:
                return
                
        # 创建新传感器
        new_sensor = XiaozhiDeviceConnectionSensor(
            device_id=device_id, 
            entry_id=config_entry.entry_id,
            websocket=websocket,
        )
        sensors.append(new_sensor)
        async_add_entities([new_sensor])
        
    # 注册事件监听器
    remove_device_connected_listener = hass.bus.async_listen(
        EVENT_DEVICE_CONNECTED, device_connected
    )
    
    # 在配置条目卸载时移除监听器
    config_entry.async_on_unload(remove_device_connected_listener)
    
    # 添加初始传感器
    if sensors:
        async_add_entities(sensors)


class XiaozhiDeviceConnectionSensor(BinarySensorEntity, RestoreEntity):
    """小智设备连接状态传感器。"""

    def __init__(self, device_id: str, entry_id: str, websocket) -> None:
        """初始化传感器。"""
        self.device_id = device_id
        self.entry_id = entry_id
        self.websocket = websocket
        self._attr_name = f"小智设备 {device_id} 连接状态"
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_{device_id}_connection"
        self._attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
        self._attr_is_on = True  # 默认为连接状态
        
        # 设备信息
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=f"小智语音助手 {device_id}",
            manufacturer="XiaoZhi",
            model="ESP32 语音助手",
            sw_version="1.0.0",
        )
        
        # 额外属性
        self._attr_extra_state_attributes = {
            "device_id": device_id,
            "status": "online",
            "last_seen": None,
        }
        
    async def async_added_to_hass(self) -> None:
        """当实体添加到HA时调用。"""
        await super().async_added_to_hass()
        
        # 恢复之前的状态
        last_state = await self.async_get_last_state()
        if last_state:
            self._attr_is_on = last_state.state == "on"
            if last_state.attributes.get("last_seen"):
                self._attr_extra_state_attributes["last_seen"] = last_state.attributes.get("last_seen")
        
        # 注册事件监听
        @callback
        def device_connected(event):
            """当设备连接时更新状态。"""
            if event.data.get("device_id") == self.device_id:
                self._attr_is_on = True
                self._attr_extra_state_attributes["status"] = "online"
                self._attr_extra_state_attributes["last_seen"] = self.hass.states.get("sensor.date_time").state
                self.async_write_ha_state()
                
        @callback
        def device_disconnected(event):
            """当设备断开连接时更新状态。"""
            if event.data.get("device_id") == self.device_id:
                self._attr_is_on = False
                self._attr_extra_state_attributes["status"] = "offline"
                self.async_write_ha_state()
                
        # 注册监听器
        self.async_on_remove(
            self.hass.bus.async_listen(EVENT_DEVICE_CONNECTED, device_connected)
        )
        self.async_on_remove(
            self.hass.bus.async_listen(EVENT_DEVICE_DISCONNECTED, device_disconnected)
        )
        
        # 检查当前连接状态
        if self.device_id in self.websocket.get_connected_devices():
            self._attr_is_on = True
            self._attr_extra_state_attributes["status"] = "online"
            self._attr_extra_state_attributes["last_seen"] = self.hass.states.get("sensor.date_time").state
        else:
            self._attr_is_on = False
            self._attr_extra_state_attributes["status"] = "offline"
            
    @property
    def available(self) -> bool:
        """返回实体是否可用。"""
        return True  # 传感器总是可用的 