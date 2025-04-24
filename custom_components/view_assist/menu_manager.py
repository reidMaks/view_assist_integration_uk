"""Menu manager for View Assist."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import logging
from typing import Any, Dict, List, Optional, Tuple, Union

from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    CONF_DISPLAY_SETTINGS,
    CONF_ENABLE_MENU,
    CONF_ENABLE_MENU_TIMEOUT,
    CONF_MENU_ITEMS,
    CONF_MENU_TIMEOUT,
    CONF_SHOW_MENU_BUTTON,
    CONF_STATUS_ICONS,
    DEFAULT_VALUES,
    DOMAIN,
)
from .helpers import (
    arrange_status_icons,
    ensure_menu_button_at_end,
    get_config_entry_by_entity_id,
    get_master_config_entry,
    get_sensor_entity_from_instance,
    normalize_status_items,
    update_status_icons,
)
from .typed import VAConfigEntry, VAEvent

_LOGGER = logging.getLogger(__name__)

# Maximum number of update iterations before restarting the processor
MAX_UPDATE_ITERATIONS = 10000
StatusItemType = Union[str, List[str]]


@dataclass
class MenuState:
    """Structured representation of a menu's state."""

    entity_id: str
    active: bool = False
    configured_items: List[str] = field(default_factory=list)
    status_icons: List[str] = field(default_factory=list)
    system_icons: List[str] = field(default_factory=list)
    menu_timeout: Optional[asyncio.Task] = None
    item_timeouts: Dict[Tuple[str, str, bool], asyncio.Task] = field(
        default_factory=dict
    )


