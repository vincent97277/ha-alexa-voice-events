<p align="center"><img src="custom_components/alexa_voice_events/brand/icon.png" alt="Alexa Voice Events icon" width="160"></p>

# Alexa Voice Events

[繁體中文](README.zh-TW.md)

Use what Alexa heard to run Home Assistant actions and speak HA information back
on the same speaker. Reuse an existing **Alexa Devices** account; no second Amazon
login, Custom Skill or separate voice-history database is required.

**Alexa recognition → voice event → your HA automation → optional spoken reply.**
Household rules stay in HA. This is a community integration, not an official Amazon
or Home Assistant integration.

[Install](#installation) · [Configure](#configuration) · [Blueprint](#blueprint) ·
[Phrase tips](#recognized-phrases) · [FAQ](#faq) · [Update](#updates-and-rollback)

## Requirements

- Home Assistant Core **2026.10.2** with official **Alexa Devices** configured and
  authenticated; its client must be **aioamazondevices 16.3.2**.
- A speaker belonging to that account. Marshall Uxbridge has
  [scoped hardware evidence](docs/hardware-simplified-replies.md); other speakers
  and reception methods require explicit unverified opt-in.
- Other Core/client combinations need review and tests. Do not downgrade Core to
  satisfy this integration. See [compatibility](docs/compatibility.md).

## Installation

Choose one method, then restart HA:

| Method | Steps |
| --- | --- |
| HACS custom repository | HACS → ⋮ → Custom repositories → add `https://github.com/vincent97277/ha-alexa-voice-events`, category **Integration** → download Alexa Voice Events **v0.3.1**. This repository is not in the default HACS store. |
| Manual | Download the [v0.3.1 source ZIP](https://github.com/vincent97277/ha-alexa-voice-events/archive/refs/tags/v0.3.1.zip). Copy only `custom_components/alexa_voice_events` into your HA configuration's `custom_components/` directory, normally `/config/custom_components/alexa_voice_events`. Include its `brand` directory. |

## Configuration

1. Open **Settings → Devices & services → Add integration → Alexa Voice Events**.
2. Select an existing Alexa Devices account and one or more speakers. Each account
   has one AVE entry; add another entry for another account.
3. Review reception methods in **Configure**. Uxbridge suggests `volume_push`;
   unknown speakers default to `native` and require **Explicitly allow this
   unverified speaker / method** before enabling. Overriding a known profile's
   suggested method also requires opt-in.
4. Each selected speaker gets a voice event, reception switch and diagnostics on
   its existing HA device. `ready` means locally ready, not guaranteed delivery.
   Turning reception off prevents new managed actions; re-enabling does not replay
   old commands.

`native` observes official integration updates; `volume_push` uses a matching push
to fetch history. There is no continuous idle history polling. Details belong in
[reception architecture](docs/architecture.md).

## Blueprint

Install the integration first. In **Settings → Automations & scenes → Blueprints →
Import Blueprint**, paste this fixed-version URL:

```text
https://github.com/vincent97277/ha-alexa-voice-events/blob/v0.3.1/blueprints/automation/alexa_voice_events/phrase_to_action.yaml
```

[View / download Blueprint](https://github.com/vincent97277/ha-alexa-voice-events/blob/v0.3.1/blueprints/automation/alexa_voice_events/phrase_to_action.yaml).
Create an automation from it and configure the following six inputs. Installing or
importing alone creates no household automation. Each input includes a **Help**
link back to its explanation here.

### Speakers' voice event entities

Select one or more **Alexa Voice Events event entities**, not media players.
Replies always use normal **Speak on the speaker that produced the event**.
No speaker serial number or reply-mode setting is needed.

### Recognized phrases

Enter **one phrase per line, without the leading `alexa`**. Say your normal wake
word aloud; it does not belong in the configured phrase.

Good starting examples, to connect to your own actions or sensors:

```text
turn the bedroom lights on
turn the bedroom lights off
tell me the bedroom temperature
```

Use different automations for different actions. These are examples, not built-in
commands or guaranteed recognition results.

Matching ignores case, repeated whitespace and **one leading standalone `alexa`**
on either side. Existing phrases with `alexa` keep working; you do not need two
lines. Event `voice_command` stays unchanged for diagnosis. The prefix must be
separated by whitespace: `Alexa, ...` retains its comma and is not this exception.

Everything else is literal: punctuation, spelling and suffixes matter. Start with
phrases without punctuation, then verify the actual `voice_command`. For example,
`light on, please` matches only if the recognized text also contains the comma;
`light on please` does not match it. The integration does not fix bridge to fridge,
remove Alexa in the middle, strip other wake words or infer intent.

**Recognition tips.** In our tests, fridge sometimes became bridge. A complete,
relevant sentence can provide useful context, so try `where is the fridge` instead
of the isolated word `fridge`, or `turn the bedroom lights on` instead of `light on`.
This may help recognition; longer phrases and filler words are not a guarantee,
and adding phrases in HA does not train Alexa. [Evidence and troubleshooting](docs/recognized-phrases.md).

**Optional experiment: `never mind`.** Some users may try a suffix such as
`turn the bedroom lights on never mind` to reduce native interaction. If you use
it, configure the full text actually recognized, including that suffix. It can
also be interpreted as cancellation or change the transcript; there is no guarantee
that it suppresses Alexa while preserving the HA command. Do not assume a separate
cancel request leaves queued work intact. [Amazon's CancelIntent documentation](https://developer.amazon.com/en-US/docs/alexa/custom-skills/standard-built-in-intents.html)
concerns Custom Skills and does not establish this same-utterance technique here.

### Attempt to interrupt the native reply

**On by default.** For a matched, authorized event, attempt to stop the source
speaker before your Actions. **It can stop music too.** Turn it off where unwanted.

This integration observes recognized history instead of taking over Alexa's
[Custom Skill interaction model](https://developer.amazon.com/en-US/alexa/alexa-skills-kit/get-deeper/custom-skills).
Alexa may still answer or ask follow-up questions. Push/history availability,
HA processing and the network add delay; interruption may take several seconds.
Three seconds is not a fixed delay, minimum or guarantee. A returned Stop action
is not proof that Alexa ended the conversation.

### Sensors to report

Select sensors, such as temperature and humidity, and leave **Reply message** blank.
The Blueprint's built-in template generates a report after your Actions:

> Home Assistant reports: Room temperature is 22.1 °C; Room humidity is 43 %.

It uses HA's current recorded names, values and units. Names can be in your own
language; report wording is English. It does not translate names, convert units,
round values or claim a fresh sensor sampling time. Missing/invalid measurements
are reported as unavailable; real zero remains valid. General text sensors can
report their text. Use Reply message for custom formatting.

### Reply message

Optional fixed text or an HA template. **A nonblank custom message takes priority
over Sensors to report.** Both inputs can be configured, but only the custom
message is used. Clear both for no HA speech; interruption remains independent.

- Fixed text: `The fridge is in the kitchen.`
- Template: `Home Assistant reports {{ states('sensor.example_value') }}.`

Replace the example entity with your own. Prefer the sensor selector for ordinary
readings; it already handles unavailable measurements. For custom numeric wording,
use the [validated measurement template](docs/replies.md#adapt-a-sensor-query-without-changing-the-integration)
rather than converting missing readings to zero. Preview templates in HA's template
editor. Values are read after Actions, not frozen at trigger time.

### Actions

Choose your usual HA actions, for example turning on selected lights or running a
script. A sensor-only query can leave this empty. The request order is:
**attempt source Stop → your Actions → optional source Speak**.

Avoid overlapping phrase automations, including phrases now equivalent after
removing Alexa. A matching phrase on several lines runs that automation once;
separate matching automations still each run. Each managed step checks current
reception, session, event identity and a fifteen-second deadline. A newer event
from that speaker supersedes pending old work. Already-running Actions and
commands submitted to Amazon cannot be recalled. [Detailed behavior](docs/replies.md).

## Updates and rollback

Keep the component and imported Blueprint on the **same fixed release**.
**Updating HACS does not update an existing Blueprint.** Save the actual component,
Blueprint path/content and all consumers' configurations/enabled states before
replacing them; validate and enable one consumer at a time.

v0.3.1 accepts existing prefixed phrases. You may remove redundant variants after
checking for equivalent phrases across automations. Earlier `reply_device` and
`reply_mode` options were removed in v0.3.0; review consumers that relied on them.
For rollback, restore the saved sources and complete settings; the
[v0.3.0 release](https://github.com/vincent97277/ha-alexa-voice-events/releases/tag/v0.3.0)
remains available. [Full migration / rollback](docs/replies.md#migration-and-rollback).

## FAQ

**Does this replace Alexa or improve its recognizer?** No. Amazon still recognizes
speech and may handle it natively. AVE publishes the text for HA rules.

**Nothing happened. Where should I look?** Check reception diagnostics, a new event's
`voice_command` and source time, then the automation trace. No new event is not by
itself proof of a missing transcript. See the [phrase guide](docs/recognized-phrases.md).

**Can HA reply on another speaker?** The supplied Blueprint uses the source speaker.
For advanced routing, use ordinary HA actions and the [target lookup API](docs/replies.md#read-only-target-lookup-for-ordinary-ha-automations).

**Does every queued command run?** No. Expired, superseded or revoked work is rejected.
HA's `queued` mode is local to each automation; it is not a global speaker lock.
Change `mode`/`max` in your created automation YAML if needed (defaults: queued / 10).

## Privacy, development and license

Voice events contain recognized text and follow HA recorder policy. There is no
extra voice-history store. Redact voice text, credentials and account/device IDs
when [reporting an issue](https://github.com/vincent97277/ha-alexa-voice-events/issues).

[Architecture](docs/architecture.md) · [Development / tests](docs/development.md) ·
[Release notes](docs/releases/v0.3.1.md) · [Hardware scope](docs/hardware-simplified-replies.md)

[Apache-2.0](LICENSE) · [Third-party notices and icon provenance](NOTICE)
