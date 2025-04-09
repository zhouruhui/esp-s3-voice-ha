"""Config flow for XiaoZhi ESP32 integration."""
from __future__ import annotations

import logging
import voluptuous as vol

from homeassistant.components import assist_pipeline
from homeassistant.config_entries import ConfigFlow, OptionsFlow, ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN,
    CONF_WEBSOCKET_PORT,
    CONF_WEBSOCKET_PATH,
    CONF_PIPELINE_ID,
    CONF_FORWARD_URL,
    DEFAULT_WEBSOCKET_PORT,
    DEFAULT_WEBSOCKET_PATH,
)

_LOGGER = logging.getLogger(__name__)

async def validate_input(hass: HomeAssistant, data: dict) -> dict:
    """Validate the user input allows us to connect."""
    # 验证WebSocket端口是否可用
    port = data.get(CONF_WEBSOCKET_PORT, DEFAULT_WEBSOCKET_PORT)
    
    # 检查Pipeline是否存在
    pipeline_id = data.get(CONF_PIPELINE_ID)
    if pipeline_id:
        pipelines = await assist_pipeline.async_get_pipelines(hass)
        if not any(p.id == pipeline_id for p in pipelines):
            return {"base": "pipeline_not_found"}
    else:
        return {"base": "pipeline_required"}
    
    return {}

class XiaozhiConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for XiaoZhi ESP32."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, str] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors = {}

        # 获取可用的Pipelines
        pipelines = await assist_pipeline.async_get_pipelines(self.hass)
        pipeline_options = {p.id: f"{p.name}" for p in pipelines}

        if user_input is not None:
            errors = await validate_input(self.hass, user_input)
            if not errors:
                # 创建条目
                return self.async_create_entry(
                    title=user_input.get(CONF_NAME, "XiaoZhi ESP32 语音助手"),
                    data=user_input,
                )

        # 显示表单
        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default="XiaoZhi ESP32 语音助手"): str,
                vol.Required(CONF_PIPELINE_ID): vol.In(pipeline_options),
                vol.Required(
                    CONF_WEBSOCKET_PORT, default=DEFAULT_WEBSOCKET_PORT
                ): cv.port,
                vol.Required(
                    CONF_WEBSOCKET_PATH, default=DEFAULT_WEBSOCKET_PATH
                ): str,
                vol.Optional(CONF_FORWARD_URL): str,
            }
        )

        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
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
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, str] | None = None
    ) -> FlowResult:
        """Manage the options."""
        errors = {}
        options = self.config_entry.options.copy()
        
        # 获取配置
        data = self.config_entry.data.copy()

        if user_input is not None:
            # 更新选项
            options.update(user_input)
            
            # 验证数据
            errors = await validate_input(self.hass, {**data, **user_input})
            
            if not errors:
                return self.async_create_entry(title="", data=options)

        # 获取可用的Pipelines
        pipelines = await assist_pipeline.async_get_pipelines(self.hass)
        pipeline_options = {p.id: f"{p.name}" for p in pipelines}

        # 构建选项表单
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_PIPELINE_ID, 
                    default=data.get(CONF_PIPELINE_ID)
                ): vol.In(pipeline_options),
                vol.Optional(
                    CONF_WEBSOCKET_PATH, 
                    default=data.get(CONF_WEBSOCKET_PATH, DEFAULT_WEBSOCKET_PATH)
                ): str,
                vol.Optional(
                    CONF_FORWARD_URL,
                    default=data.get(CONF_FORWARD_URL, "")
                ): str,
            }
        )

        return self.async_show_form(
            step_id="init", data_schema=schema, errors=errors
        ) 