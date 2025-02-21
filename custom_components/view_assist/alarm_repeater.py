"""Handlers alarm repeater."""

import asyncio
from dataclasses import dataclass
import logging

from config.custom_components.view_assist.const import BROWSERMOD_DOMAIN
from homeassistant.components.media_player import MediaPlayerEntity, MediaType
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity, entity_registry as er
from homeassistant.helpers.entity_component import DATA_INSTANCES, EntityComponent
from homeassistant.helpers.network import get_url

_LOGGER = logging.getLogger(__name__)


@dataclass
class PlayingMedia:
    """Class to hold paused media."""

    media_content_id: str
    media_type: str = "music"
    media_position: float = 0
    volume: int = 0


class VAAlarmRepeater:
    """Class to handle announcing on media player with resume."""

    def __init__(self, hass: HomeAssistant, config: ConfigEntry) -> None:
        """Initialise."""
        self.hass = hass
        self.config = config

        self.alarm_tasks: dict[str, asyncio.Task] = {}

    def _get_entity_from_entity_id(self, entity_id: str):
        """Get entity object from entity_id."""
        domain = entity_id.partition(".")[0]
        entity_comp: EntityComponent[entity.Entity] | None
        entity_comp = self.hass.data.get(DATA_INSTANCES, {}).get(domain)
        if entity_comp:
            return entity_comp.get_entity(entity_id)
        return None

    def _get_integration_domain(self, entity_id: str) -> str | None:
        """Get integration of entity id."""

        entity_registry = er.async_get(self.hass)
        _entity = entity_registry.async_get(entity_id)
        if _entity:
            return _entity.platform
        return None

    def get_currently_playing_media(
        self, media_entity: MediaPlayerEntity
    ) -> PlayingMedia | None:
        """Try and get currently playing media."""

        # If not playing then return None
        # if media_entity.state != MediaPlayerState.PLAYING:
        #    _LOGGER.warning("Not PLAYING! - %s", media_entity.state)
        #    return None
        data = None
        # An integration may populate these properties - most don't seem to
        if content_id := media_entity.media_content_id:
            data = PlayingMedia(
                media_content_id=content_id,
                media_type=media_entity.media_content_type | "music",
                media_position=media_entity.media_position,
            )

        media_integration = media_entity.platform.platform_name
        _LOGGER.debug("MEDIA ENTITY PLATFORM: %s", media_integration)
        # Browermod
        if media_integration == BROWSERMOD_DOMAIN:
            _data = media_entity._data  # noqa: SLF001
            _LOGGER.debug("MEDIA ENTITY DATA: %s", _data)
            return PlayingMedia(
                media_content_id=_data["player"].get("src"),
                media_type="music",
                media_position=_data.get("player", {}).get("media_position", None),
                volume=_data.get("player", {}).get("volume", 0),
            )

        # Music Assistant
        if media_integration == "mass":
            data = media_entity.mass
        # HA Voice Satellite
        elif media_integration == "esphome":
            data = media_entity._entry_data  # noqa: SLF001
        else:
            data = None

        _LOGGER.debug("MEDIA PLAYER DATA: %s", data)
        return None

    async def repeat_media(
        self, entity_id: str, media_type: str, media_url: str, max_repeats: int = 0
    ):
        """Repeat playing media file."""
        # Format media url

        if not media_url.startswith("http"):
            media_url = media_url.removeprefix("/")
            media_url = f"{get_url(self.hass)}/{media_url}"

        i = 1
        while i <= max_repeats or not max_repeats:
            await self.hass.services.async_call(
                "media_player",
                "play_media",
                {
                    "entity_id": entity_id,
                    "media_content_type": "music",
                    "media_content_id": media_url,
                },
            )
            await asyncio.sleep(1)
            i += 1

    async def cancel_alarm_sound(self, entity_id: str | None = None):
        """Cancel announcement."""
        if entity_id:
            entities = [entity_id]
        else:
            entities = list(self.alarm_tasks.keys())

        for mp_entity_id in entities:
            await self.hass.services.async_call(
                "media_player", "media_stop", {"entity_id": mp_entity_id}
            )
            if (
                self.alarm_tasks.get(mp_entity_id)
                and not self.alarm_tasks[mp_entity_id].done()
            ):
                self.alarm_tasks[mp_entity_id].cancel()

    async def alarm_sound(
        self,
        entity_id: str,
        media_url: str,
        media_type: MediaType = "music",
        resume: bool = True,
        max_repeats: int = 0,
    ):
        """Announce to media player and resume."""

        # Get instance of media player
        media_entity: MediaPlayerEntity
        if media_entity := self._get_entity_from_entity_id(entity_id):
            playing_media = self.get_currently_playing_media(media_entity)

            # Sound alarm
            self.alarm_tasks[entity_id] = self.config.async_create_background_task(
                self.hass,
                self.repeat_media(entity_id, media_type, media_url, max_repeats),
                name=f"AlarmRepeat-{entity_id}",
            )

            # Wait for alarm media task to finish
            while not self.alarm_tasks[entity_id].done():
                await asyncio.sleep(0.2)

            if resume and playing_media:
                _LOGGER.debug("Resuming media: %s", playing_media)
                await self.hass.services.async_call(
                    "media_player",
                    "play_media",
                    {
                        "entity_id": entity_id,
                        "media_content_type": playing_media.media_type,
                        "media_content_id": playing_media.media_content_id,
                    },
                )

                if playing_media.media_position:
                    await self.hass.services.async_call(
                        "media_player",
                        "media_seek",
                        {
                            "entity_id": entity_id,
                            "seek_position": playing_media.media_position,
                        },
                    )
        return {}
