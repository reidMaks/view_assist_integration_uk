"""Class to handle timers with persistent storage."""

import asyncio
from asyncio import Task
import contextlib
from dataclasses import dataclass, field
import datetime as dt
from enum import StrEnum
import logging
import math
import re
import time
from typing import Any

import wordtodigits

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import ulid as ulid_util

from .const import DOMAIN
from .helpers import get_entity_id_from_conversation_device_id

_LOGGER = logging.getLogger(__name__)

# Event name prefixes
VA_EVENT_PREFIX = "va_timer_{}"
VA_COMMAND_EVENT_PREFIX = "va_timer_command_{}"


TIMERS_STORE_NAME = f"{DOMAIN}.timers"

WEEKDAYS = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]

SPECIAL_DAYS = [
    "today",
    "tomorrow",
]

AMPM = ["am", "pm"]

HOURS = {
    "midnight": 0,
    "noon": 12,
}
PAST_TO = {
    "quarter": 15,
    "half": 30,
}
HOUR_FRACTIONS = {
    "1/4": 15,
    "quarter": 15,
    "1/2": 30,
    "half": 30,
    "3/4": 45,
    "three quarters": 45,
}


class TimerClass(StrEnum):
    """Timer class."""

    ALARM = "alarm"
    REMINDER = "reminder"
    TIMER = "timer"
    COMMAND = "command"


@dataclass
class TimerInterval:
    """Timer Interval."""

    days: int = 0
    hours: int = 0
    minutes: int = 0
    seconds: int = 0


@dataclass
class TimerTime:
    """Timer Time."""

    day: str = ""
    hour: int = 0
    minute: int = 0
    second: int = 0
    meridiem: str = ""


class TimerStatus(StrEnum):
    """Timer status."""

    INACTIVE = "inactive"
    RUNNING = "running"
    EXPIRED = "expired"
    SNOOZED = "snoozed"


class TimerEvent(StrEnum):
    """Event enums."""

    STARTED = "started"
    WARNING = "warning"
    EXPIRED = "expired"
    SNOOZED = "snoozed"
    CANCELLED = "cancelled"


