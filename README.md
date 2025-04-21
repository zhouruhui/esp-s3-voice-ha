# XiaoZhi ESP32 语音助手 - Home Assistant集成

这是一个Home Assistant的自定义集成组件，用于将XiaoZhi ESP32语音终端设备与Home Assistant连接，提供完整的语音交互和智能控制功能。

## 功能特点

* 通过WebSocket协议直接连接XiaoZhi ESP32设备
* 完全整合Home Assistant的语音助手框架(Assist Pipeline)
* 双向音频流支持：设备发送语音到HA，HA回传TTS音频到设备
* 支持语音识别、对话处理和语音合成
* 直接调用Home Assistant的语音助手功能，无需中间代理
* 利用HA的EXPOSE功能控制可被语音助手访问的设备
* 提供设备状态监控和TTS消息发送功能
* 自动生成ESP32设备烧录配置信息

## 安装方法

### 使用HACS安装（推荐）

1. 确保已安装HACS
2. 在HACS中添加自定义仓库：  
   * 仓库URL: `https://github.com/zhouruhui/xiaozhi-ha`  
   * 类别: `集成`
3. 在HACS中安装"XiaoZhi ESP32 语音助手"集成
4. 重启Home Assistant

### 手动安装

1. 下载或克隆此仓库
2. 将`custom_components/xiaozhi`目录复制到您的Home Assistant配置目录下的`custom_components`目录中
3. 重启Home Assistant

## 配置步骤

### 1\. 创建语音助手Pipeline

在配置XiaoZhi集成之前，您需要首先创建一个语音助手Pipeline：

1. 在Home Assistant中转到`设置` \-> `语音助手`
2. 点击"创建语音助手"按钮
3. 配置您希望使用的语音识别(STT)、对话(LLM)和语音合成(TTS)服务
4. 保存Pipeline配置

### 2\. 暴露需要语音控制的设备

为了让语音助手能够控制您的设备，需要将设备暴露给语音助手：

1. 在Home Assistant中转到`设置` \-> `语音助手` \-> `管理暴露的实体`
2. 选择您希望能通过语音控制的设备和实体
3. 保存设置

### 3\. 添加XiaoZhi集成

1. 在Home Assistant中转到`设置` \-> `设备与服务` \-> `集成`
2. 点击右下角的"添加集成"按钮
3. 搜索"XiaoZhi"
4. 填写集成配置表单：  
   * 名称：您想给此集成的名称  
   * WebSocket服务端口：用于WebSocket服务的端口（默认：8554）  
   * WebSocket路径：WebSocket服务的URL路径（默认：/ws/xiaozhi）  
   * 语音助手Pipeline：选择您之前创建的Pipeline

### 4\. 配置ESP32设备

1. 在Home Assistant中转到`开发者工具` \-> `服务`
2. 选择`xiaozhi.get_device_config`服务
3. 输入参数：  
   * 配置条目ID：您刚才添加的集成的ID（查看集成详情可找到）  
   * 设备ID（可选）：自定义的设备ID  
   * 回退URL（可选）：如果无法获取Home Assistant外部URL，提供备选URL
4. 调用服务并获取配置信息
5. 按照生成的指南配置您的XiaoZhi ESP32设备

## 使用方法

### 语音控制

连接后，您可以通过XiaoZhi ESP32设备使用语音命令控制Home Assistant：

1. 对设备说出唤醒词（默认为"小智小智"）
2. 语音输入命令，如"打开客厅灯"、"把卧室温度设置为26度"等
3. 设备将通过语音助手Pipeline处理指令并执行相应动作
4. 设备会播放HA的语音助手回复

### 发送TTS消息

您可以通过Home Assistant向XiaoZhi设备发送语音消息：

1. 在`开发者工具` \-> `服务`中选择`xiaozhi.send_tts`服务
2. 输入参数：  
   * 设备ID：要发送消息的设备ID  
   * 消息内容：要播放的文本消息
3. 调用服务，设备将播放TTS消息

### 自动化示例

```yaml
# 当有人到家时，通过XiaoZhi设备播放欢迎消息
automation:
  - alias: "有人到家欢迎提醒"
    trigger:
      - platform: state
        entity_id: person.your_name
        from: "not_home"
        to: "home"
    action:
      - service: xiaozhi.send_tts
        data:
          device_id: "xiaozhi_device1"
          message: "欢迎回家！当前室内温度24度，天气晴朗。"

# 当检测到异常活动时，通过语音通知
automation:
  - alias: "安全警报通知"
    trigger:
      - platform: state
        entity_id: binary_sensor.motion_sensor
        to: "on"
    condition:
      - condition: state
        entity_id: alarm_control_panel.home_alarm
        state: "armed_away"
    action:
      - service: xiaozhi.send_tts
        data:
          device_id: "xiaozhi_device1"
          message: "警告：检测到活动，已通知安防系统。"
```

## 技术架构

XiaoZhi集成使用WebSocket协议连接ESP32设备和Home Assistant，主要组件包括：

1. **WebSocket服务**：处理与ESP32设备的双向通信
2. **Assist Pipeline集成**：处理语音识别、对话和TTS
3. **音频处理**：支持多种音频格式，包括Opus编码
4. **连接状态监控**：提供设备连接状态的实时反馈
5. **配置生成**：自动生成ESP32设备配置

### 通信流程

1. ESP32设备与HA建立WebSocket连接
2. 设备检测唤醒词并开始录音
3. 设备将音频流发送到HA
4. HA的语音助手处理音频并执行命令
5. HA将响应和TTS音频发送回设备
6. 设备播放语音回复

## 故障排除

如果您遇到问题，请尝试以下步骤：

1. 检查设备连接状态实体，确认设备是否成功连接
2. 查看Home Assistant日志中的`xiaozhi`相关日志
3. 确保ESP32设备配置正确（WebSocket URL、设备ID等）
4. 验证您的语音助手Pipeline是否正常工作
5. 确认已正确暴露需要控制的设备到语音助手

## 支持与贡献

* 如有问题，请在GitHub仓库中提出issue
* 欢迎提交Pull Request改进此集成
* 项目地址：<https://github.com/zhouruhui/xiaozhi-ha>

## 许可证

MIT 