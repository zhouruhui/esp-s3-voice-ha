# XiaoZhi ESP32固件配置指南

本文档提供有关如何配置XiaoZhi ESP32固件以连接到Home Assistant的详细指南。

## 准备工作

在开始之前，请确保：

1. 已在Home Assistant中安装并配置了XiaoZhi集成
2. 已调用`xiaozhi.get_device_config`服务获取配置信息
3. 已安装ESP-IDF开发环境（推荐版本：v4.4或更高）
4. 已克隆或下载XiaoZhi ESP32项目源码

## 配置步骤

### 1. 使用menuconfig配置WebSocket连接

在XiaoZhi ESP32项目目录下运行：

```bash
idf.py menuconfig
```

导航到"组件配置" → "XiaoZhi配置"，设置以下参数：

- **连接类型**：选择"WebSocket"
- **WebSocket服务器URL**：输入从Home Assistant获取的WebSocket URL
- **设备ID**：输入从Home Assistant获取的设备ID
- **客户端ID**：输入从Home Assistant获取的客户端ID
- **协议版本**：保持默认值"1"

### 2. 配置网络连接

在menuconfig中导航到"组件配置" → "WiFi连接配置"，设置：

- **WiFi SSID**：您的WiFi网络名称
- **WiFi密码**：您的WiFi密码

### 3. 编译和烧录固件

```bash
idf.py build
idf.py -p [端口] flash
```

将`[端口]`替换为您的ESP32设备的串口（例如`COM3`或`/dev/ttyUSB0`）。

### 4. 监控设备日志

```bash
idf.py -p [端口] monitor
```

## ESP32代码修改示例

如果您需要修改ESP32代码以适应Home Assistant的XiaoZhi集成，以下是关键部分的示例：

### WebSocket客户端初始化

```c
esp_websocket_client_config_t websocket_cfg = {
    .uri = CONFIG_XIAOZHI_WEBSOCKET_URL,
    .headers = {
        // 设置WebSocket连接头信息
        "Device-Id: " CONFIG_XIAOZHI_DEVICE_ID "\r\n"
        "Client-Id: " CONFIG_XIAOZHI_CLIENT_ID "\r\n"
        "Protocol-Version: " CONFIG_XIAOZHI_PROTOCOL_VERSION "\r\n"
    },
};

// 初始化WebSocket客户端
esp_websocket_client_handle_t client = esp_websocket_client_init(&websocket_cfg);
```

### 处理WebSocket消息

```c
static void websocket_event_handler(void *handler_args, esp_event_base_t base, int32_t event_id, void *event_data)
{
    esp_websocket_event_data_t *data = (esp_websocket_event_data_t *)event_data;
    esp_websocket_client_handle_t client = (esp_websocket_client_handle_t)handler_args;

    switch (event_id) {
    case WEBSOCKET_EVENT_CONNECTED:
        ESP_LOGI(TAG, "WEBSOCKET_EVENT_CONNECTED");
        // 发送hello消息
        char hello_msg[100];
        snprintf(hello_msg, sizeof(hello_msg), 
                 "{\"type\":\"hello\",\"version\":\"%s\",\"device_id\":\"%s\"}",
                 CONFIG_XIAOZHI_PROTOCOL_VERSION,
                 CONFIG_XIAOZHI_DEVICE_ID);
        esp_websocket_client_send_text(client, hello_msg, strlen(hello_msg), portMAX_DELAY);
        break;
    case WEBSOCKET_EVENT_DISCONNECTED:
        ESP_LOGI(TAG, "WEBSOCKET_EVENT_DISCONNECTED");
        break;
    case WEBSOCKET_EVENT_DATA:
        if (data->op_code == WS_TRANSPORT_OPCODES_TEXT) {
            // 处理文本消息
            ESP_LOGI(TAG, "Received text data: %.*s", data->data_len, (char *)data->data_ptr);
            // 解析JSON并处理不同类型的消息
            process_text_message((char *)data->data_ptr, data->data_len);
        } else if (data->op_code == WS_TRANSPORT_OPCODES_BINARY) {
            // 处理二进制数据（如TTS音频）
            ESP_LOGI(TAG, "Received binary data, len=%d", data->data_len);
            // 播放音频数据
            play_audio_data(data->data_ptr, data->data_len);
        }
        break;
    case WEBSOCKET_EVENT_ERROR:
        ESP_LOGI(TAG, "WEBSOCKET_EVENT_ERROR");
        break;
    }
}
```

