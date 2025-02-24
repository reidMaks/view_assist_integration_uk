# Timers

The timer functionality is designed to handle timers, alarms, reminders and scheduled commands, managed via voice.

Upon expiration of the timer, an event is fired with the timer details.
Equally, prior to the expiration of the timer, an expiry warning event is fired to allow for a countdown to expiry.  This is default set at 10 seconds before but can be set in the `set_timer` service on timer creation.

The following services are available

## Set Timer

This service creates the timer and provides a response.

#### Service Name
view_assist.set_timer
#### Parameters
 - `device_id` (required) - this is the device id of the voice device which was passed in the sentence
 - `type` (required) - this is the type of timer (alarm, timer, reminder, command)
 - `name` (optional) - a name for the timer
 - `time` (required) - a time sentence - see below for examples of supported sentences
 - `extra` (optional) - accepts key/value pairs of any additional data to be stored with the timer and available in the timer info on the va entity attributes and in any timer events.

#### Service Response
Returns the timer data and a sentence that can be used for a conversation response that is the interpretation of the requested time.

```json
timer_id: 01JMWN5DBFPVEDT6H0SNXBJW3C
timer:
  device_id: 4a3389dfdc31e0c0fe451396ea741118
  timer_class: reminder
  timer_type: TimerTime
  name: Pick up the kids
  expires: "2025-02-25T16:00:00"
  original_expiry: "2025-02-25T16:00:00"
  pre_expire_warning: 10
  expires_in_seconds: 75724
  expires_in_interval:
    days: 0
    hours: 21
    minutes: 2
    seconds: 4
  expires_in_text: tomorrow at 4:00 PM
  created_at: "2025-02-24T18:57:56"
  updated_at: "2025-02-24T18:57:56"
  status: running
  extra_info:
    sentence: tuesday at 4:00 pm
    timer_info:
      day: tuesday
      hour: 4
      minute: 0
      second: 0
      meridiem: pm
    view_assist_entity_id: sensor.display_test
response: Pick up the kids for tomorrow at 4:00 PM
```

## Cancel Timer
This service cancels 1 or more timers and provides a response to confirm if timers were cancelled.

#### Service Name
view_assist.cancel_timer
#### Parameters
 - `timer_id` (optional) - this is the id of the individual timer you wish to cancel
 - `device_id` (optional) - this is the device id of the voice device which was passed in when the timer was created.  This will cancel all timers for that device id.
 - `remove_all` (optional) - this will delete all timers

#### Response
```json
result: true
```

## Snooze Timer
This service snoozes an expired timer and reschedules it to fire again later.  It returns the updated timer if successful with the snooze information in the extra_info key.

#### Service Name
view_assist.snooze_timer
#### Parameters
 - `timer_id` (required) - this is the id of the individual timer you wish to cancel
 - `time` (required) - a time sentence - see below for examples of supported sentences

#### Response
```json
timer_id: 01JMWMYR7YQ1GVTT2TYBQM21Q6
timer:
  device_id: 4a3389dfdc31e0c0fe451396ea741118
  timer_class: timer
  timer_type: TimerInterval
  name: ""
  expires: "2025-02-24T19:04:57"
  original_expiry: "2025-02-24T18:54:28"
  pre_expire_warning: 10
  expires_in_seconds: 600
  expires_in_interval:
    days: 0
    hours: 0
    minutes: 10
    seconds: 0
  expires_in_text: 10 minutes
  created_at: "2025-02-24T18:54:18"
  updated_at: "2025-02-24T18:54:57"
  status: snoozed
  extra_info:
    sentence: 10 seconds
    timer_info:
      days: 0
      hours: 0
      minutes: 0
      seconds: 10
    view_assist_entity_id: sensor.display_test
    snooze_duration:
      days: 0
      hours: 0
      minutes: 10
      seconds: 0
response: 10 minutes

```

## Get Timers
This service retrieves a list of timers.  With no parameters it will return all active timers

#### Service Name
view_assist.get_timers
#### Parameters
 - `timer_id` (optional) - this is the id of the individual timer you wish to view
 - `device_id` (optional) - this is the device id of the voice device which was passed in when the timer was created.  This will return all timers for that device id.
 - `include_expired` (optional) - this will include/exclude expired timers

#### Response
```json
result:
  - id: 01JMWK41PTEZ2JFKD9FSFERHRR
    device_id: 4a3389dfdc31e0c0fe451396ea741118
    timer_class: reminder
    timer_type: TimerTime
    name: do the chores
    expires: "2025-02-25T14:30:00"
    original_expiry: "2025-02-25T14:30:00"
    pre_expire_warning: 10
    expires_in_seconds: 70612
    expires_in_interval:
      days: 0
      hours: 19
      minutes: 36
      seconds: 52
    expires_in_text: tomorrow at 2:30 PM
    created_at: "2025-02-24T18:22:14"
    updated_at: "2025-02-24T18:22:14"
    status: running
    extra_info:
      sentence: 14:30 tomorrow
      timer_info:
        day: tomorrow
        hour: 14
        minute: 30
        second: 0
        meridiem: ""
      view_assist_entity_id: sensor.display_test
  - id: 01JMWKVP7PXDZ38MD6CV62NYW3
    device_id: 4a3389dfdc31e0c0fe451396ea741118
    timer_class: alarm
    timer_type: TimerTime
    name: ""
    expires: "2025-02-25T23:30:00"
    original_expiry: "2025-02-25T23:30:00"
    pre_expire_warning: 10
    expires_in_seconds: 103012
    expires_in_interval:
      days: 1
      hours: 4
      minutes: 36
      seconds: 52
    expires_in_text: tomorrow at 11:30 PM
    created_at: "2025-02-24T18:35:09"
    updated_at: "2025-02-24T18:35:09"
    status: running
    extra_info:
      sentence: 11:30 pm on tuesday
      timer_info:
        day: tuesday
        hour: 11
        minute: 30
        second: 0
        meridiem: pm
      view_assist_entity_id: sensor.display_test

```

## Events

The timer will raise an event for the following statuses:

- Timer Started

- Timer Cancelled

- Timer Warning

- Timer Expired

- Timer Snoozed

All event names are:

`va_timer_[action]` - for alarms, timers, reminders

or

`va_timer_command_[action]` - for command timers

where [action] is one of started, cancelled, warning, expired, snoozed

## Outstanding TODOs
- Create an expired timer clean up routine - they are currently only deleted by timer_cancel and restart of HA
- Allow setting of timer expiry warning event when setting timer
