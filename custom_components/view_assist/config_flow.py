import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector
from .const import DOMAIN

class ViewAssistConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for View Assist."""

    VERSION = 1

    def __init__(self):
        self.type = None

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if user_input is not None:
            self.type = user_input["type"]
            return await self.async_step_options()

        # Show the initial form to select the type with descriptive text
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("type", default="view_audio"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                {"value": "view_audio", "label": "View Assist device with display"},
                                {"value": "audio_only", "label": "View Assist device with no display"},
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
            return self.async_create_entry(title=user_input.get("name", "View Assist"), data=user_input)

        # Define the schema based on the selected type
        if self.type == "view_audio":
            data_schema = vol.Schema(
                {
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
                    vol.Required("display_device"): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="sensor")
                    ),
                    vol.Required("browser_id"): str,
                }
            )
        else:  # audio_only
            data_schema = vol.Schema(
                {
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
            )

        # Show the form for the selected type
        return self.async_show_form(step_id="options", data_schema=data_schema)