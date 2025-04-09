"""Constants for the XiaoZhi ESP32 integration."""
from homeassistant.const import Platform

DOMAIN = "xiaozhi"
PLATFORMS = [Platform.BINARY_SENSOR]

# 配置项
CONF_WEBSOCKET_PORT = "websocket_port"
CONF_WEBSOCKET_PATH = "websocket_path"
CONF_PIPELINE_ID = "pipeline_id"
CONF_FORWARD_URL = "forward_url"

# 默认值
DEFAULT_WEBSOCKET_PORT = 8554
DEFAULT_WEBSOCKET_PATH = "/xiaozhi"

# 服务
SERVICE_SEND_TTS = "send_tts"
SERVICE_GET_DEVICE_CONFIG = "get_device_config"

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