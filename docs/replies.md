# Interruption and replies (v0.3.1)

Use the v0.3.1 component and Blueprint together. Earlier reply behavior has
[scoped Uxbridge checks](hardware-simplified-replies.md); v0.3.1 adds prefix matching
and field Help links without new hardware acceptance. The user confirmed the prior
audio investigation resolved and closed. Already-submitted speech cannot be recalled.

## Configure an automation

Use a component checkout and imported Blueprint from the **same fixed commit**.
Updating the HACS component does not update an imported Blueprint. Before replacing
an imported Blueprint, save its actual content and the affected automations.

Keep your voice-event selection and household Actions; review recognized phrases
against actual `voice_command` values. The standard reply setup is:

- **Attempt to interrupt the native reply:** on by default; attempts source Stop
  only for matched, authorized events, and may stop music. Disable where unwanted.
- **Sensors to report:** optionally select one or more sensors; with blank Reply
  message, generate a report from their HA-recorded values after Actions.
- **Reply message:** optional text or HA template, evaluated after Actions. A
  nonblank custom reply overrides selected sensors. Clear both inputs for silence.
- Replies always use normal **Speak on the source speaker**. Reply speaker and
  Reply mode inputs have been removed. Saved `reply_device`/`reply_mode` no longer
  change this behavior; adjust consumers that depended on another device or Announce.

See [simple sensor setup](reply-simplification.md) for generated report examples,
units, text states and unavailable readings. No household brand or room is built in.
The advanced resolver API below remains available for ordinary HA automations.

### Adapt a sensor query without changing the integration

Create an automation from the matching Blueprint. Select your voice event entities,
enter the recognized phrases without a leading Alexa (old prefixed entries still work),
and leave Actions empty if the automation only answers a question. Select sensors and leave Reply message blank for the generated report, or paste a
custom template into Reply message for your own wording. Replies use the triggering speaker.
For example, replace the placeholder entity in this template with your own:

```jinja
{% set entity = 'sensor.example_measurement' %}
{% set value = states(entity) %}
{% set unit = state_attr(entity, 'unit_of_measurement') %}
{% if is_number(value) and unit %}
Home Assistant reports {{ value }} {{ unit }}.
{% else %}
The recorded measurement is currently unavailable in Home Assistant.
{% endif %}
```

This is household wording, not a built-in intent or sensor policy. Choose your own
unit conversion, precision and missing-value wording. Check validity before numeric
conversion; do not turn unknown, unavailable, absent or non-finite values into zero.
Zero itself can be a valid reading. For several sensors, answer the available parts
and explicitly describe missing parts. A unit mismatch must not be relabelled as
another unit. HA state timestamps are not necessarily sensor sampling timestamps;
use “Home Assistant reports” unless a trustworthy source supplies sampling time.

Preview the template in HA's template editor without assigning fake states to live
sensors. A successful preview is not evidence that Alexa spoke, stopped its native
reply or delivered the message.

The call order is Stop on the source, your Actions, then optional Speak on that
same source. Templates read the data after Actions, not at
trigger time. Strings and finite numbers become text; null or whitespace is not
spoken. Lists, mappings, booleans and other invalid reply results do not become
spoken dumps. Template errors do not undo already-completed household effects.

## Migration and rollback

1. Save the actual component directory, imported Blueprint file/path and every
   affected automation's complete config and enabled state. Keep backups private.
2. Review old `reply_device` and `reply_mode` settings. The v0.3.0 Blueprint always
   uses source Speak, so explicitly redesign any cross-speaker/Announce consumers
   with ordinary HA actions before switching; do not silently assume old routing.
