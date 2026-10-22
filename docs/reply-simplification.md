# Simplified replies (unreleased)

This describes the development Blueprint, not the published v0.2.0 Blueprint.
The short-phrase playback failure is still under investigation. Passing software
tests does not establish reliable speaker playback. A Blueprint-only candidate
installation has [scoped Uxbridge checks](hardware-simplified-replies.md); native
interruption and the earlier matched-Speak failure remain unresolved.

## Configure without a template

1. Select the speakers' voice event entities and literal recognized phrases. Use
   the [phrase guide](recognized-phrases.md) to verify what Alexa actually heard.
2. Set your household Actions, or leave them empty for a query.
3. Select **Sensors to report**, for example your temperature and humidity sensors.
4. Leave **Reply message** blank.

The reply uses recorded HA values after Actions and always requests normal Speak
on the speaker that produced this event. There is no Reply speaker or Reply mode
input. A typical generated message is:

> Home Assistant reports: Room temperature is 22.1 °C; Room humidity is 43 %.

Names and units come from your sensors. No brand, room or sensor entity is built
into the integration. Missing/unknown/unavailable values, non-finite values and
invalid numeric measurements are described as unavailable; real zero is valid.
Unitless sensors with a numeric state class (measurement, total or total_increasing)
also require a finite number. Other sensors without a unit can report their text state. The generator does not
convert units, round readings, translate names or claim a sensor sampling time.
Use Reply message for different wording or formatting.

If you want silence, clear both **Sensors to report** and **Reply message**. The
interruption switch is independent: it still defaults on. Sensor reports use
English wording; sensor names come from HA and may use another language.

## Custom replies

A nonblank **Reply message** overrides the sensor report. Examples:

- Fixed text: `The fridge is in the kitchen.`
- Template: `Home Assistant reports {{ states('sensor.example_value') }}.`

For numeric validation and custom missing-value wording, copy the
[measurement template](replies.md#adapt-a-sensor-query-without-changing-the-integration)
and replace its example entity. With no selected sensors and a blank message,
no custom speech is requested. Stop is controlled separately.

## Updating existing automations

Back up the actual imported Blueprint and all affected automation configurations
before replacing the Blueprint. Saved `reply_device` and `reply_mode` inputs no
longer select another speaker or Announce: every Blueprint reply uses source
Speak. Review automations that previously depended on those options. Ordinary
HA actions and the advanced read-only resolver API remain available.

The v0.2.0 release tag is unchanged. Do not treat its hardware acceptance as
validation of this development Blueprint. Service completion still does not prove
that Amazon accepted or played the speech, or that native follow-up stopped.

## Scope of this change

This is a Blueprint interface change. The read-only target resolver keeps its
existing API for ordinary HA automations. There is no new Amazon login, speech
recognizer, transcript correction, playback retry or fixed delay. See the
[phrase troubleshooting guide](recognized-phrases.md) before treating missing
speech as a playback failure.
