# XiaoZhi ESP32设备配置指南

本文档提供了将XiaoZhi ESP32设备配置为与Home Assistant集成的详细说明。

## 准备工作

在开始之前，请确保您已经：

1. 在Home Assistant中安装并配置了XiaoZhi集成
2. 获取了设备配置信息（使用`xiaozhi.get_device_config`服务）
3. 安装了ESP-IDF开发环境
4. 获取了XiaoZhi ESP32固件源码

## 配置步骤

### 1. 修改设备配置文件

在XiaoZhi ESP32固件项目中，找到`main/config.h`或类似的配置文件，修改以下参数：

```c
// 连接设置
#define XIAOZHI_DEVICE_ID      "从Home Assistant获取的设备ID"
#define XIAOZHI_WS_URL         "从Home Assistant获取的WebSocket URL"
#define XIAOZHI_RECONNECT_MS   5000
#define XIAOZHI_PING_MS        30000

// 通信类型设置 (0: MQTT, 1: WebSocket)
#define XIAOZHI_COMM_TYPE      1
```

### 2. 修改设备唤醒词（可选）

如果需要更改设备的唤醒词，请修改相应的配置：

```c
// 唤醒词设置
#define XIAOZHI_WAKEWORD       "xiaozhi"  // 默认为"小智小智"
```

### 3. 编译固件

在项目根目录执行以下命令进行编译：

```bash
# 配置项目
idf.py menuconfig

# 编译项目
idf.py build
```

在menuconfig中，确保以下设置正确：

- 组件设置 -> XiaoZhi设置
  - 选择通信类型 -> WebSocket
  - 输入WebSocket URL
  - 输入设备ID
  - 设置重连间隔和心跳间隔

### 4. 烧录固件

连接ESP32设备到电脑，并执行烧录命令：

```bash
idf.py -p [COM端口] flash
```

其中`[COM端口]`替换为您系统中ESP32设备的实际串口，例如：
- Windows: `COM3`
- Linux: `/dev/ttyUSB0`
- macOS: `/dev/cu.usbserial-0001`

### 5. 监控设备日志

烧录完成后，可以通过串口监视器查看设备日志：

```bash
idf.py -p [COM端口] monitor
```

## 故障排除

### 连接问题

如果设备无法连接到Home Assistant，请检查：

1. WebSocket URL是否正确（包括`ws://`或`wss://`前缀）
2. Home Assistant是否可以从ESP32设备网络访问
3. 防火墙设置是否允许WebSocket连接
4. 设备ID是否唯一

在ESP32的日志中，寻找类似以下的信息来诊断问题：

```
I (5432) XIAOZHI_WS: 正在连接到WebSocket服务器: ws://your-homeassistant:8554/xiaozhi
E (10432) XIAOZHI_WS: WebSocket连接失败，错误: -1
I (15432) XIAOZHI_WS: 尝试重新连接...
```

### 音频问题

如果设备能连接但无法正常处理语音，请检查：

1. 麦克风是否正确连接和配置
2. 音频采样率和格式是否与Home Assistant语音助手Pipeline兼容
3. ESP32是否有足够的内存处理音频流

## 高级配置

### SSL/TLS支持

对于使用`wss://`加密连接，需要在项目中启用SSL支持并添加证书：

```c
// SSL配置（仅在使用wss://时需要）
#define XIAOZHI_USE_SSL        1
// 对于自签名证书，需要提供证书信息
#define XIAOZHI_ROOT_CERT      "..."  // 根证书
```

### 音频参数调整

根据您的ESP32型号和麦克风配置，可能需要调整音频参数：

```c
// 音频设置
#define XIAOZHI_SAMPLE_RATE    16000
#define XIAOZHI_BIT_WIDTH      16
#define XIAOZHI_CHANNELS       1
```

## 支持与反馈

如果在配置过程中遇到问题，请参考：

- [项目GitHub页面](https://github.com/zhouruhui/xiaozhi-ha)提交Issue
- Home Assistant社区论坛寻求帮助
- 查看ESP32设备日志以获取详细错误信息 