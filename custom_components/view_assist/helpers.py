"""Helper functions."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import CONF_BROWSER_ID, DOMAIN, VAConfigEntry, VAType


def is_first_instance(
    hass: HomeAssistant, config: VAConfigEntry, display_instance_only: bool = False
):
    """Return if first config entry.

    Optional to return if first config entry for instance with type of view_audio
    """
    accepted_types = [VAType.VIEW_AUDIO]
    if not display_instance_only:
        accepted_types.append(VAType.AUDIO_ONLY)

    entries = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.data["type"] in accepted_types and not entry.disabled_by
    ]

    # If first instance matches this entry id, return True
    if entries and entries[0].entry_id == config.entry_id:
        return True
    return False


def ensure_list(value: str | list[str]):
    """Ensure that a value is a list."""
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        value = (value.replace("[", "").replace("]", "").replace('"', "")).split(",")
        return value if value else []
    return []


def get_entity_id_by_browser_id(hass: HomeAssistant, browser_id: str) -> str:
    """Get entity id form browser id.

    Support websocket
    """
    entity_registry = er.async_get(hass)

    # Get all instances of view assist
    entry_ids = [entry.entry_id for entry in hass.config_entries.async_entries(DOMAIN)]

    # For each instance, get list of entities
    for entry_id in entry_ids:
        integration_entities = er.async_entries_for_config_entry(
            entity_registry, entry_id
        )
        # Get entity ids
        entity_ids = [entity.entity_id for entity in integration_entities if entity]

        # Get entity id state and check browser id attribute
        for entity_id in entity_ids:
            if state := hass.states.get(entity_id):
                if (
                    state.attributes.get(CONF_BROWSER_ID)
                    and state.attributes[CONF_BROWSER_ID] == browser_id
                ):
                    return entity_id
    return None
