"""Integration classes and constants."""

from enum import StrEnum

from homeassistant.const import CONF_MODE

from .typed import (
    VAAssistPrompt,
    VABackgroundMode,
    VAIconSizes,
    VAScreenMode,
    VATimeFormat,
)

DOMAIN = "view_assist"
GITHUB_REPO = "dinki/View-Assist"
GITHUB_BRANCH = "main"
GITHUB_TOKEN_FILE = "github.token"
GITHUB_PATH = "View Assist dashboard and views"
VIEWS_DIR = "views"
COMMUNITY_VIEWS_DIR = "community_contributions"
DASHBOARD_DIR = "dashboard"

DASHBOARD_NAME = "View Assist"
DEFAULT_VIEW = "clock"
DEFAULT_VIEWS = [
    "alarm",
    "camera",
    "clock",
    "info",
    "infopic",
    "intent",
    "list",
    "locate",
    "music",
    "sports",
    "thermostat",
    "weather",
    "webpage",
]
CYCLE_VIEWS = ["music", "info", "weather", "clock"]

BROWSERMOD_DOMAIN = "browser_mod"
REMOTE_ASSIST_DISPLAY_DOMAIN = "remote_assist_display"
CUSTOM_CONVERSATION_DOMAIN = "custom_conversation"
HASSMIC_DOMAIN = "hassmic"
USE_VA_NAVIGATION_FOR_BROWSERMOD = True

IMAGE_PATH = "images"
AUDIO_PATH = "audio"
VA_SUB_DIRS = [AUDIO_PATH, IMAGE_PATH]
URL_BASE = "view_assist"
RANDOM_IMAGE_URL = "https://unsplash.it/1280/800?random"
JSMODULES = [
    {
        "name": "View Assist Helper",
        "filename": "view_assist.js",
        "version": "1.0.10",
    },
]


class VAMode(StrEnum):
    """View Assist modes."""

    NORMAL = "normal"
    MUSIC = "music"
    CYCLE = "cycle"
    HOLD = "hold"
    NIGHT = "night"
    ROTATE = "rotate"


VAMODE_REVERTS = {
    VAMode.NORMAL: {"revert": True, "view": "home"},
    VAMode.MUSIC: {"revert": True, "view": "music"},
    VAMode.CYCLE: {"revert": False},
    VAMode.HOLD: {"revert": False},
    VAMode.NIGHT: {"revert": True, "view": "home"},
}


# Config keys
CONF_MIC_DEVICE = "mic_device"
CONF_MEDIAPLAYER_DEVICE = "mediaplayer_device"
CONF_MUSICPLAYER_DEVICE = "musicplayer_device"
CONF_DISPLAY_DEVICE = "display_device"
CONF_INTENT_DEVICE = "intent_device"

CONF_DASHBOARD = "dashboard"
CONF_HOME = "home"
CONF_INTENT = "intent"
CONF_MUSIC = "music"
CONF_BACKGROUND_SETTINGS = "background_settings"
CONF_BACKGROUND_MODE = "background_mode"
CONF_BACKGROUND = "background"
CONF_ROTATE_BACKGROUND_PATH = "rotate_background_path"
CONF_ROTATE_BACKGROUND_LINKED_ENTITY = "rotate_background_linked_entity"
CONF_ROTATE_BACKGROUND_INTERVAL = "rotate_background_interval"

CONF_DISPLAY_SETTINGS = "display_settings"
CONF_ASSIST_PROMPT = "assist_prompt"
CONF_STATUS_ICON_SIZE = "status_icons_size"
CONF_FONT_STYLE = "font_style"
CONF_STATUS_ICONS = "status_icons"
CONF_TIME_FORMAT = "time_format"
CONF_SCREEN_MODE = "screen_mode"

CONF_WEATHER_ENTITY = "weather_entity"
CONF_VIEW_TIMEOUT = "view_timeout"
CONF_DO_NOT_DISTURB = "do_not_disturb"
CONF_USE_ANNOUNCE = "use_announce"
CONF_MIC_UNMUTE = "micunmute"
CONF_DUCKING_VOLUME = "ducking_volume"