3. Disable affected/overlapping consumers. Install the v0.3.1 component, restart HA
   if replacing component files, and separately replace the Blueprint from the
   [same tag](https://github.com/vincent97277/ha-alexa-voice-events/blob/v0.3.1/blueprints/automation/alexa_voice_events/phrase_to_action.yaml)
   at the original import path. HACS does not update imported Blueprints.
4. Existing prefixed phrases remain valid. Review equivalent phrases across
   automations before removing redundant variants; general punctuation is still literal.
   Remove obsolete reply-device/mode inputs. Select sensors for an automatic report,
   or retain your custom Reply message; the new sensor input defaults empty. Keep
   Stop explicitly false where unwanted. Validate, reload, read back installed
   sources/configs and enable consumers individually; verify their actual effects.
5. To roll back, disable affected consumers and restore the saved component,
   original Blueprint at its original path and complete configs/enabled states.
   [v0.3.0](https://github.com/vincent97277/ha-alexa-voice-events/releases/tag/v0.3.0)
   remains available. A Blueprint-only candidate trial requires only that file and
   its consumer configs/states to be restored; don't perform a full HA restore.
6. Restart only if restoring component files, validate/reload, then check reception
   and original phrases. Preserve official login and unrelated household services.
   Check Core/client compatibility before restoring; do not downgrade Core or assume
   already-submitted Amazon commands can be recalled.

## Fresh work only

The Blueprint snapshots the triggering envelope. Before each managed step it
checks the current source/device and event identity, reception control/session,
current account binding, and both source and received ages below fifteen seconds
with no future times. A newer published event from the same speaker supersedes
older work even when its phrase is unmatched. Another source does not revoke it.
Closing reception, changing sessions or reloading never replays the old work.

An already-running user Actions sequence is not forcibly stopped or rolled back.
After it returns, authorization is checked again. A twenty-second Actions sequence
can complete its household effects while its old reply is discarded. The fifteen
seconds are a **start-next-step deadline**, not a service or playback timeout.

Queued mode remains local to the automation. A multi-source automation shares
one queue; independent automations do not share a speaker lock. Avoid overlapping
phrase consumers. Identical words in a new valid event are still a new utterance.

## Failures and honest outcomes

- Invalid source authority, supersession or expiration discards all remaining
  managed steps. It is not a recoverable Stop failure.
- A missing Stop target or visible Stop error does not prevent authorized Actions
  and a reply. An unhandled Actions error skips the planned reply.
- Missing/ambiguous/unavailable reply targets, invalid reply text and visible
  notify errors do not reroute, retry or undo household actions.
- Each run makes at most one managed Stop and one managed notify call. No additional
  Blueprint retries, text-command fallback, fixed speech waits, global scheduler,
  new login or permanent speech/history store is introduced.

HA action return means only that the local official call returned/enqueued. The
pinned client batches sequences in background and itself retries some HTTP errors.
There is no correlated receipt for cloud delivery, dialogue ending or speech
completion. Background HTTP errors may only reach upstream logs. A successful HA
trace is not a confirmed-stop or confirmed-spoken signal.

A newer utterance whose history has not arrived cannot be detected yet. An operation
already enqueued upstream cannot be retracted by turning off reception, cancelling
automations or timing out a caller. Across batches, a late Stop can still race with
speech. No fixed sleep would prove completion, so none is added. Cross-automation
speech overlap, native follow-up behavior and self-recognition require hardware
checks. Report limitations per capability/device; reception compatibility does not
prove interruption or speaking compatibility. Music recovery is not included.

## Read-only target lookup for ordinary HA automations

`alexa_voice_events.resolve_targets` requires a response variable. Its fields are
`source_entity_id` (an AVE event entity) and optional `reply_device_id` (an official
single speaker). Omitting the latter uses the source; a supplied invalid device
never falls back. The action never calls Amazon or changes a device.

```yaml
action: alexa_voice_events.resolve_targets
data:
  source_entity_id: event.example_speaker_voice
response_variable: targets
```

The returned mapping has `schema_version: 1`, `source_valid`, `source_reason`,
`source_device_id`, `reply_device_id`, and `stop`, `speak`, `announce` objects. Each
role has `entity_id` and `reason`: a resolved entity has null reason; a failed role
has null entity ID and a fixed reason. The source Stop role is independent of the
chosen output's Speak/Announce roles.

**source_valid verifies current identity binding only.** It is not authorization
for any old event. Ordinary consumers must retain their triggering snapshot and
repeat the freshness/latest/session/reception checks before control calls, just
like the Blueprint. A disabled reception control can still have a valid identity.

The lookup checks selected AVE identity and official account/device/role registry
keys, survives entity renames and rejects ambiguous mappings. It reads current
metadata on each call and remains registered as individual accounts unload; an
unloaded source returns an invalid result. It does not guess from names or raw
serial input. Notify `unknown` alone is not an unavailability or delivery receipt.

Fixed reasons include source_not_found, source_not_configured, account_not_ready,
source_mismatch, source_unavailable, device_not_found, ambiguous_account,
unsupported_capability, entity_not_found, ambiguous_entity, entity_disabled and
entity_unavailable. Raw errors, credentials, account names and serials are not
returned. Detailed software evidence is in the HA action/automation tests; physical
acceptance remains separate.

### Reading a rejected voice trace

Each voice guard records `voice_guard_reason` before deciding whether to continue:
`ready`, `source_mismatch`, `event_superseded`, `reception_disabled`,
`session_revoked`, `invalid_timestamp`, `future_timestamp` or `event_expired`.
When several checks fail, the first applicable reason is recorded. Target resolver
results separately explain account binding and individual action-role failures.
These values describe local checks and never confirm remote delivery.
