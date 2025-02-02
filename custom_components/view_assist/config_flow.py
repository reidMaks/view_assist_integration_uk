"""Config flow handler."""

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import DOMAIN

BASE_SCHEMA = {
    vol.Required("name"): str,
    vol.Required("mic_device"): selector.EntitySelector(
        selector.EntitySelectorConfig(domain=["sensor", "assist_satellite"])
    ),
    vol.Required("mediaplayer_device"): selector.EntitySelector(
        selector.EntitySelectorConfig(domain="media_player")
    ),
    vol.Required("musicplayer_device"): selector.EntitySelector(
        selector.EntitySelectorConfig(domain="media_player")
    ),
}

DISPLAY_SCHEMA = {
    vol.Required("display_device"): selector.EntitySelector(
        selector.EntitySelectorConfig(domain="sensor")
    ),
    vol.Required("browser_id"): str,
}


class ViewAssistConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for View Assist."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler.

        Remove this method and the ExampleOptionsFlowHandler class
        if you do not want any options for your integration.
        """
        return ViewAssistOptionsFlowHandler(config_entry)

    def __init__(self) -> None:
        """Initialise."""
        self.type = None

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if user_input is not None:
            self.type = user_input["type"]
            return await self.async_step_options()

        # Show the initial form to select the type with descriptive text
        return self.async_show_form(
            step_id="user",
            last_step=False,
            data_schema=vol.Schema(
                {
                    vol.Required("type", default="view_audio"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                {
                                    "value": "view_audio",
                                    "label": "View Assist device with display",
                                },
                                {
                                    "value": "audio_only",
                                    "label": "View Assist device with no display",
                                },
                            ],
                            mode="dropdown",
                        )
                    ),
                }
            ),
        )

    async def async_step_options(self, user_input=None):
        """Handle the options step."""
        if user_input is not None:
            # Include the type in the data to save in the config entry
            user_input["type"] = self.type
            return self.async_create_entry(
                title=user_input.get("name", "View Assist"), data=user_input
            )

        # Define the schema based on the selected type
        if self.type == "view_audio":
            data_schema = vol.Schema({**BASE_SCHEMA, **DISPLAY_SCHEMA})
        else:  # audio_only
            data_schema = vol.Schema(BASE_SCHEMA)

        # Show the form for the selected type
        return self.async_show_form(step_id="options", data_schema=data_schema)


class ViewAssistOptionsFlowHandler(OptionsFlow):
    """Handles the options flow.

    Here we use an initial menu to select different options forms,
    and show how to use api data to populate a selector.
    """

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry
        self.options = dict(config_entry.options)
        self.type = self.config_entry.data["type"]

    async def async_step_init(self, user_input=None):
        """Handle options flow."""

        # Display an options menu if display device
        # Display reconfigure form if audio onlu

        # Also need to be in strings.json and translation files.

        if self.type == "view_audio":
            return self.async_show_menu(
                step_id="init",
                menu_options=["main_config", "display_options"],
            )

        return await self.async_step_main_config()

    async def async_step_main_config(self, user_input=None):
        """Handle main config flow."""

        if user_input is not None:
            # This is just updating the core config so update config_entry.data
            user_input["type"] = self.type
            self.hass.config_entries.async_update_entry(
                self.config_entry, data=user_input
            )
            return self.async_create_entry(data=None)
        # Define the schema based on the selected type
        BASE_OPTIONS = {
            vol.Required("name", default=self.config_entry.data["name"]): str,
            vol.Required(
                "mic_device", default=self.config_entry.data["mic_device"]
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["sensor", "assist_satellite"])
            ),
            vol.Required(
                "mediaplayer_device",
                default=self.config_entry.data["mediaplayer_device"],
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="media_player")
            ),
            vol.Required(
                "musicplayer_device",
                default=self.config_entry.data["musicplayer_device"],
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="media_player")
            ),
        }

        if self.type == "view_audio":
            data_schema = vol.Schema(
                {
                    **BASE_OPTIONS,
                    vol.Required(
                        "display_device",
                        default=self.config_entry.data["display_device"],
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="sensor")
                    ),
                    vol.Required(
                        "browser_id", default=self.config_entry.data["browser_id"]
                    ): str,
                }
            )
        else:  # audio_only
            data_schema = vol.Schema(BASE_OPTIONS)

        # Show the form for the selected type
        return self.async_show_form(step_id="main_config", data_schema=data_schema)

    async def async_step_display_options(self, user_input=None):
        """Handle display options flow."""
        if user_input is not None:
            # This is just updating the core config so update config_entry.data
            return self.async_create_entry(data=user_input)

        data_schema = vol.Schema(
            {
                vol.Optional(
                    "display_op1",
                    default=self.config_entry.options.get("display_op1", "abc"),
                ): str,
                vol.Optional(
                    "display_op2",
                    default=self.config_entry.options.get("display_op2", "def"),
                ): str,
                vol.Optional(
                    "display_op3",
                    default=self.config_entry.options.get("display_op3", "ghi"),
                ): str,
                vol.Optional(
                    "display_op4",
                    default=self.config_entry.options.get("display_op4", "klm"),
                ): str,
            }
        )

        # Show the form for the selected type
        return self.async_show_form(step_id="display_options", data_schema=data_schema)
