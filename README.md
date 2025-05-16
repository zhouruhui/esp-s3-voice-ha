# ESP32-S3-HA-Voice

基于ESP32-S3设备的Home Assistant语音助手项目，支持语音控制智能家居设备。本项目修改自[esphome/wake-word-voice-assistants](https://github.com/esphome/wake-word-voice-assistants)，并针对中文环境进行了优化。

## 功能特点

- 使用ESP32-S3 Box 3硬件平台
- 支持离线唤醒词检测
- 通过WebSocket与Home Assistant进行通信
- 支持语音指令控制智能家居设备
- 可视化界面显示语音助手状态
- 支持定时器功能

## 唤醒词修改

本项目将原始的"OK, Nabu"唤醒词修改为乐鑫官方支持的"嗨乐鑫"（Hi, 乐鑫）唤醒词。修改涉及以下两个方面：

1. 将唤醒词模型从`okay_nabu`更改为`wn9s_hilexin`
2. 添加ESP-SR外部组件以支持乐鑫官方唤醒词

```yaml
# 唤醒词模型配置
substitutions:
  # ...其他配置...
  micro_wake_word_model: wn9s_hilexin  # 使用乐鑫官方的"Hi,乐鑫"唤醒词模型

# 添加ESP-SR外部组件
external_components:
  - source: github://espressif/esp-sr
    components: [esp_sr]
    refresh: 0s
```

## 使用方法

1. 将配置文件烧录到ESP32-S3 Box 3设备上：
   ```bash
   esphome run esp32-s3-box-3.yaml
   ```

2. 设备将自动连接到Home Assistant并注册为语音助手

3. 使用"嗨乐鑫"唤醒设备，然后说出您的命令

## 设备状态说明

设备显示屏会显示不同的状态图标：

- **空闲状态**：显示待命图标，等待唤醒词
- **聆听状态**：显示聆听图标，正在接收您的语音命令  
- **思考状态**：显示思考图标，正在处理您的请求
- **回复状态**：显示回复图标，正在播放语音回复
- **错误状态**：显示错误图标，表示遇到问题
- **无连接状态**：显示未连接图标，表示未连接到Home Assistant

## 高级配置

设备支持两种唤醒词检测模式：

1. **设备端检测**（默认）：在ESP32-S3设备上进行唤醒词检测，节省带宽和保护隐私
2. **Home Assistant端检测**：在Home Assistant服务器上进行唤醒词检测

可以在Home Assistant界面中通过"Wake word engine location"选项切换这两种模式。

## 原项目来源

本项目基于ESPHome官方的语音助手项目修改：
[esphome/wake-word-voice-assistants](https://github.com/esphome/wake-word-voice-assistants)

唤醒词模型来自乐鑫官方的ESP-SR项目：
[espressif/esp-sr](https://github.com/espressif/esp-sr) 