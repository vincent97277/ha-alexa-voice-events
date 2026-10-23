# Simplified reply candidate: scoped hardware checks

Status: the Blueprint from commit `88ad0288cfd1a28735fcd2d3d61b5935514f8bd4`
was installed and checked on one Marshall Uxbridge on **2026-10-23 (Asia/Taipei)**.
v0.3.0 includes the same Blueprint. This report describes candidate installation,
not a tagged HACS install, and does not establish reliability on another speaker.

## Current closure status

On 2026-10-23, after the later phrase and reply tests, the user confirmed the audio
issue clarified, resolved and closed. The observations and limitations below record
the earlier candidate phase, not a currently open audio ticket. v0.3.1 prefix
matching, Help links and icon are new software/assets; no new physical or HA/HACS
UI acceptance is claimed. v0.3.1 changes the Blueprint from this recorded candidate.

## Build and deployment

HA Core 2026.10.2, Python 3.14.6 and HAOS 18.3 were read back. Only the imported
Blueprint was replaced; no Python component, official account or credentials were
changed, and HA was not restarted. The installed file was read back and matched
the candidate after parsing and normalization through the same HA Blueprint
schema. All four consumers were backed up and paused before replacement, then
restored to their original enabled states. Obsolete reply-device/mode inputs were
removed. HA's configuration-check service returned successfully.

The candidate passed 111 software tests, mypy and Ruff before installation. Real
speaker observations below are separate evidence from those tests and from local
service return. There is still no correlated Amazon playback receipt.

## Human observations paired with traces

| Scenario | Observation | Trace evidence |
| --- | --- | --- |
| Select two sensors, blank Reply message | Three consecutive complete, clear replies; response acceptable | Three matched events, each with one source Speak using HA-recorded sensor values after Actions |
| Existing custom temperature/humidity template | Three consecutive complete replies with reasonable values; response acceptable | Original template preserved; one source Speak per matched event |
| Existing lights off/on actions | Three corrected rounds, each off then ambient; correct effects, no custom speech, response acceptable | One original household script call per matched event; no notify |
| Unmatched native time question | Three normal native answers; no HA speech or light changes | All four consumers exited at literal phrase matching for each event; no service calls |

The initial lighting group was **not** a pass: two events omitted the wake-word
prefix and were rejected by the original household phrase lists. The other six
matched events called the correct household action. Only the observed no-prefix
`lights on` and `lights out` variants were added to those household lists before
the successful three-round retry. This is a household configuration correction;
that candidate did not remove wake words or infer intent. v0.3.1 adds only the
leading Alexa comparison exception, without changing the original event text.

The sensor-generated report included the entities' existing Chinese display names
with English report wording and recorded units. The user confirmed clarity on this
speaker. The temporary sensor selection and blank test reply were then removed,
and the original test message restored. Production custom wording and household
actions were preserved. Final readback found all four consumers on and reception
ready, with only the documented input cleanup and two phrase additions retained.

## Limits and rollback

- Native-answer/follow-up interruption remains unreliable. These reply successes
  do not prove interruption succeeded or resolve earlier reports of matched Speak
  submissions with missing/incomplete audio.
- Missing, invalid and non-finite values and true zero have software coverage.
  Unavailable-value speech was not physically tested; no fake states were
  written to live sensors. HA-recorded values do not establish sampling time.
- Other speakers, Announce, cross-speaker replies and active-media behavior were
  not newly verified. The simplified Blueprint always uses source Speak; ordinary
  advanced HA actions and the resolver API remain available.
- Three consecutive successes are scoped observations, not a reliability rate.

Actual prior Blueprint content and all affected automation configs/enabled states
were saved privately. To roll back this Blueprint-only change, disable the affected
consumers, restore the original Blueprint at the same path and their complete saved
configs/enabled states, then validate and verify readback. A full HA restore or
Python component replacement is not required for this change. Already-submitted
Amazon commands cannot be recalled. No diagnostic automation or helper remains.
