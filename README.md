# Alexa Voice Events

[繁體中文](README.zh-TW.md)

Generic Alexa voice events for Home Assistant. Select an existing Alexa Devices account and speakers, then use a phrase-to-action Blueprint or ordinary HA automations to decide what happens.

## Release status

**v0.2.0** adds template replies, optional native-reply interruption and read-only
official-target lookup. Source Speak, existing household actions and unmatched
native requests have scoped Marshall Uxbridge hardware evidence. Native
interruption is **unreliable**, and submitted speech may finish before a newer
native answer. Announce, active-media effects and other speakers remain
unverified. See the [hardware report](docs/hardware-acceptance.md) and
[release notes](docs/releases/v0.2.0.md).

## Interruption and replies

Configure phrases, household Actions and a template reply in the Blueprint;
[configuration, API and limits](docs/replies.md) describe the complete flow.
Interruption **defaults on** and may stop music. A blank reply does not disable
Stop. Keep the component and imported Blueprint on the same fixed release;
updating the HACS component does not update an existing Blueprint.

## Installation

Requires **Home Assistant Core 2026.10.2** and its official **Alexa Devices** integration using **aioamazondevices 16.3.2**. Add/authenticate the official integration first. Other Core/client combinations are unsupported until reviewed and tested; do not downgrade Core for this integration.

Choose one installation method:

- **Manual:** download this repository, copy only `custom_components/alexa_voice_events` into your HA configuration's `custom_components/` directory (normally `/config/custom_components/alexa_voice_events`), then restart HA.
- **HACS custom repository:** in HACS → ⋮ → Custom repositories, add `https://github.com/vincent97277/ha-alexa-voice-events` with category **Integration**, download Alexa Voice Events, then restart HA. This project is not in the default HACS store. Install the tagged release for a fixed version; selecting the default branch instead uses changing development code.

In HA → Settings → Devices & services → Add integration, choose **Alexa Voice Events**, select an existing Alexa Devices account and its speakers. Configure reception as described below. No additional Amazon login is needed.

The release targets Core 2026.10.2. Download [v0.2.0](https://github.com/vincent97277/ha-alexa-voice-events/releases/tag/v0.2.0), or its [source archive](https://github.com/vincent97277/ha-alexa-voice-events/archive/refs/tags/v0.2.0.zip) for manual installation. Record the installed tag/commit separately from the manifest version. Python runtime files and the Blueprint match hardware-tested candidate `e5fd040`; the component manifest version is now 0.2.0. The candidate was manually installed; that is separate from installing this release through HACS. Keep the [v0.1.0 source](https://github.com/vincent97277/ha-alexa-voice-events/releases/tag/v0.1.0) and actual prior Blueprint/automation backups for rollback; see [migration and rollback](docs/replies.md#migration-and-rollback). The older `4944eea` Core 2026.10.1 baseline is historical; see [compatibility review](docs/compatibility.md).

## Blueprint

Open HA → Settings → Automations & scenes → Blueprints → Import Blueprint and paste:

```text
https://github.com/vincent97277/ha-alexa-voice-events/blob/v0.2.0/blueprints/automation/alexa_voice_events/phrase_to_action.yaml
```

Importing the Blueprint is independent of installing the integration. Create an automation from it, select the speakers' voice event entities, enter one literal phrase per line, and choose HA actions. Installing/importing creates no household automation automatically. Use ordinary HA automations for more complex rules; official Alexa Devices actions remain available in HA. Disable overlapping legacy consumers when switching household actions to this integration to avoid duplicate actions.

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

## Reception settings

Use HA Core **2026.10.2** with **aioamazondevices 16.3.2**; unsupported combinations display an unsupported reception state and leave the official integration alone. Select the existing account and one or more voice-capable speakers, then review each speaker’s reception method. Add another integration entry for another existing account; cross-account selections and duplicate account entries are rejected.

Use the integration’s **Configure** options to add/remove speakers or change methods. `native` observes official Alexa Devices history updates; `volume_push` uses matching speaker pushes to fetch history. Only the necessary method and opt-in choices are exposed; scheduling limits stay internal.

The Marshall Uxbridge profile suggests `volume_push` using the documented Uxbridge checks. It starts enabled when first selected; this does not verify another physical speaker or another method. Unknown speakers default to `native`; they and overrides of a known profile’s suggested method stay disabled until **Explicitly allow this unverified speaker / method** is checked. A reception switch cannot bypass this opt-in. Tests/selection never promote a device to verified. The status sensor exposes `method` and `validation_scope` (`uxbridge_volume_push` or `unverified`). Hardware scope is recorded in the [acceptance report](docs/hardware-acceptance.md), rather than a hardcoded pending flag in every installation.

Create an automation using it, choose one or more speakers’ voice events, enter one phrase per line and select HA actions. The event, switch and diagnostic sensors attach to the upstream physical device. No household automation is installed automatically.

The v0.2.0 runtime was exercised as the fixed, manually installed candidate; the report distinguishes that from the earlier v0.1.0 HACS installation. See the acceptance report for exact builds and limits. For troubleshooting, inspect reception status/error diagnostics first, then report the Core/client versions and reproduction steps through [issues](https://github.com/vincent97277/ha-alexa-voice-events/issues); redact voice text and account/device identifiers.

## Tests and typing

The target environment is Python **3.14.6**, HA **2026.10.2**, test plugin **0.13.373** and aioamazondevices **16.3.2**. The lockfile records exact resolved dependencies. The plugin's package metadata explicitly pins the required Core version; tests assert the Core/client versions.

```sh
uv sync --locked
uv run pytest
uv run mypy
uv run ruff check .
uv run ruff format --check .
```

Recovery tests exercise actual HA account unload/setup, API replacement with late callbacks, per-speaker availability/method changes, restore-storage startup, queue revocation after account rebind, timeout/backoff, ownership conflicts and unsupported paths. Tests cover multiple accounts (including equal raw speaker identifiers), same-name speakers, native and compatibility methods, opt-in, targeted selection changes, concurrent switch persistence, rename/device association, bounded cross-speaker handoff and queued Blueprint source snapshots. Tests use the real HA config/entity lifecycle and real automation/script engine, with a real upstream coordinator, dispatcher and parser. Remote history responses, clocks and the official Stop/notify service boundaries are controlled; Amazon speaker calls are not executed. The suite disables external sockets; synthetic source identifiers and phrases are not household recordings. These tests prove software behavior, not Amazon delivery, physical action success or other-speaker compatibility.

## License and source

Apache-2.0. No upstream parser fixture is redistributed in this slice: tests execute the pinned installed client with synthetic responses. The source-association repair follows the previous local compatibility behavior, rewritten as an adapter without household dependencies. Upstream code remains covered by its own license: [aioamazondevices 16.3.2](https://github.com/chemelli74/aioamazondevices/tree/v16.3.2) and [HA Core 2026.10.2](https://github.com/home-assistant/core/tree/2026.10.2).
