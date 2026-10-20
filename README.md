# Alexa Voice Events

Generic Alexa voice events for Home Assistant. Select an existing Alexa Devices account and speakers, then use a phrase-to-action Blueprint or ordinary HA automations to decide what happens.

## Development status

This is the **Ticket 03 local implementation**, not a published or hardware-verified release. Each official Alexa account has at most one entry with multiple selected speakers. Native upstream updates and push-triggered compatibility share the same generic event contract. HA options support selection and method changes without reloading unaffected speakers. Enabled reception now waits for the selected account and recovers through availability changes, API replacement and reload using fresh sessions.

The planned first release is 0.1.0. Public repository creation, HACS distribution, the Traditional Chinese README and CI publication belong to the publication ticket. New Uxbridge/Blueprint hardware acceptance is required before the formal tag/release. Previous-component results do not verify this implementation.

## Current behavior

- Reuse official Alexa Devices authentication and its API instance; no new credentials.
- Native reception observes the existing coordinator and uses genuine Amazon record timestamps; it never manufactures source times from HA state changes.
- Compatibility preserves native volume processing and shares one fetch worker per account. A pending hint gets at most two attempts, each with a twenty-second timeout. Each dispatch has at most two requests; pending sources that arrive during the final attempt receive a turn after a one-second cooldown. Overlapping hints keep their source identities and finite attempt budget. There is no idle history polling or manual trial window.
- Repair missing source association only when known device/source keys agree. Unknown/conflicting sources remain rejected by the real upstream parser.
- Publish an event containing recognized text, source and receive times, opaque record/session identity, the HA device and its current reception control.
- Each speaker has its own reception switch, session and diagnostic sensors. Off/on, removal and method changes revoke that speaker’s previous publication/action authority; other speakers keep their sessions. Switch intent persists independently of the options editor, so concurrent toggles and an open options form do not overwrite it. Fetch failures defer further compatibility work by 30/60/120/240 seconds, capped at 240 seconds. Before five consecutive failures the status is `waiting` during backoff; at five it becomes `error`. A later matching push can retry after the deadline; a successful fetch, including an empty one, resets the budget. Failed hints are discarded; there is no autonomous retry history polling. Native reception remains independent.
- The Blueprint matches literal phrase variants after trimming, lowercasing and collapsing whitespace. Include `alexa` in a configured phrase if it appears in the observed text; no semantic or household intent mapping is performed.
- Queued actions recheck freshness, switch state and session immediately before user actions. Already-running arbitrary user actions are not canceled by the receiver. HA automation mode is user-editable: open the created automation in YAML and override `mode` (default `queued`) and `max` (default `10`) to suit your action sequence.

Account observation uses public HA entry-state notifications and a five-second check of local account/API identity. It never opens a second connection or polls history to detect recovery. Account loss/rebind revokes sessions before removing owned hooks/listeners and canceling/awaiting owned work. A missing/offline speaker revokes only its own session. Disabled intent remains disabled after startup and reload; recently restored voice attributes cannot create an action. Already-running user actions remain HA's responsibility. If a platform refuses unload, reception resumes with fresh authority and only successfully unloaded platforms are restored. HA still reports the failed unload and may require a restart; local resources are also cleaned on HA shutdown.

Reception status distinguishes `disabled`, `ready`, `waiting`, `error` and `unsupported`; `ready` means local readiness, not guaranteed Amazon delivery. Diagnostic errors are fixed codes, never raw exception text. Compatibility diagnostics expose `consecutive_failures` and a UTC `retry_at`; empty fetches never advance the last received voice timestamp. `account_not_ready`/`account_unavailable`/`speaker_not_available` wait for the selected source. `unsupported_version` requires source review and tests for the installed Core/client combination; do not downgrade Core to satisfy this integration. `unsupported_structure` or `ownership_conflict` stops the affected path and leaves other reception methods and the official integration alone. Resolve competing hooks or changed upstream interfaces before reloading this integration. Only hooks still owned by this instance are restored.

Voice events contain text and follow HA recorder policy. There is no additional voice-history store, scene registry, Xiaomi dependency, measurement workflow or music-recovery logic.

## Local use

Use HA Core **2026.10.1** with **aioamazondevices 16.3.2**; unsupported combinations display an unsupported reception state and leave the official integration alone. Install the custom component in an HA development configuration, restart/load it, and add **Alexa Voice Events**. Select the existing account and one or more voice-capable speakers, then review each speaker’s reception method. Add another integration entry for another existing account; cross-account selections and duplicate account entries are rejected.

Use the integration’s **Configure** options to add/remove speakers or change methods. `native` observes official Alexa Devices history updates; `volume_push` uses matching speaker pushes to fetch history. Only the necessary method and opt-in choices are exposed; scheduling limits stay internal.

The Marshall Uxbridge profile suggests `volume_push` using **legacy Uxbridge evidence**. It starts enabled when first selected, without claiming new hardware acceptance. Unknown speakers default to `native`; they and overrides of a known profile’s suggested method stay disabled until **Explicitly allow this unverified speaker / method** is checked. A reception switch cannot bypass this opt-in. Tests/selection never promote a device to verified. The status sensor exposes `method`, `validation_scope` (`legacy_uxbridge` or `unverified`) and `new_hardware_acceptance: pending`.

Copy the supplied automation Blueprint into that development configuration's Blueprint collection and reload Blueprints. Create an automation using it, choose one or more speakers’ voice events, enter one phrase per line and select HA actions. The event, switch and diagnostic sensors attach to the upstream physical device. No household automation is installed automatically.

Keep any legacy voice consumer disabled if using replacement household actions. This ticket has not installed files, restarted live HA, spoken through a device or modified household settings. The development selection format changed after Ticket 01; recreate any disposable Ticket 01 test entry when trying this pre-release build.

## Tests and typing

The target environment is Python **3.14.5**, HA **2026.10.1**, test plugin **0.13.372** and aioamazondevices **16.3.2**. The lockfile records exact resolved dependencies. The plugin's package metadata explicitly pins the required Core version; tests assert the Core/client versions.

```sh
uv sync --locked
uv run pytest
uv run mypy
uv run ruff check .
uv run ruff format --check .
```

Recovery tests exercise actual HA account unload/setup, API replacement with late callbacks, per-speaker availability/method changes, restore-storage startup, queue revocation after account rebind, timeout/backoff, ownership conflicts and unsupported paths. Tests cover multiple accounts (including equal raw speaker identifiers), same-name speakers, native and compatibility methods, opt-in, targeted selection changes, concurrent switch persistence, rename/device association, bounded cross-speaker handoff and queued Blueprint source snapshots. Tests use the real HA config/entity lifecycle and real automation/script engine, with a real upstream coordinator, dispatcher and parser. Only remote history responses and clocks are controlled. The suite disables external sockets; synthetic source identifiers and phrases are not household recordings. These tests prove software behavior, not Amazon delivery, physical action success or other-speaker compatibility.

## License and source

Apache-2.0. No upstream parser fixture is redistributed in this slice: tests execute the pinned installed client with synthetic responses. The source-association repair follows the previous local compatibility behavior, rewritten as an adapter without household dependencies. Upstream code remains covered by its own license: [aioamazondevices 16.3.2](https://github.com/chemelli74/aioamazondevices/tree/v16.3.2) and [HA Core 2026.10.1](https://github.com/home-assistant/core/tree/2026.10.1).
