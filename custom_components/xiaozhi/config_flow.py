"""Config flow for XiaoZhi ESP32 integration."""
from __future__ import annotations

import logging
import socket
import voluptuous as vol
from typing import Any, Dict, Optional

from homeassistant.components import assist_pipeline
from homeassistant.config_entries import ConfigFlow, OptionsFlow, ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    DOMAIN,
    CONF_WEBSOCKET_PORT,
    CONF_WEBSOCKET_PATH,
    CONF_PIPELINE_ID,
    CONF_FORWARD_URL,
    DEFAULT_WEBSOCKET_PORT,
    DEFAULT_WEBSOCKET_PATH,
    CONF_PROXY_MODE,
)

_LOGGER = logging.getLogger(__name__)

def is_port_in_use(port: int) -> bool:
    """Check if port is in use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("0.0.0.0", port))
            return False
        except OSError:
            return True

async def validate_input(hass: HomeAssistant, data: dict) -> dict:
    """Validate the user input allows us to connect."""
    errors = {}
    
    try:
        # 验证WebSocket端口是否可用
        port = data.get(CONF_WEBSOCKET_PORT, DEFAULT_WEBSOCKET_PORT)
        if is_port_in_use(port):
            errors["base"] = "port_unavailable"
            return errors

        # 检查是否是代理模式
        proxy_mode = data.get(CONF_PROXY_MODE, False)
        
        # 在代理模式下，不要检查Pipeline
        if not proxy_mode:
            # 检查Pipeline是否存在
            pipeline_id = data.get(CONF_PIPELINE_ID)
            if not pipeline_id:
                # 在非代理模式下，仍然需要Pipeline
                errors["base"] = "pipeline_required"
                return errors
            
            try:
                pipelines = await assist_pipeline.async_get_pipelines(hass)
                if not any(p.id == pipeline_id for p in pipelines):
                    errors["base"] = "pipeline_not_found"
            except Exception as ex:
                _LOGGER.error("获取Pipeline失败: %s", ex)
                errors["base"] = "unknown"
        else:
            # 代理模式下，检查转发URL
            forward_url = data.get(CONF_FORWARD_URL)
            if not forward_url:
                errors["base"] = "forward_url_required"
                return errors
                
    except Exception as ex:
        _LOGGER.error("验证输入时出错: %s", ex)
        errors["base"] = "unknown"
        
    return errors

async def _async_get_pipelines(hass: HomeAssistant) -> Dict[str, str]:
    """获取可用的语音助手Pipeline。"""
    try:
        # 不使用await，直接获取列表
        pipeline_list = assist_pipeline.async_get_pipelines(hass)
        
        if not pipeline_list:
            _LOGGER.warning("未找到语音助手Pipeline")
            # 添加一个默认选项，避免UI为空
            return {"default": "默认Pipeline"}
        
        # 转换为字典格式
        pipelines = {pipeline.id: pipeline.name for pipeline in pipeline_list}
        return pipelines
    except Exception as e:
        _LOGGER.error("获取语音助手Pipeline时出错: %s", e)
        _LOGGER.exception("详细错误:")
        # 返回默认值避免UI出错
        return {"default": "默认Pipeline"}

class XiaozhiConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for XiaoZhi ESP32."""

    VERSION = 1

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors = {}
        
        # 获取可用的Pipeline
        pipelines = await _async_get_pipelines(self.hass)
        
        if not pipelines:
            errors["base"] = "no_pipelines"

        if user_input is not None:
            try:
                proxy_mode = user_input.get(CONF_PROXY_MODE, False)
                
                # 检查配置的有效性
                if not proxy_mode and not user_input.get(CONF_PIPELINE_ID):
                    errors[CONF_PIPELINE_ID] = "missing_pipeline_id"
                elif proxy_mode and not user_input.get(CONF_FORWARD_URL):
                    errors[CONF_FORWARD_URL] = "missing_forward_url"
                else:
                    # 创建配置条目
                    return self.async_create_entry(
                        title="XiaoZhi ESP32 语音助手",
                        data=user_input,
                    )
                    
            except Exception as exc:
                _LOGGER.error("配置错误: %s", exc)
                errors["base"] = "unknown"

        # 准备表单
        schema = vol.Schema({
            vol.Required(CONF_NAME, default="XiaoZhi ESP32 语音助手"): str,
            vol.Required(
                CONF_WEBSOCKET_PORT, default=DEFAULT_WEBSOCKET_PORT
            ): cv.port,
            vol.Required(
                CONF_WEBSOCKET_PATH, 
                default=user_input.get(CONF_WEBSOCKET_PATH, DEFAULT_WEBSOCKET_PATH) if user_input else DEFAULT_WEBSOCKET_PATH
            ): TextSelector(
                TextSelectorConfig(type=TextSelectorType.TEXT)
            ),
            vol.Required(
                CONF_PROXY_MODE, 
                default=user_input.get(CONF_PROXY_MODE, False) if user_input else False
            ): BooleanSelector(),
        })
        
        # 如果代理模式为False（即本地处理模式），添加Pipeline选项
        if not user_input or not user_input.get(CONF_PROXY_MODE, False):
            schema = schema.extend({
                vol.Optional(
                    CONF_PIPELINE_ID, 
                    description={"suggested_value": user_input.get(CONF_PIPELINE_ID) if user_input else None}
                ): vol.In(pipelines)
            })
        
        # 如果代理模式为True，添加转发URL选项
        if user_input and user_input.get(CONF_PROXY_MODE, False):
            schema = schema.extend({
                vol.Optional(
                    CONF_FORWARD_URL, 
                    description={"suggested_value": user_input.get(CONF_FORWARD_URL) if user_input else None}
                ): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.URL)
                )
            })

        return self.async_show_form(
            step_id="user", 
            data_schema=schema, 
            errors=errors,
        )
    
    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow for this handler."""
        return XiaozhiOptionsFlow(config_entry)


class XiaozhiOptionsFlow(OptionsFlow):
    """Handle options for XiaoZhi ESP32."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Manage the options."""
        errors = {}
        options = self._config_entry.options.copy()
        data = self._config_entry.data.copy()

        pipelines = await _async_get_pipelines(self.hass)
        
        if user_input is not None:
            try:
                proxy_mode = user_input.get(CONF_PROXY_MODE, False)
                
                # 检查配置的有效性
                if not proxy_mode and not user_input.get(CONF_PIPELINE_ID):
                    errors[CONF_PIPELINE_ID] = "missing_pipeline_id"
                elif proxy_mode and not user_input.get(CONF_FORWARD_URL):
                    errors[CONF_FORWARD_URL] = "missing_forward_url"
                else:
                    # 更新选项
                    return self.async_create_entry(title="", data=user_input)
                    
            except Exception as exc:
                _LOGGER.error("配置错误: %s", exc)
                errors["base"] = "unknown"

        # 准备表单
        all_data = {**data, **options}
        
        schema = vol.Schema({
            vol.Required(
                CONF_WEBSOCKET_PATH, 
                default=all_data.get(CONF_WEBSOCKET_PATH, DEFAULT_WEBSOCKET_PATH)
            ): TextSelector(
                TextSelectorConfig(type=TextSelectorType.TEXT)
            ),
            vol.Required(
                CONF_PROXY_MODE, 
                default=all_data.get(CONF_PROXY_MODE, False)
            ): BooleanSelector(),
        })
        
        # 如果代理模式为False（即本地处理模式），添加Pipeline选项
        if not all_data.get(CONF_PROXY_MODE, False):
            schema = schema.extend({
                vol.Optional(
                    CONF_PIPELINE_ID, 
                    description={"suggested_value": all_data.get(CONF_PIPELINE_ID)}
                ): vol.In(pipelines)
            })
        
        # 如果代理模式为True，添加转发URL选项
        if all_data.get(CONF_PROXY_MODE, False):
            schema = schema.extend({
                vol.Optional(
                    CONF_FORWARD_URL, 
                    description={"suggested_value": all_data.get(CONF_FORWARD_URL)}
                ): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.URL)
                )
            })

        return self.async_show_form(
            step_id="init", 
            data_schema=schema, 
            errors=errors,
        ) 