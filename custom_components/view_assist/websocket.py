"""View Assist websocket handlers."""

import datetime as dt
import logging
import time

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

_LOGGER = logging.getLogger(__name__)


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

    # Get server datetime
    @websocket_command(
        {
            vol.Required("type"): f"{DOMAIN}/get_server_time_delta",
            vol.Required("epoch"): int,
        }
    )
    @async_response
    async def websocket_get_server_time(
        hass: HomeAssistant, connection: ActiveConnection, msg: dict
    ) -> None:
        """Get entity id by browser id."""

        delta = round(time.time() * 1000) - msg["epoch"]
        connection.send_result(msg["id"], delta)

    async_register_command(hass, websocket_get_entity_by_browser_id)
    async_register_command(hass, websocket_get_server_time)