CONF_DEVELOPER_DEVICE = "developer_device"
CONF_DEVELOPER_MIMIC_DEVICE = "developer_mimic_device"


# Legacy
CONF_MIC_TYPE = "mic_type"
CONF_USE_24H_TIME = "use_24_hour_time"
CONF_DEV_MIMIC = "dev_mimic"
CONF_HIDE_HEADER = "hide_header"
CONF_HIDE_SIDEBAR = "hide_sidebar"
CONF_ROTATE_BACKGROUND = "rotate_background"
CONF_ROTATE_BACKGROUND_SOURCE = "rotate_background_source"


DEFAULT_VALUES = {
    # Dashboard options
    CONF_DASHBOARD: "/view-assist",
    CONF_HOME: "/view-assist/clock",
    CONF_MUSIC: "/view-assist/music",
    CONF_INTENT: "/view-assist/intent",
    CONF_BACKGROUND_SETTINGS: {
        CONF_BACKGROUND_MODE: VABackgroundMode.DEFAULT_BACKGROUND,
        CONF_BACKGROUND: "/view_assist/dashboard/background.jpg",
        CONF_ROTATE_BACKGROUND_PATH: f"{IMAGE_PATH}/backgrounds",
        CONF_ROTATE_BACKGROUND_LINKED_ENTITY: "",
        CONF_ROTATE_BACKGROUND_INTERVAL: 60,
    },
    CONF_DISPLAY_SETTINGS: {
        CONF_ASSIST_PROMPT: VAAssistPrompt.BLUR_POPUP,
        CONF_STATUS_ICON_SIZE: VAIconSizes.LARGE,
        CONF_FONT_STYLE: "Roboto",
        CONF_STATUS_ICONS: [],
        CONF_TIME_FORMAT: VATimeFormat.HOUR_12,
        CONF_SCREEN_MODE: VAScreenMode.HIDE_HEADER_SIDEBAR,
    },
    # Default options
    CONF_WEATHER_ENTITY: "weather.home",
    CONF_MODE: VAMode.NORMAL,
    CONF_VIEW_TIMEOUT: 20,
    CONF_DO_NOT_DISTURB: "off",
    CONF_USE_ANNOUNCE: "off",
    CONF_MIC_UNMUTE: "off",
    CONF_DUCKING_VOLUME: 2,
    # Default developer otions
    CONF_DEVELOPER_DEVICE: "",
    CONF_DEVELOPER_MIMIC_DEVICE: "",
}

# Config default values
DEFAULT_NAME = "View Assist"
DEFAULT_TYPE = "view_audio"
DEFAULT_VIEW_INFO = "info"


# Service attributes
ATTR_EVENT_NAME = "event_name"
ATTR_EVENT_DATA = "event_data"
ATTR_PATH = "path"
ATTR_DEVICE = "device"
ATTR_REDOWNLOAD_FROM_REPO = "download_from_repo"
ATTR_COMMUNITY_VIEW = "community_view"
ATTR_BACKUP_CURRENT_VIEW = "backup_current_view"
ATTR_EXTRA = "extra"
ATTR_TYPE = "type"
ATTR_TIMER_ID = "timer_id"
ATTR_REMOVE_ALL = "remove_all"
ATTR_INCLUDE_EXPIRED = "include_expired"
ATTR_MEDIA_FILE = "media_file"
ATTR_RESUME_MEDIA = "resume_media"
ATTR_MAX_REPEATS = "max_repeats"

VA_ATTRIBUTE_UPDATE_EVENT = "va_attr_update_event_{}"
VA_BACKGROUND_UPDATE_EVENT = "va_background_update_{}"
CC_CONVERSATION_ENDED_EVENT = f"{CUSTOM_CONVERSATION_DOMAIN}_conversation_ended"


# TODO: Remove this when BP/Views updated
OPTION_KEY_MIGRATIONS = {
    "blur pop up": "blur_pop_up",
    "flashing bar": "flashing_bar",
    "Home Assistant Voice Satellite": "home_assistant_voice_satellite",
    "HassMic": "hassmic",
    "Stream Assist": "stream_assist",
    "BrowserMod": "browser_mod",
    "Remote Assist Display": "remote_assist_display",
}
