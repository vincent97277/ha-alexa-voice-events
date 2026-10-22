# Development: interruption and replies

These features are **unreleased development changes**, not part of the tagged
v0.1.0 installation. They have software checks; new Stop/Speak/Announce hardware
acceptance and formal release belong to later delivery steps. Existing v0.1.0
hardware acceptance proves its recorded reception/action scope only.

## Configure an automation

Use a component checkout and imported Blueprint from the **same fixed commit**.
Updating the HACS component does not update an imported Blueprint. Before replacing
an imported Blueprint, save its actual content and the affected automations.

Keep the existing voice-event selection, recognized phrase variants and Actions.
The development Blueprint adds:

- **Attempt to interrupt the native reply:** enabled by default. Only a matched,
  still-authorized event attempts Stop on its source speaker. This may stop music.
  Disable it for automations that should not stop the speaker. Adopting the updated
  Blueprint changes existing automations that do not explicitly override this input.
- **Reply message:** optional HA template, evaluated after Actions. Leave it empty
  for no custom reply. Actions may be empty for a query-only automation.
- **Reply speaker:** leave empty to use the speaker from this triggering event,
  or explicitly choose another single official Alexa device. Invalid choices do
  not fall back to another speaker. Speaker groups are not standard reply targets;
  use ordinary HA actions for intentional broadcasts.
- **Advanced reply settings / Reply mode:** Speak by default; Announce adds its
  announcement sound. Entity existence does not verify the device's sound behavior.

For example, set a reply template such as `The recorded value is
{{ states('sensor.example_value') }}` after replacing the example entity with your
own. Sensor selection, units, missing-value wording and sampling-age policy are
household automation concerns. No brand or room rules are built into the integration.

The call order is Stop on source A, your Actions, then optional notify on reply B.
Choosing B never adds a Stop on B. Templates read the data after Actions, not at
trigger time. Strings and finite numbers become text; null or whitespace is not
spoken. Lists, mappings, booleans and other invalid reply results do not become
spoken dumps. Template errors do not undo already-completed household effects.

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