class MenuManager:
    """Class to manage View Assist menus."""

    def __init__(self, hass: HomeAssistant, config: VAConfigEntry) -> None:
        """Initialize menu manager."""
        self.hass = hass
        self.config = config
        self._menu_states: Dict[str, MenuState] = {}
        self._pending_updates: Dict[str, Dict[str, Any]] = {}
        self._update_event = asyncio.Event()
        self._update_task: Optional[asyncio.Task] = None
        self._initialized = False

        config.async_on_unload(self.cleanup)
        self.hass.bus.async_listen_once(
            "homeassistant_started", self._initialize_on_startup)

    async def _initialize_on_startup(self, _event: Event) -> None:
        """Initialize when Home Assistant has fully started."""
        if self._initialized:
            return

        self._update_task = self.config.async_create_background_task(
            self.hass, self._update_processor(), name="VA Menu Manager"
        )

        # Initialize existing entities
        for entry_id in [e.entry_id for e in self.hass.config_entries.async_entries(DOMAIN)]:
            entity_id = get_sensor_entity_from_instance(self.hass, entry_id)
            if entity_id:
                self._get_or_create_state(entity_id)

        self._initialized = True
        _LOGGER.debug("Menu manager initialized")

    def _get_or_create_state(self, entity_id: str) -> MenuState:
        """Get or create a MenuState for the entity."""
        if entity_id not in self._menu_states:
            self._menu_states[entity_id] = MenuState(entity_id=entity_id)
            state = self.hass.states.get(entity_id)

            if state:
                menu_items = self._get_config_value(
                    entity_id, f"{CONF_DISPLAY_SETTINGS}.{CONF_MENU_ITEMS}", []
                )
                self._menu_states[entity_id].configured_items = menu_items or []

                status_icons = state.attributes.get(CONF_STATUS_ICONS, [])
                self._menu_states[entity_id].status_icons = status_icons if status_icons else [
                ]
                self._menu_states[entity_id].active = state.attributes.get(
                    "menu_active", False)

                self._menu_states[entity_id].system_icons = [
                    icon for icon in self._menu_states[entity_id].status_icons
                    if icon not in self._menu_states[entity_id].configured_items
                    and icon != "menu"
                ]

        return self._menu_states[entity_id]

    def _get_config_value(self, entity_id: str, key: str, default: Any = None) -> Any:
        """Get configuration value with hierarchy: entity > master > default."""
        # Check entity config
        entity_config = get_config_entry_by_entity_id(self.hass, entity_id)
        if entity_config:
            # Check direct key
            if key in entity_config.options:
                return entity_config.options[key]

            # Check nested key
            if "." in key:
                section, setting = key.split(".")
                if (section in entity_config.options and
                    isinstance(entity_config.options[section], dict) and
                        setting in entity_config.options[section]):
                    return entity_config.options[section][setting]

        # Check master config
        master_config = get_master_config_entry(self.hass)
        if master_config:
            # Check direct key
            if key in master_config.options:
                return master_config.options[key]

            # Check nested key
            if "." in key:
                section, setting = key.split(".")
                if (section in master_config.options and
                    isinstance(master_config.options[section], dict) and
                        setting in master_config.options[section]):
                    return master_config.options[section][setting]

        # Check defaults
        if key in DEFAULT_VALUES:
            return DEFAULT_VALUES[key]

        if "." in key:
            section, setting = key.split(".")
            if (section in DEFAULT_VALUES and
                isinstance(DEFAULT_VALUES[section], dict) and
                    setting in DEFAULT_VALUES[section]):
                return DEFAULT_VALUES[section][setting]

        return default

    async def toggle_menu(
        self, entity_id: str, show: Optional[bool] = None, timeout: Optional[int] = None
    ) -> None:
        """Toggle menu visibility for an entity."""
        # Ensure initialization
        await self._ensure_initialized()

        # Validate entity and config
        config_entry = get_config_entry_by_entity_id(self.hass, entity_id)
        if not config_entry:
            _LOGGER.error("Config entry not found for %s", entity_id)
            return

        enable_menu = self._get_config_value(
            entity_id, f"{CONF_DISPLAY_SETTINGS}.{CONF_ENABLE_MENU}", False
        )

        if not enable_menu:
            _LOGGER.warning("Menu is not enabled for %s", entity_id)
            return

        state = self.hass.states.get(entity_id)
        if not state:
            _LOGGER.warning("Entity %s not found", entity_id)
            return

        # Get menu state and settings
        menu_state = self._get_or_create_state(entity_id)
        current_active = menu_state.active
        show = show if show is not None else not current_active

        self._cancel_timeout(entity_id)

        show_menu_button = self._get_config_value(
            entity_id, f"{CONF_DISPLAY_SETTINGS}.{CONF_SHOW_MENU_BUTTON}", False
        )

        # Update system icons from current status
        current_status_icons = state.attributes.get(CONF_STATUS_ICONS, [])
        system_icons = [
            icon for icon in current_status_icons
            if icon not in menu_state.configured_items and icon != "menu"
        ]
        menu_state.system_icons = system_icons

        # Apply the menu state change
        changes = {}
        if show:
            # Show menu
            updated_icons = arrange_status_icons(
                menu_state.configured_items, system_icons, show_menu_button
            )
            menu_state.active = True
            menu_state.status_icons = updated_icons
            changes = {"status_icons": updated_icons, "menu_active": True}

            # Handle timeout
            if timeout is not None:
                self._setup_timeout(entity_id, timeout)
            elif self._get_config_value(
                entity_id, f"{CONF_DISPLAY_SETTINGS}.{CONF_ENABLE_MENU_TIMEOUT}", False
            ):
                timeout_value = self._get_config_value(
                    entity_id, f"{CONF_DISPLAY_SETTINGS}.{CONF_MENU_TIMEOUT}", 10
                )
                self._setup_timeout(entity_id, timeout_value)
        else:
            # Hide menu
            updated_icons = system_icons.copy()
            if show_menu_button:
                ensure_menu_button_at_end(updated_icons)

            menu_state.active = False
            menu_state.status_icons = updated_icons
            changes = {"status_icons": updated_icons, "menu_active": False}

        # Apply changes
        if changes:
            await self._update_entity_state(entity_id, changes)

            # Notify via dispatcher
            if config_entry:
                async_dispatcher_send(
                    self.hass,
                    f"{DOMAIN}_{config_entry.entry_id}_event",
                    VAEvent("menu_update", {"menu_active": show}),
                )

    async def add_menu_item(
        self,
        entity_id: str,
        status_item: StatusItemType,
        menu: bool = False,
        timeout: Optional[int] = None,
    ) -> None:
        """Add status item(s) to the entity's status icons or menu items."""
        # Normalize input and validate
        items = normalize_status_items(status_item)
        if isinstance(items, str):
            items = [items]
        elif not items:
            _LOGGER.warning("No valid items to add")
            return

        config_entry = get_config_entry_by_entity_id(self.hass, entity_id)
        if not config_entry:
            _LOGGER.warning("No config entry found for entity %s", entity_id)
            return

        # Ensure initialization
        await self._ensure_initialized()
        menu_state = self._get_or_create_state(entity_id)
        show_menu_button = self._get_config_value(
            entity_id, f"{CONF_DISPLAY_SETTINGS}.{CONF_SHOW_MENU_BUTTON}", False
        )

        changes = {}
        if menu:
            # Add to menu items
            updated_items = menu_state.configured_items.copy()
            changed = False

            for item in items:
                if item not in updated_items:
                    updated_items.append(item)
                    changed = True

            if changed:
                menu_state.configured_items = updated_items
                changes["menu_items"] = updated_items
                await self._save_to_config_entry_options(entity_id, CONF_MENU_ITEMS, updated_items)

                # Update icons if menu is active
                if menu_state.active:
                    updated_icons = arrange_status_icons(
                        updated_items, menu_state.system_icons, show_menu_button
                    )
                    menu_state.status_icons = updated_icons
                    changes["status_icons"] = updated_icons
        else:
            # Add to status icons
            updated_icons = update_status_icons(
                menu_state.status_icons,
                add_icons=items,
                menu_items=menu_state.configured_items if menu_state.active else None,
                show_menu_button=show_menu_button
            )

            if updated_icons != menu_state.status_icons:
                menu_state.status_icons = updated_icons
                changes["status_icons"] = updated_icons
                await self._save_to_config_entry_options(entity_id, CONF_STATUS_ICONS, updated_icons)

        # Apply changes
        if changes:
            await self._update_entity_state(entity_id, changes)

        # Set up timeouts if needed
        if timeout is not None:
            for item in items:
                await self._setup_item_timeout(entity_id, item, timeout, menu)

    async def remove_menu_item(
        self, entity_id: str, status_item: StatusItemType, from_menu: bool = False
    ) -> None:
        """Remove status item(s) from the entity's status icons or menu items."""
        # Normalize input and validate
        items = normalize_status_items(status_item)
        if isinstance(items, str):
            items = [items]
        elif not items:
            _LOGGER.warning("No valid items to remove")
            return

        config_entry = get_config_entry_by_entity_id(self.hass, entity_id)
        if not config_entry:
            return

        # Ensure initialization
        await self._ensure_initialized()
        menu_state = self._get_or_create_state(entity_id)
        show_menu_button = self._get_config_value(
            entity_id, f"{CONF_DISPLAY_SETTINGS}.{CONF_SHOW_MENU_BUTTON}", False
        )

        changes = {}
        if from_menu:
            # Remove from menu items
            updated_items = [
                item for item in menu_state.configured_items if item not in items]

            if updated_items != menu_state.configured_items:
                menu_state.configured_items = updated_items
                changes["menu_items"] = updated_items
                await self._save_to_config_entry_options(entity_id, CONF_MENU_ITEMS, updated_items)

                # Update icons if menu is active
                if menu_state.active:
                    updated_icons = arrange_status_icons(
                        updated_items, menu_state.system_icons, show_menu_button
                    )
                    menu_state.status_icons = updated_icons
                    changes["status_icons"] = updated_icons
        else:
            # Remove from status icons
            updated_icons = update_status_icons(
                menu_state.status_icons,
                remove_icons=items,
                menu_items=menu_state.configured_items if menu_state.active else None,
                show_menu_button=show_menu_button
            )

            if updated_icons != menu_state.status_icons:
                menu_state.status_icons = updated_icons
                changes["status_icons"] = updated_icons
                await self._save_to_config_entry_options(entity_id, CONF_STATUS_ICONS, updated_icons)

        # Apply changes and cancel timeouts
        if changes:
            await self._update_entity_state(entity_id, changes)

        for item in items:
            self._cancel_item_timeout(entity_id, item, from_menu)

    async def _save_to_config_entry_options(self, entity_id: str, option_key: str, value: List[str]) -> None:
        """Save options to config entry for persistence."""
        config_entry = get_config_entry_by_entity_id(self.hass, entity_id)
        if not config_entry:
            _LOGGER.warning(
                "Cannot save %s - config entry not found", option_key)
            return

        try:
            new_options = dict(config_entry.options)
            new_options[option_key] = value
            self.hass.config_entries.async_update_entry(
                config_entry, options=new_options)
        except Exception as err:
            _LOGGER.error("Error saving config entry options: %s", str(err))

    def _setup_timeout(self, entity_id: str, timeout: int) -> None:
        """Setup timeout for menu."""
        menu_state = self._get_or_create_state(entity_id)
        self._cancel_timeout(entity_id)

        async def _timeout_task() -> None:
            try:
                await asyncio.sleep(timeout)
                await self.toggle_menu(entity_id, False)
            except asyncio.CancelledError:
                pass

        menu_state.menu_timeout = self.config.async_create_background_task(
            self.hass, _timeout_task(), name=f"VA Menu Timeout {entity_id}"
        )

    def _cancel_timeout(self, entity_id: str) -> None:
        """Cancel any existing timeout for an entity."""
        if entity_id in self._menu_states and self._menu_states[entity_id].menu_timeout:
            menu_timeout = self._menu_states[entity_id].menu_timeout
            if not menu_timeout.done():
                menu_timeout.cancel()
                self._menu_states[entity_id].menu_timeout = None

    async def _setup_item_timeout(
        self, entity_id: str, menu_item: str, timeout: int, is_menu_item: bool = False
    ) -> None:
        """Set up a timeout for a specific menu item."""
        menu_state = self._get_or_create_state(entity_id)
        item_key = (entity_id, menu_item, is_menu_item)
        self._cancel_item_timeout(entity_id, menu_item, is_menu_item)

        async def _item_timeout_task() -> None:
            try:
                await asyncio.sleep(timeout)
                await self.remove_menu_item(entity_id, menu_item, is_menu_item)
            except asyncio.CancelledError:
                pass

        menu_state.item_timeouts[item_key] = self.config.async_create_background_task(
            self.hass, _item_timeout_task(), name=f"VA Item Timeout {entity_id} {menu_item}"
        )

    def _cancel_item_timeout(
        self, entity_id: str, menu_item: str, is_menu_item: bool = False
    ) -> None:
        """Cancel timeout for a specific menu item."""
        if entity_id not in self._menu_states:
            return

        menu_state = self._menu_states[entity_id]
        item_key = (entity_id, menu_item, is_menu_item)

        if item_key in menu_state.item_timeouts and not menu_state.item_timeouts[item_key].done():
            menu_state.item_timeouts[item_key].cancel()
            menu_state.item_timeouts.pop(item_key)

    async def _update_entity_state(
        self, entity_id: str, changes: Dict[str, Any]
    ) -> None:
        """Queue entity state update."""
        if not changes:
            return

        if entity_id not in self._pending_updates:
            self._pending_updates[entity_id] = {}

        self._pending_updates[entity_id].update(changes)
        self._update_event.set()

    async def _update_processor(self) -> None:
        """Process updates with a fixed iteration limit."""
        iterations = 0

        while iterations < MAX_UPDATE_ITERATIONS:
            iterations += 1

            try:
                await self._update_event.wait()
                self._update_event.clear()

                updates = self._pending_updates.copy()
                self._pending_updates.clear()

                for entity_id, changes in updates.items():
                    if changes:
                        changes["entity_id"] = entity_id
                        try:
                            await self.hass.services.async_call(DOMAIN, "set_state", changes)
                        except Exception as err:
                            _LOGGER.error("Error updating %s: %s",
                                          entity_id, str(err))

            except asyncio.CancelledError:
                break
            except Exception as err:
                _LOGGER.error("Unexpected error: %s", str(err))
                await asyncio.sleep(1)

        # Restart if reached iteration limit
        if iterations >= MAX_UPDATE_ITERATIONS:
            self._update_task = self.config.async_create_background_task(
                self.hass, self._update_processor(), name="VA Menu Manager"
            )

    async def _ensure_initialized(self) -> None:
        """Ensure the menu manager is initialized."""
        if not self._initialized:
            self._update_task = self.config.async_create_background_task(
                self.hass, self._update_processor(), name="VA Menu Manager"
            )

            for entry_id in [e.entry_id for e in self.hass.config_entries.async_entries(DOMAIN)]:
                entity_id = get_sensor_entity_from_instance(
                    self.hass, entry_id)
                if entity_id:
                    self._get_or_create_state(entity_id)

            self._initialized = True

    async def cleanup(self) -> None:
        """Clean up resources."""
        for menu_state in self._menu_states.values():
            if menu_state.menu_timeout and not menu_state.menu_timeout.done():
                menu_state.menu_timeout.cancel()

            for timeout in menu_state.item_timeouts.values():
                if not timeout.done():
                    timeout.cancel()

        if self._update_task and not self._update_task.done():
            self._update_task.cancel()
