"""Handles entity listeners."""

import logging
from typing import Literal

from hassil.recognize import RecognizeResult

from homeassistant.components.conversation import (
    DOMAIN as CONVERSATION_DOMAIN,
    ConversationEntity,
    ConversationInput,
    ConversationResult,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class CustomSentences:
    """Class to manage custom senstence actions."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialise."""
        self.hass = hass
        self.config_entry = config_entry

        sentences = ["[whats] the weather", "[whats] the weather {when}"]

        config_entry.async_on_unload(
            hass.data[f"{CONVERSATION_DOMAIN}_default_entity"].register_trigger(
                sentences, self.call_action
            )
        )

    async def call_action(
        self, user_input: ConversationInput, result: RecognizeResult
    ) -> str | None:
        """Call action with right context."""

        # Add slot values as extra trigger data
        details = {
            entity_name: {
                "name": entity_name,
                "text": entity.text.strip(),  # remove whitespace
                "value": (
                    entity.value.strip()
                    if isinstance(entity.value, str)
                    else entity.value
                ),
            }
            for entity_name, entity in result.entities.items()
        }

        _LOGGER.info(
            "SENSTENCE TRIGGER %s",
            {
                "platform": CONVERSATION_DOMAIN,
                "sentence": user_input.text,
                "details": details,
                "slots": {  # direct access to values
                    entity_name: entity["value"]
                    for entity_name, entity in details.items()
                },
                "device_id": user_input.device_id,
                "user_input": user_input.as_dict(),
            },
        )
        if self.config_entry.data["type"] == "view_audio":
            await self.hass.services.async_call(
                "browser_mod",
                "navigate",
                {
                    "browser_id": "b7141f1b-c14cba93",
                    "path": "/dashboard-view_assist/weather",
                },
            )

        return "Showing weather view"
