# ESP32-S3-HA-Voice

基于ESP32-S3设备的Home Assistant语音助手项目，支持语音控制智能家居设备。本项目修改自[esphome/wake-word-voice-assistants](https://github.com/esphome/wake-word-voice-assistants)，并针对中文环境进行了优化。

经过多次尝试，在esphome micro wake word这个框架下无法支持中文唤醒词和中文显示问题，放弃这个方向，准备采用乐鑫官方 https://github.com/espressif/esp-sr 框架重新开发。
