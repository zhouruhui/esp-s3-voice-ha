"""XiaoZhi ESP32 语音助手集成的常量定义。"""
from homeassistant.const import Platform

DOMAIN = "xiaozhi"
PLATFORMS = [Platform.BINARY_SENSOR]

# 配置常量
CONF_NAME = "name"
CONF_WEBSOCKET_PORT = "websocket_port"
CONF_WEBSOCKET_PATH = "websocket_path"
CONF_PIPELINE_ID = "pipeline_id"
CONF_PROXY_MODE = "proxy_mode"
CONF_FORWARD_URL = "forward_url"

# 默认值
DEFAULT_WEBSOCKET_PORT = 6789
DEFAULT_WEBSOCKET_PATH = "/ws/xiaozhi"

# 服务名称
SERVICE_SEND_TTS = "send_tts"
SERVICE_GET_CONFIG = "get_device_config"

# 事件名称
EVENT_VOICE_COMMAND = "xiaozhi_voice_command"
EVENT_DEVICE_CONNECTED = "xiaozhi_device_connected"
EVENT_DEVICE_DISCONNECTED = "xiaozhi_device_disconnected"

# 数据存储键
DATA_WEBSOCKET = "websocket"
DATA_DEVICES = "devices"

# 二进制传感器
DEVICE_CLASS_CONNECTIVITY = "connectivity"

# 属性
ATTR_DEVICE_ID = "device_id"
ATTR_MESSAGE = "message"
ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_FALLBACK_URL = "fallback_url"

# 状态
CONNECTED = "connected"
DISCONNECTED = "disconnected"

# WebSocket message types
WS_MSG_TYPE_HELLO = "hello"
WS_MSG_TYPE_START_LISTEN = "start_listen"
WS_MSG_TYPE_STOP_LISTEN = "stop_listen"
WS_MSG_TYPE_WAKEWORD = "wakeword_detected"
WS_MSG_TYPE_RECOGNITION_RESULT = "recognition_result"
WS_MSG_TYPE_TTS_START = "tts_start"
WS_MSG_TYPE_TTS_END = "tts_end"
WS_MSG_TYPE_ABORT = "abort"
WS_MSG_TYPE_DEVICE_INFO = "device_info"
WS_MSG_TYPE_DEVICE_STATUS = "device_status"
WS_MSG_TYPE_EMOTION = "emotion"
WS_MSG_TYPE_ERROR = "error"

# Error codes
ERR_INVALID_MESSAGE = "invalid_message"
ERR_UNAUTHORIZED = "unauthorized"
ERR_SERVER_ERROR = "server_error" 