"""Class to handle persistent storage."""

import asyncio
from asyncio import Task
import contextlib
import datetime as dt
import logging
import math
import re
import time
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import ulid as ulid_util

from .const import (
    HOURS,
    PAST_TO,
    SPECIAL_DAYS,
    TIMERS_STORE_NAME,
    VA_TIMER_FINISHED_EVENT,
    WEEKDAYS,
    Timer,
    TimerClass,
    TimerInterval,
    TimerStatus,
    TimerTime,
)

_LOGGER = logging.getLogger(__name__)

# TODO: TO BE REMOVED WHEN KNOWN WORKING!!!
TESTDATA = [
    "4:00 PM",
    "1600",
    "10:30 AM",
    "11:30",
    "23:48",
    "Thursday 4:00 PM",
    "Tuesday at 2300",
    "Sunday at 9:15 PM",
    "Sunday at 9:15 AM",
    "4:13 PM on Thursday",
    "1600 on Thursday",
    "Tomorrow at 1245",
    "Next Wednesday at 21:15",
    "Next Monday at 08:15 AM",
    "Next Friday at 1200",
    "2 days 1 hour 20 minutes",
    "1 day 20 minutes",
    "5 hours",
    "2 hours 30 minutes",
    "30 seconds",
    "5 minutes 30 seconds",
    "5 minutes",
    "2 1/2 hours",
    "quarter past 11",
    "20 past five",
    "half past 12",
    "half past twelve",
    "twenty to four",
    "twenty to four AM",
    "twenty to four PM",
    "20 to 4:00 PM",
    "tuesday at ten past 4",
    "half past nine tonight",
]


REGEX_DAYS = r"(?i)\b(" + ("|".join(WEEKDAYS + SPECIAL_DAYS)) + ")"

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
REGEX_SUPER_TEXT = (
    r"(?i)\b("
    + ("|".join(WEEKDAYS + SPECIAL_DAYS))
    + r")?[ ]?(?:at)?[ ]?(\d+|"
    + "|".join(PAST_TO.keys())
    + r")\s(to|past)\s(\d+|"
    + ("|".join(HOURS))
    + r")(?::\d+)?[ ]?(am|pm|tonight)?\b"
)


def calc_days_add(day: str, dt_now: dt.datetime) -> int:
    """Get number of days to add for required weekday from now."""
    day = day.lower()
    if day in WEEKDAYS:
        # monday is weekday 0
        current_weekday = dt_now.weekday()
        set_weekday = WEEKDAYS.index(day)

        # Check for 'next' prefix to day or if day less than today (assume next week)
        if set_weekday < current_weekday:  # "next" in sentence.lower() or
            return (7 - current_weekday) + set_weekday

        return set_weekday - current_weekday
    if day == "tomorrow":  # or "tomorrow" in sentence:
        return 1
    return 0


def decode_time_sentence(sentence: str) -> dt.datetime | None:
    """Convert senstence from assist into datetime.

    Sentence can be:
        a time only in 12/24h format
        a time with a day of the week or a special day like tomorrow
        an interval like 10 hours and 3 minutes
        a spoken term like half past 6 or tuesday at 20 to 5

    Return None if unable to decode
    """

    # firstly look for a time
    # returns tuple of day, hour, min, sec, am/pm
    set_time = re.findall(REGEX_TIME, sentence)

    # make sure not a super text statement by tesing for to or past in the senstence
    if " to " in sentence.lower() or " past " in sentence.lower():
        set_time = None

    if set_time:
        set_time = list(set_time[0])

        # Set any string ints to int
        for i in range(1, 3):
            if isinstance(set_time[i], str) and set_time[i].isnumeric():
                set_time[i] = int(set_time[i])

        # Get if day or special day in sentence
        # This is a second check incase first REGEX does not detect it.
        if day_text := re.findall(REGEX_DAYS, sentence):
            _LOGGER.info("DAY TEXT: %s", day_text)
            set_time[0] = day_text[0]

        _LOGGER.info("TIME: %s -> %s", sentence, set_time)

        # make into a class object
        time_info = TimerTime(
            day=set_time[0],
            hour=set_time[1],
            minute=set_time[2],
            second=set_time[3],
            meridiem=set_time[4],
        )
        return sentence, time_info

    if int_search := re.search(REGEX_INTERVAL, sentence):
        interval = int_search.groups()
        # interval is tuple in (days, hours, minutes, seconds)
        # make datetime
        if any(interval):
            _LOGGER.info("INTERVAL: %s -> %s", sentence, interval)

            interval_info = TimerInterval(
                days=0 if interval[0] is None else int(interval[0]),
                hours=0 if interval[1] is None else int(interval[1]),
                minutes=0 if interval[2] is None else int(interval[2]),
                seconds=0 if interval[3] is None else int(interval[3]),
            )
            return sentence, interval_info

        # Super text search
        if spec_time := re.findall(REGEX_SUPER_TEXT, sentence):
            set_time = list(spec_time[0])
            _LOGGER.info("SUPER TEXT: %s -> %s", sentence, set_time)

            # return None if not a full match
            if not all(set_time[1:3]):
                return sentence, interval, None

            # Get if day or special day in sentence
            # This is a second check incase first REGEX does not detect it.
            if day_text := re.findall(REGEX_DAYS, sentence):
                _LOGGER.info("DAY TEXT: %s", day_text)
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

            _LOGGER.info("TRANSLATED: %s", set_time)

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

    _LOGGER.info("DECODE: NOT DECODED: %s -> %s", sentence, None)
    return sentence, None


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
    if set_time.meridiem.lower() in ["pm", "tonight"]:
        add_hours = 12

    # Add time context - set for next time 12h time comes around
    # If 20 to 5 and it is 11am, set for 16:40
    # if 20 to 5 and it is 6pm, set for 04:40
    elif context_time and not set_time.meridiem:
        # Set for next 12h time match
        if set_time.hour < (dt_now.hour % 12):
            add_hours = 12
            _LOGGER.info("CONTEXT TIME: Adding %sh", add_hours)

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
        _LOGGER.info("DAY INTERPRETATION: Adding %s days", add_days)
        date = date + dt.timedelta(days=add_days)

    # If time is less than now, add 1 day
    if date < dt.datetime.now():
        _LOGGER.info("ADDING 1 DAY")
        date = date + dt.timedelta(days=1)

    return date