### 发送音频数据

```c
// 发送开始监听消息
void start_listening(esp_websocket_client_handle_t client)
{
    char msg[100];
    snprintf(msg, sizeof(msg), 
             "{\"type\":\"start_listen\",\"time\":%lld}",
             get_timestamp());
    esp_websocket_client_send_text(client, msg, strlen(msg), portMAX_DELAY);
}

// 发送音频数据
void send_audio_frame(esp_websocket_client_handle_t client, const uint8_t *audio_data, size_t len)
{
    esp_websocket_client_send_binary(client, audio_data, len, portMAX_DELAY);
}

// 停止监听
void stop_listening(esp_websocket_client_handle_t client)
{
    char msg[100];
    snprintf(msg, sizeof(msg), 
             "{\"type\":\"stop_listen\",\"time\":%lld}",
             get_timestamp());
    esp_websocket_client_send_text(client, msg, strlen(msg), portMAX_DELAY);
}
```

## 通信流程

1. **连接建立**：
   - ESP32连接到WebSocket服务器
   - 发送hello消息
   - 接收服务器的hello响应

2. **语音识别**：
   - 检测到唤醒词后发送`wakeword_detected`消息
   - 发送`start_listen`消息
   - 发送音频数据（二进制）
   - 发送`stop_listen`消息
   - 接收`recognition_result`消息

3. **语音合成**：
   - 接收`tts_start`消息
   - 接收TTS音频数据（二进制）
   - 接收`tts_end`消息
   - 播放收到的音频

## 故障排除

### 无法连接到WebSocket服务器

- 确认WiFi连接正常
- 验证WebSocket URL格式正确（ws://或wss://）
- 检查Home Assistant是否可以从外部访问
- 确认端口是否开放且未被防火墙阻止

### 连接断开

- 增加WebSocket保持连接超时设置
- 确保网络连接稳定
- 实现自动重连机制

### 音频传输问题

- 确认音频格式正确（OPUS编码，16000Hz采样率）
- 检查音频帧大小（建议帧长60ms）
- 验证音频数据是否完整传输

## 进阶配置

### Kconfig配置选项

在XiaoZhi ESP32项目的`Kconfig.projbuild`文件中添加以下配置选项：

```
menu "XiaoZhi配置"
    choice XIAOZHI_CONNECTION_TYPE
        prompt "连接类型"
        default XIAOZHI_CONNECTION_WEBSOCKET
        help
            选择XiaoZhi与服务器的连接类型。
        
        config XIAOZHI_CONNECTION_WEBSOCKET
            bool "WebSocket"
        
        config XIAOZHI_CONNECTION_MQTT
            bool "MQTT"
    endchoice
    
    config XIAOZHI_WEBSOCKET_URL
        string "WebSocket服务器URL"
        depends on XIAOZHI_CONNECTION_WEBSOCKET
        default "ws://your-homeassistant:8554/xiaozhi_ws"
        help
            XiaoZhi集成WebSocket服务器的URL。
    
    config XIAOZHI_DEVICE_ID
        string "设备ID"
        default "xiaozhi_esp32"
        help
            设备唯一标识符。
    
    config XIAOZHI_CLIENT_ID
        string "客户端ID"
        default ""
        help
            客户端唯一标识符。
    
    config XIAOZHI_PROTOCOL_VERSION
        string "协议版本"
        default "1"
        help
            XiaoZhi通信协议版本。
endmenu
```

希望这份配置指南对您连接XiaoZhi ESP32设备到Home Assistant有所帮助！如有任何问题，请参考主README文档或提交issue。 