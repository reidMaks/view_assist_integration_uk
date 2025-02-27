"""View Assist websocket handlers."""

import voluptuous as vol

from homeassistant.components.websocket_api import (
    ActiveConnection,
    async_register_command,
    async_response,
    websocket_command,
)
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .helpers import get_entity_id_by_browser_id, get_mimic_entity_id


async def async_register_websockets(hass: HomeAssistant):
    """Register websocket functions."""

    # Get sensor entity by browser id
    @websocket_command(
        {
            vol.Required("type"): f"{DOMAIN}/get_entity_id",
            vol.Required("browser_id"): str,
        }
    )
    @async_response
    async def websocket_get_entity_by_browser_id(
        hass: HomeAssistant, connection: ActiveConnection, msg: dict
    ) -> None:
        """Get entity id by browser id."""
        output = get_entity_id_by_browser_id(hass, msg["browser_id"])
        if not output:
            output = get_mimic_entity_id(hass)

        connection.send_result(msg["id"], output)

    async_register_command(hass, websocket_get_entity_by_browser_id)