@dataclass
class Timer:
    """Class to hold timer."""

    timer_class: TimerClass
    original_expires_at: int
    expires_at: int
    timer_type: str = "TimerInterval"
    name: str | None = None
    device_id: str | None = None
    pre_expire_warning: int = 0
    created_at: int = 0
    updated_at: int = 0
    status: TimerStatus = field(default_factory=TimerStatus.INACTIVE)
    extra_info: dict[str, Any] | None = None

    @property
    def expires_in_seconds(self) -> int:
        """Get expire in time in seconds."""
        return (
            dt.datetime.fromtimestamp(self.expires_at) - dt.datetime.now()
        ).total_seconds()

    @property
    def expires_in_interval(self) -> dict[str, Any]:
        """Get expire in time in days, hours, mins, secs tuple."""
        expires_in = math.ceil(self.expires_in_seconds)
        days, remainder = divmod(expires_in, 3600 * 24)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        return {
            "days": days,
            "hours": hours,
            "minutes": minutes,
            "seconds": int(seconds),
        }

    @property
    def dynamic_name(self) -> str:
        """Generate dynamic name."""
        return encode_datetime_to_human(
            self.timer_type,
            self.name,
            dt.datetime.fromtimestamp(self.expires_at),
            append_name=False,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return json output."""
        return {
            "device_id": self.device_id,
            "timer_class": self.timer_class,
            "timer_type": self.timer_type,
            "name": self.name,
            "expires": dt.datetime.fromtimestamp(self.expires_at),
            "original_expiry": dt.datetime.fromtimestamp(self.original_expires_at),
            "pre_expire_warning": self.pre_expire_warning,
            "expires_in_seconds": math.ceil(self.expires_in_seconds),
            "expires_in_interval": self.expires_in_interval,
            "expires_in_text": self.dynamic_name,
            "created_at": dt.datetime.fromtimestamp(self.created_at),
            "updated_at": dt.datetime.fromtimestamp(self.updated_at),
            "status": self.status,
            "extra_info": self.extra_info,
        }


REGEX_DAYS = (
    r"(?i)\b("
    + (
        "|".join(WEEKDAYS + SPECIAL_DAYS)
        + "|"
        + "|".join(f"Next {weekday}" for weekday in WEEKDAYS)
    )
    + ")"
)

# Find a time in the string and split into day, hours, mins and secs
# 10:15 AM
# 1600
# 15:24
# Monday at 10:00 AM
REGEX_TIME = (
    r"(?i)\b("
    + ("|".join(WEEKDAYS + SPECIAL_DAYS))
    + r")?[ ]?(?:at)?[ ]?([01]?[0-9]|2[0-3]):?([0-5][0-9])(?::([0-9][0-9]))?[ ]?(AM|am|PM|pm|tonight)?\b"
)

# Find an interval in human readbale form and decode into days, hours, minutes, seconds.
# 5 minutes 30 seconds
# 5 minutes
# 2 hours 30 minutes
# 30 seconds
# 2 days 1 hour 20 minutes
# 1 day 20 minutes
REGEX_INTERVAL = (
    r"(?i)\b"  # noqa: ISC003
    + r"(?:(\d+) days?)?"
    + r"[ ]?(?:and)?[ ]?(?:([01]?[0-9]|2[0-3]]) hours?)?"
    + r"[ ]?(?:and)?[ ]?(?:([0-5]?[0-9]) minutes?)?"
    + r"[ ]?(?:and)?[ ]?(?:(\d+) seconds?)?\b"
)

# Allow natural language times
# quarter past 11
# 20 past five
# half past 12
# half past twelve
# twenty to four
# twenty to four AM
# twenty to four PM
# 20 to 4:00 PM
REGEX_SUPER_TIME = (
    r"(?i)\b("
    + ("|".join(WEEKDAYS + SPECIAL_DAYS))
    + r")?[ ]?(?:at)?[ ]?(\d+|"
    + "|".join(PAST_TO.keys())
    + r")\s(to|past)\s(\d+|"
    + ("|".join(HOURS))
    + r")(?::\d+)?[ ]?(am|pm|tonight)?\b"
)

# All natural language intervals
# 2 1/2 hours
# 2 and a half hours
# two and a half hours
# one and a quarter hours
# 1 1/2 minutes

# three quarters of an hour
# 3/4 of an hour
# half an hour
# 1/2 an hour
# quarter of an hour
# 1/4 of an hour
REGEX_SUPER_INTERVAL = (
    r"()(\d+|"
    + "|".join(HOURS)
    + r")?[ ]?(?:and a)?[ ]?("
    + "|".join(HOUR_FRACTIONS)
    + r")[ ](?:an|of an)?[ ]?(?:minutes?|hours?)()"
)


def calc_days_add(day: str, dt_now: dt.datetime) -> int:
    """Get number of days to add for required weekday from now."""
    day = day.lower()
    has_next = False

    # Deal with the likes of next wednesday
    if "next" in day:
        has_next = True
        day = day.replace("next", "").strip()

    if day in WEEKDAYS:
        # monday is weekday 0
        current_weekday = dt_now.weekday()
        set_weekday = WEEKDAYS.index(day)

        # Check for 'next' prefix to day or if day less than today (assume next week)
        if set_weekday < current_weekday or has_next:
            return (7 - current_weekday) + set_weekday

        return set_weekday - current_weekday
    if day == "tomorrow":  # or "tomorrow" in sentence:
        return 1
    return 0


def decode_time_sentence(sentence: str) -> dt.datetime | None:  # noqa: C901
    """Convert senstence from assist into datetime.

    Sentence can be:
        a time only in 12/24h format
        a time with a day of the week or a special day like tomorrow
        an interval like 10 hours and 3 minutes
        a spoken term like half past 6 or tuesday at 20 to 5

    Return None if unable to decode
    """

    def _convert_to_ints(input_list: list) -> list[int]:
        for i, entry in enumerate(input_list):
            if isinstance(entry, str):
                if entry.isnumeric():
                    input_list[i] = int(entry)
            # Set to 0 if None or ""
            if not entry:
                input_list[i] = 0

        return input_list

    # Preprocess sentence for known issues
    # These are a bit fudgy but so far too small a number to write
    # more regex's for them
    _sentence = sentence.lower()

    if _sentence == "an hour and a half":
        _sentence = "1 hour and 30 minutes"

    elif _sentence == "a day and a half":
        _sentence = "1 day and 12 hours"

    elif _sentence.startswith("an hour"):
        _sentence = _sentence.replace("an hour", "1 hour")

    # Convert all word numbers to ints
    if not _sentence.startswith("three quarters"):
        _sentence = wordtodigits.convert(_sentence)

    # Time search
    set_time = re.findall(REGEX_TIME, _sentence)

    # make sure not a super text statement by tesing for to or past in the senstence
    if " to " in _sentence or " past " in _sentence:
        set_time = None

    if set_time:
        set_time = list(set_time[0])

        # Convert h,r, min, sec to int
        set_time = set_time[:1] + _convert_to_ints(set_time[1:4]) + set_time[-1:]

        # Get if day or special day in sentence
        # This is a second check incase first REGEX does not detect it.
        if day_text := re.findall(REGEX_DAYS, _sentence):
            set_time[0] = day_text[0]

        # make into a class object
        time_info = TimerTime(
            day=set_time[0],
            hour=set_time[1],
            minute=set_time[2],
            second=set_time[3],
            meridiem=set_time[4],
        )
        return sentence, time_info

    # Interval search
    int_search = re.search(REGEX_INTERVAL, _sentence)
    interval = int_search.groups()

    if any(interval):
        interval = _convert_to_ints(list(interval))

        interval_info = TimerInterval(
            days=interval[0],
            hours=interval[1],
            minutes=interval[2],
            seconds=interval[3],
        )
        return sentence, interval_info

    # Super time search
    spec_time = re.findall(REGEX_SUPER_TIME, _sentence)
    if spec_time:
        set_time = list(spec_time[0])

        # return None if not a full match
        if all(set_time[1:3]):
            # Get if day or special day in sentence
            # This is a second check incase first REGEX does not detect it.
            if day_text := re.findall(REGEX_DAYS, _sentence):
                set_time[0] = day_text[0]

            # now iterate and replace text numbers with numbers
            for i, v in enumerate(set_time):
                if i > 0:
                    with contextlib.suppress(KeyError):
                        set_time[i] = HOURS.get(v, PAST_TO.get(v, v))

            # Set any string ints to int
            if isinstance(set_time[1], str) and set_time[1].isnumeric():
                set_time[1] = int(set_time[1])
            if isinstance(set_time[3], str) and set_time[3].isnumeric():
                set_time[3] = int(set_time[3])

            # Amend for set_time[2] == "to"
            if set_time[2] == "to":
                set_time[3] = set_time[3] - 1 if set_time[3] != 0 else 23
                set_time[1] = 60 - set_time[1]

            # make set_time into a class object
            time_info = TimerTime(
                day=set_time[0],
                hour=set_time[3],
                minute=set_time[1],
                second=0,
                meridiem=set_time[4],
            )
            return sentence, time_info

    # Super interval search
    interval = re.findall(REGEX_SUPER_INTERVAL, _sentence)
    if interval:
        interval = list(interval[0])

        # Convert hours to numbers
        if interval[1] in HOURS:
            interval[1] = HOURS.get(interval[1])

        # Convert hour fractions
        if interval[2] in HOUR_FRACTIONS:
            interval[2] = HOUR_FRACTIONS.get(interval[2])

        interval = _convert_to_ints(interval)

        # Fix for interval in minutes not hours
        if ("minute" in _sentence or "minutes" in _sentence) and not (
            "hour" in _sentence or "hours" in _sentence
        ):
            # Shift values right in list
            interval = interval[-1:] + interval[:-1]

        interval_info = TimerInterval(
            days=interval[0],
            hours=interval[1],
            minutes=interval[2],
            seconds=interval[3],
        )
        return sentence, interval_info

    _LOGGER.warning(
        "Time senstence decoder - Unable to decode: %s -> %s", sentence, None
    )
    return sentence, _sentence


def get_datetime_from_timer_interval(interval: TimerInterval) -> dt.datetime:
    """Return datetime from TimerInterval."""
    date = dt.datetime.now().replace(microsecond=0)
    return date + dt.timedelta(
        days=interval.days,
        hours=interval.hours,
        minutes=interval.minutes,
        seconds=interval.seconds,
    )


def get_datetime_from_timer_time(
    set_time: TimerTime, context_time: bool = True
) -> dt.datetime:
    """Return datetime from TimerTime."""
    dt_now = dt.datetime.now()
    add_hours = 0

    # Don't set times between midnight and 6am unless set specifically
    # assume they mean PM
    if set_time.hour < 6 and not set_time.meridiem:
        set_time.meridiem = "pm"

    if set_time.hour <= 12 and set_time.meridiem in ["pm", "tonight"]:
        add_hours = 12

    # Add time context - set for next time 12h time comes around
    # If 20 to 5 and it is 11am, set for 16:40
    # if 20 to 5 and it is 6pm, set for 04:40
    elif context_time and not set_time.meridiem:
        # Set for next 12h time match
        set_datetime = dt_now.replace(
            hour=set_time.hour, minute=set_time.minute, second=set_time.second
        )

        if set_time.hour < 12 and set_datetime + dt.timedelta(hours=12) > dt_now:
            add_hours = 12

    # Now build datetime
    date = dt_now
    date = date.replace(
        hour=(set_time.hour + add_hours) % 24,
        minute=set_time.minute if set_time.minute else 0,
        second=0,
        microsecond=0,
    )

    # if day name in sentence
    if set_time.day:
        add_days = calc_days_add(set_time.day, dt_now)
        date = date + dt.timedelta(days=add_days)

    # If time is less than now, add 1 day
    if date < dt.datetime.now():
        date = date + dt.timedelta(days=1)

    return date


def encode_datetime_to_human(
    timer_type: str,
    timer_name: str,
    timer_dt: dt.datetime,
    h24format: bool = False,
    append_name: bool = True,
) -> str:
    """Encode datetime into human speech sentence."""

    dt_now = dt.datetime.now()
    delta = timer_dt - dt_now
    delta_s = math.ceil(delta.total_seconds())

    if timer_type == "TimerInterval":
        minutes, seconds = divmod(delta_s, 60)
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)

        response = []
        if days:
            response.append(f"{days} days")
        if hours:
            response.append(f"{hours} hours")
        if minutes:
            response.append(f"{minutes} minutes")
        if seconds:
            response.append(f"{seconds} seconds")

        duration = ", ".join(response)
        if append_name and timer_name:
            return f"{timer_name} in {duration}"
        return duration

    if timer_type == "TimerTime":
        # do date bit - today, tomorrow, day of week if in next 7 days, date

        days_diff = timer_dt.day - dt_now.day
        named_output = True
        if days_diff == 0:
            output_date = "today"
        elif days_diff == 1:
            output_date = "tomorrow"
        elif days_diff < 7:
            output_date = f"{WEEKDAYS[timer_dt.weekday()]}"
        else:
            output_date = timer_dt.strftime("%-d %B")
            named_output = False

        if h24format:
            output_time = timer_dt.strftime("%-H:%M")
        else:
            output_time = timer_dt.strftime("%-I:%M %p")

        date_text = f"{output_date} at {output_time}"
        if append_name and timer_name:
            if named_output:
                return f"{timer_name} for {date_text}"
            return f"{timer_name} on {date_text}"
        return date_text

    return timer_dt


def make_singular(sentence: str) -> str:
    """Make a time senstence singluar."""
    if sentence[-1:].lower() == "s":
        return sentence[:-1]
    return sentence


class VATimerStore:
    """Class to manager timer store."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialise."""
        self.store = Store(hass, 1, TIMERS_STORE_NAME)
        self.listeners = []
        self.timers: dict[str, Timer] = {}
        self.dirty = False

    async def save(self):
        """Save store."""
        if self.dirty:
            await self.store.async_save(self.timers)
            self.dirty = False

    async def load(self):
        """Load tiers from store."""
        stored: dict[str, Any] = await self.store.async_load()
        if stored:
            for timer_id, timer in stored.items():
                self.timers[timer_id] = Timer(**timer)
        self.dirty = False

    async def updated(self, timer_id: str):
        """Store has been updated."""
        self.dirty = True
        if timer_id in self.timers:
            self.timers[timer_id].updated_at = time.mktime(
                dt.datetime.now().timetuple()
            )
        for listener in self.listeners:
            listener(self.timers)
        await self.save()

    def add_listener(self, callback):
        """Add store updated listener."""
        self.listeners.append(callback)

        def remove_listener():
            self.listeners.remove(callback)

        return remove_listener

    async def update_status(self, timer_id: str, status: TimerStatus):
        """Update timer current status."""
        self.timers[timer_id].status = status
        await self.updated(timer_id)

    async def cancel_timer(self, timer_id: str) -> bool:
        """Cancel timer."""
        if timer_id in self.timers:
            self.timers.pop(timer_id)
            await self.updated(timer_id)
            return True
        return False


class VATimers:
    """Class to handle VA timers."""

    def __init__(self, hass: HomeAssistant, config: ConfigEntry) -> None:
        """Initialise."""
        self.hass = hass
        self.config = config

        self.store = VATimerStore(hass)
        self.timer_tasks: dict[str, Task] = {}

    async def load(self):
        """Load data store."""
        await self.store.load()

        if self.store.timers:
            # Removed any in expired status on restart as event already got fired
            expired_timers = [
                timer_id
                for timer_id, timer in self.store.timers.items()
                if timer.status == TimerStatus.EXPIRED
            ]
            for timer_id in expired_timers:
                self.store.timers.pop(timer_id, None)

            for timer_id, timer in self.store.timers.items():
                await self.start_timer(timer_id, timer)

    async def _fire_event(self, timer_id: int, event_type: TimerEvent):
        """Fire timer event on the event bus."""
        if timer := self.store.timers.get(timer_id):
            event_name = (
                VA_COMMAND_EVENT_PREFIX
                if timer.timer_class == TimerClass.COMMAND
                else VA_EVENT_PREFIX
            ).format(event_type)
            event_data = {"timer_id": timer_id}
            event_data.update(timer.to_dict())
            self.hass.bus.async_fire(event_name, event_data)
            _LOGGER.debug("Timer event fired: %s - %s", event_name, event_data)

    def is_duplicate_timer(self, device_id: str, name: str, expires_at: int) -> bool:
        """Return if same timer already exists."""

        # Get timers for device_id
        existing_device_timers = [
            timer_id
            for timer_id, timer in self.store.timers.items()
            if timer.device_id == device_id
        ]

        if not existing_device_timers:
            return False

        for timer_id in existing_device_timers:
            timer = self.store.timers[timer_id]
            if timer.expires_at == expires_at:
                return True
        return False

    async def add_timer(
        self,
        timer_class: TimerClass,
        device_id: str,
        timer_info: TimerTime | TimerInterval,
        name: str | None = None,
        pre_expire_warning: int = 10,
        start: bool = True,
        extra_info: dict[str, Any] | None = None,
    ) -> tuple:
        """Add timer to store."""

        timer_id = ulid_util.ulid_now()

        # calculate expiry time from TimerTime or TimerInterval
        timer_info_class = timer_info.__class__.__name__
        if timer_info_class == "TimerTime":
            expiry = get_datetime_from_timer_time(timer_info)
        elif timer_info_class == "TimerInterval":
            expiry = get_datetime_from_timer_interval(timer_info)
        else:
            raise TypeError("Not a valid time or interval object")

        expires_unix_ts = time.mktime(expiry.timetuple())
        time_now_unix = time.mktime(dt.datetime.now().timetuple())

        if not self.is_duplicate_timer(device_id, name, expires_unix_ts):
            # Add timer_info to extra_info
            extra_info["timer_info"] = timer_info
            extra_info["view_assist_entity_id"] = (
                get_entity_id_from_conversation_device_id(self.hass, device_id)
            )

            timer = Timer(
                timer_class=timer_class.lower(),
                timer_type=timer_info_class,
                original_expires_at=expires_unix_ts,
                expires_at=expires_unix_ts,
                name=name,
                device_id=device_id,
                pre_expire_warning=pre_expire_warning,
                created_at=time_now_unix,
                updated_at=time_now_unix,
                status=TimerStatus.INACTIVE,
                extra_info=extra_info,
            )

            self.store.timers[timer_id] = timer
            await self.store.save()

            if start:
                await self.start_timer(timer_id, timer)

            encoded_time = encode_datetime_to_human(
                timer_info_class, timer.name, expiry
            )
            return timer_id, timer.to_dict(), encoded_time

        return None, None, "already exists"

    async def start_timer(self, timer_id: str, timer: Timer):
        """Start timer running."""

        time_now_unix = time.mktime(dt.datetime.now().timetuple())
        total_seconds = timer.expires_at - time_now_unix

        # Fire event if total seconds -ve
        # likely caused by timer expiring during restart
        if total_seconds < 1:
            await self._timer_finished(timer_id)
        else:
            if timer.pre_expire_warning and timer.pre_expire_warning >= total_seconds:
                # Create task to wait for timer duration with no warning
                self.timer_tasks[timer_id] = self.config.async_create_background_task(
                    self.hass,
                    self._wait_for_timer(
                        timer_id, total_seconds, timer.updated_at, fire_warning=False
                    ),
                    name=f"Timer {timer_id}",
                )
                _LOGGER.debug(
                    "Started %s timer for %ss, with no warning event",
                    timer.name,
                    total_seconds,
                )
            else:
                # Create task to wait for timer duration minus any pre_expire_warning time
                self.timer_tasks[timer_id] = self.config.async_create_background_task(
                    self.hass,
                    self._wait_for_timer(
                        timer_id,
                        total_seconds - timer.pre_expire_warning,
                        timer.updated_at,
                    ),
                    name=f"Timer {timer_id}",
                )
                _LOGGER.debug(
                    "Started %s timer for %ss, with warning event at %ss",
                    timer.name,
                    total_seconds,
                    total_seconds - timer.pre_expire_warning,
                )

            # Set timer status
            if timer.status == TimerStatus.SNOOZED:
                return

            if timer.status != TimerStatus.RUNNING:
                await self.store.update_status(timer_id, TimerStatus.RUNNING)

                # Fire event - done here to only fire if new timer started not
                # existing timer restarted after HA restart
                await self._fire_event(timer_id, TimerEvent.STARTED)

    async def snooze_timer(self, timer_id: str, duration: TimerInterval):
        """Snooze expired timer.

        This will set the timer expire to now plus duration on an expired timer
        and set the status to snooze.  Then re-run the timer.
        """
        timer = self.store.timers.get(timer_id)
        if timer and timer.status == TimerStatus.EXPIRED:
            expiry = get_datetime_from_timer_interval(duration)
            timer.expires_at = time.mktime(expiry.timetuple())
            timer.extra_info["snooze_duration"] = duration
            await self.store.update_status(timer_id, TimerStatus.SNOOZED)
            await self.start_timer(timer_id, timer)
            await self._fire_event(timer_id, TimerEvent.SNOOZED)

            encoded_duration = encode_datetime_to_human(
                "TimerInterval", timer.name, expiry
            )

            return timer_id, timer.to_dict(), encoded_duration
        return None, None, "unable to snooze"

    async def cancel_timer(
        self,
        timer_id: str | None = None,
        device_id: str | None = None,
        cancel_all: bool = False,
    ) -> bool:
        """Cancel timer by timer id, device id or all."""
        if timer_id:
            timer_ids = [timer_id] if self.store.timers.get(timer_id) else []
        elif device_id:
            timer_ids = [
                timer_id
                for timer_id, timer in self.store.timers.items()
                if timer.device_id == device_id
            ]
        elif cancel_all:
            timer_ids = self.store.timers.copy().keys()

        if timer_ids:
            for timerid in timer_ids:
                if await self.store.cancel_timer(timerid):
                    _LOGGER.debug("Cancelled timer: %s", timerid)
                    if timer_task := self.timer_tasks.pop(timerid, None):
                        if not timer_task.done():
                            timer_task.cancel()
            return True

        return False

    def get_timers(
        self,
        timer_id: str = "",
        device_id: str = "",
        include_expired: bool = False,
        sort: bool = True,
    ) -> list[Timer]:
        """Get list of timers.

        Optionally supply timer_id or device_id to filter the returned list
        """
        timers = {}

        if include_expired:
            timers = [
                {"id": tid, **timer.to_dict()}
                for tid, timer in self.store.timers.items()
                if timer.status != TimerStatus.EXPIRED
            ]
        else:
            timers = [
                {"id": tid, **timer.to_dict()}
                for tid, timer in self.store.timers.items()
                if timer.status != TimerStatus.EXPIRED
            ]

        if timer_id:
            timers = [timer for timer in timers if timer["id"] == timer_id]

        elif device_id:
            timers = [timer for timer in timers if timer["device_id"] == device_id]

        if sort and timers:
            timers = sorted(timers, key=lambda d: d["expires_in_seconds"])

        return timers

    async def _wait_for_timer(
        self, timer_id: str, seconds: int, updated_at: int, fire_warning: bool = True
    ) -> None:
        """Sleep until timer is up. Timer is only finished if it hasn't been updated."""
        try:
            await asyncio.sleep(seconds)
            timer = self.store.timers.get(timer_id)
            if timer and timer.updated_at == updated_at:
                if fire_warning and timer.pre_expire_warning:
                    await self._pre_expire_warning(timer_id)
                else:
                    await self._timer_finished(timer_id)
        except asyncio.CancelledError:
            pass  # expected when timer is updated

    async def _pre_expire_warning(self, timer_id: str) -> None:
        """Call event on timer pre_expire_warning and then call expire."""
        timer = self.store.timers[timer_id]

        if timer and timer.status == TimerStatus.RUNNING:
            await self._fire_event(timer_id, TimerEvent.WARNING)

            await asyncio.sleep(timer.pre_expire_warning)
            await self._timer_finished(timer_id)

    async def _timer_finished(self, timer_id: str) -> None:
        """Call event handlers when a timer finishes."""

        await self._fire_event(timer_id, TimerEvent.EXPIRED)
        await self.store.update_status(timer_id, TimerStatus.EXPIRED)
        self.timer_tasks.pop(timer_id, None)
