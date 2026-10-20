# Alexa Voice Events

Generic Alexa voice events for Home Assistant. Select an existing Alexa Devices account and speaker, then use a phrase-to-action Blueprint or ordinary HA automations to decide what happens.

## Development status

This is the **Ticket 01 local implementation**, not a published or hardware-verified release. It supports one selected speaker using the Marshall Uxbridge compatibility profile. The profile is model data; the receiver does not classify household commands. Multiple speakers/accounts, native-reception profiles, options and full account/fault recovery follow in later tickets.

The planned first release is 0.1.0. Public repository creation, HACS distribution, the Traditional Chinese README and CI publication belong to the publication ticket. New Uxbridge/Blueprint hardware acceptance is required before the formal tag/release. Previous-component results do not verify this implementation.

## Current behavior

- Reuse official Alexa Devices authentication and its API instance; no new credentials.
- Preserve native volume processing, using matching pushes as hints for at most two bounded history fetches. No idle cloud polling or manual trial window.
- Repair missing source association only when known device/source keys agree. Unknown/conflicting sources remain rejected by the real upstream parser.
- Publish an event containing recognized text, source and receive times, opaque record/session identity, the HA device and its current reception control.
- A reception switch revokes old work on off/on. Compact sensors expose status, last accepted voice time and a sanitized error code. In this slice, a fetch error stops reception until off/on; automatic account/fault recovery is later work.
- The Blueprint matches literal phrase variants after trimming, lowercasing and collapsing whitespace. Include `alexa` in a configured phrase if it appears in the observed text; no semantic or household intent mapping is performed.
- Queued actions recheck freshness, switch state and session immediately before user actions. Already-running arbitrary user actions are not canceled by the receiver.

Voice events contain text and follow HA recorder policy. There is no additional voice-history store, scene registry, Xiaomi dependency, measurement workflow or music-recovery logic.

## Local use

Use HA Core **2026.10.1** with **aioamazondevices 16.3.2**; unsupported combinations display an unsupported reception state and leave the official integration alone. Install the custom component in an HA development configuration, restart/load it, and add **Alexa Voice Events**. Select the existing account and its supported speaker.

Copy the supplied automation Blueprint into that development configuration's Blueprint collection and reload Blueprints. Create an automation using it, choose the speaker's voice event, enter one phrase per line and select HA actions. The event, switch and diagnostic sensors attach to the upstream physical device. No household automation is installed automatically.

Keep any legacy voice consumer disabled if using replacement household actions. This ticket has not installed files, restarted HA, spoken through a device or modified household settings.

## Tests and typing

The target environment is Python **3.14.5**, HA **2026.10.1**, test plugin **0.13.372** and aioamazondevices **16.3.2**. The lockfile records exact resolved dependencies. The plugin's package metadata explicitly pins the required Core version; tests assert the Core/client versions.

```sh
uv sync --locked
uv run pytest
uv run mypy
uv run ruff check .
uv run ruff format --check .
```

Tests use the real HA config/entity lifecycle and real automation/script engine, with a real upstream coordinator, dispatcher and parser. Only remote history responses and clocks are controlled. The suite disables external sockets; synthetic source identifiers and phrases are not household recordings. These tests prove software behavior, not Amazon delivery, physical action success or other-speaker compatibility.

## License and source

Apache-2.0. No upstream parser fixture is redistributed in this slice: tests execute the pinned installed client with synthetic responses. The source-association repair follows the previous local compatibility behavior, rewritten as an adapter without household dependencies. Upstream code remains covered by its own license: [aioamazondevices 16.3.2](https://github.com/chemelli74/aioamazondevices/tree/v16.3.2) and [HA Core 2026.10.1](https://github.com/home-assistant/core/tree/2026.10.1).