def encode_datetime_to_human(
    timer_type: str, timer_name: str, timer_dt: dt.datetime, h24format: bool = False
) -> str:
    """Encode datetime into human speech sentence."""

    dt_now = dt.datetime.now()
    delta = timer_dt - dt_now
    delta_s = math.ceil(delta.total_seconds())

    if timer_type == "TimerInterval":
        # if less than 60 mins, return mins
        # if delta.total_seconds() < 3600:
        minutes, seconds = divmod(delta_s, 60)
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)

        response = []
        _LOGGER.info(
            "TIMER: %s days %s hours, %s mins, %s secs ", days, hours, minutes, seconds
        )
        if days:
            response.append(f"{days} days")
        if hours:
            response.append(f"{hours} hours")
        if minutes:
            response.append(f"{minutes} minutes")
        if seconds:
            response.append(f"{seconds} seconds")

        duration = ", ".join(response)
        if timer_name:
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
        if timer_name:
            if named_output:
                return f"{timer_name} for {date_text}"
            return f"{timer_name} on {date_text}"
        return date_text

    return timer_dt


class VATimers:
    """Class to handle VA timers."""

    def __init__(self, hass: HomeAssistant, config: ConfigEntry) -> None:
        """Initialise."""
        self.hass = hass
        self.config = config

        self._store = Store[list[Timer]](hass, 1, TIMERS_STORE_NAME)
        self.timers: dict[str, Timer] = {}
        self.timer_tasks: dict[str, Task] = {}

    async def load(self):
        """Load data store."""
        timers: dict[str, Any] = await self._store.async_load()

        # Load timer dict into Timer class objects
        for timer_id, timer in timers.items():
            self.timers[timer_id] = Timer(**timer)

        # Removed any in expired status on restart as event already got fired
        expired_timers = [
            timer_id
            for timer_id, timer in self.timers.items()
            if timer.status == TimerStatus.EXPIRED
        ]
        for timer_id in expired_timers:
            self.timers.pop(timer_id, None)

        for timer_id, timer in self.timers.items():
            await self.start_timer(timer_id, timer)

    async def save(self):
        """Save data store."""
        await self._store.async_save(self.timers)

    def make_unix_time(self, time_or_interval: TimerTime | TimerInterval) -> int:
        """Return unix time from Time or Interval object."""
        if isinstance(time_or_interval, TimerTime):
            return

    def is_duplicate_timer(self, device_id: str, name: str, expires_at: int) -> bool:
        """Return if same timer already exists."""

        # Get timers for device_id
        existing_device_timers = [
            timer_id
            for timer_id in self.timers
            if self.timers[timer_id].device_id == device_id
        ]

        if not existing_device_timers:
            return False

        for timer_id in existing_device_timers:
            timer = self.timers[timer_id]
            if timer.expires_at == expires_at:
                return True
        return False

    async def add_timer(
        self,
        timer_class: TimerClass,
        device_id: str,
        timer_info: TimerTime | TimerInterval,
        name: str | None = None,
        start: bool = True,
        extra_info: dict[str, Any] | None = None,
    ) -> tuple:
        """Add timer to store."""

        # TODO: Make this run only on first instance - part done
        # TODO: Create cancel service
        # TODO: Add cancel
        # TODO: Improve return senstence

        timer_id = ulid_util.ulid_now()

        # calculate expiry time from TimerTime or TimerInterval
        if timer_info.__class__.__name__ == "TimerTime":
            expiry = get_datetime_from_timer_time(timer_info)
        elif timer_info.__class__.__name__ == "TimerInterval":
            expiry = get_datetime_from_timer_interval(timer_info)
        else:
            raise TypeError("Not a valid time or interval object")

        expires_unix_ts = time.mktime(expiry.timetuple())
        time_now_unix = time.mktime(dt.datetime.now().timetuple())

        if not self.is_duplicate_timer(device_id, name, expires_unix_ts):
            # Add timer_info to extra_info
            extra_info["timer_info"] = timer_info

            timer = Timer(
                timer_class=timer_class,
                expires_at=expires_unix_ts,
                name=name,
                device_id=device_id,
                created_at=time_now_unix,
                updated_at=time_now_unix,
                status=TimerStatus.INACTIVE,
                extra_info=extra_info,
            )

            self.timers[timer_id] = timer
            await self.save()

            if start:
                await self.start_timer(timer_id, timer)

            _LOGGER.warning("TIMERS: %s", self.timers)

            encoded_time = encode_datetime_to_human(
                timer_info.__class__.__name__, timer.name, expiry
            )
            return timer_id, timer, encoded_time

        return None, None, "already exists"

    async def start_timer(self, timer_id: str, timer: Timer):
        """Start timer running."""

        time_now_unix = time.mktime(dt.datetime.now().timetuple())
        total_seconds = timer.expires_at - time_now_unix

        # Fire event if total seconds -ve
        # likely caused by tomer expiring during restart
        if total_seconds < 1:
            await self._timer_finished(timer_id)
        else:
            self.timer_tasks[timer_id] = self.hass.async_create_background_task(
                self._wait_for_timer(timer_id, total_seconds, timer.created_at),
                name=f"Timer {timer_id}",
            )
            self.timers[timer_id].status = TimerStatus.RUNNING
            await self.save()
            _LOGGER.info("STARTED %s TIMER FOR %s", timer.name, total_seconds)

    async def _wait_for_timer(
        self, timer_id: str, seconds: int, updated_at: int
    ) -> None:
        """Sleep until timer is up. Timer is only finished if it hasn't been updated."""
        try:
            await asyncio.sleep(seconds)
            if (timer := self.timers.get(timer_id)) and (
                timer.updated_at == updated_at
            ):
                await self._timer_finished(timer_id)
        except asyncio.CancelledError:
            pass  # expected when timer is updated

    async def cancel_timer(
        self,
        timer_id: str | None = None,
        device_id: str | None = None,
        cancel_all: bool = False,
    ) -> bool:
        """Cancel timer by timer id, device id or all."""
        if timer_id:
            timer_ids = [timer_id] if self.timers.get(timer_id) else []
        elif device_id:
            timer_ids = [
                timer_id
                for timer_id, timer in self.timers.items()
                if timer.device_id == device_id
            ]
        elif cancel_all:
            timer_ids = self.timers.keys()

        if timer_ids:
            for timerid in timer_ids:
                if self.timers.pop(timerid, None):
                    if timer_task := self.timer_tasks.pop(timerid, None):
                        if not timer_task.cancelled():
                            timer_task.cancel()
            await self.save()
            return True

        return False

    async def get_timers(self, timer_id: str = "", device_id: str = "") -> list[Timer]:
        """Get list of timers.

        Optionally supply timer_id or device_id to filter the returned list
        """
        if timer_id:
            return {"id": timer_id, "timer": self.timers.get(timer_id)}

        if device_id:
            return [
                {"id": timer_id, "timer": timer}
                for timer_id, timer in self.timers.items()
                if timer.device_id == device_id
            ]
        return [
            {"id": timer_id, "timer": timer} for timer_id, timer in self.timers.items()
        ]

    async def _timer_finished(self, timer_id: str) -> None:
        """Call event handlers when a timer finishes."""
        timer = self.timers[timer_id]

        self.timers[timer_id].status = TimerStatus.EXPIRED
        await self.save()

        self.timer_tasks.pop(timer_id)

        _LOGGER.info("TIMER EXPIRED: %s", timer)

        self.hass.bus.fire(
            VA_TIMER_FINISHED_EVENT,
            {
                "id": timer_id,
                "device_id": timer.device_id,
                "timer_class": timer.timer_class,
                "name": timer.name,
                "created_at": timer.created_at,
                "updated_at": timer.updated_at,
                "expires": timer.expires_at,
                "extra_info": timer.extra_info,
            },
        )
