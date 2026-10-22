# Uxbridge hardware acceptance

Date: **2026-10-21**, Asia/Taipei. Environment: HAOS **18.3**, Core **2026.10.2**, Python **3.14.6**, aioamazondevices **16.3.2**. Speaker: **Marshall Uxbridge**, `volume_push`. Only this profile/method/environment was tested; other speakers and overridden methods remain unverified.

The initial installed build was **3a9a4b1**, downloaded through HACS as a custom integration repository. The Blueprint was independently imported from that immutable commit. Real speech and chosen HA scene actions were used, without event injection or manual automation execution.

| Check | Observed result |
|---|---|
| Enabled reception, a configured phrase | New generic event; Blueprint and HA action completed. User confirmed correct lights and acceptable response. |
| Source reception switched off, another spoken phrase | No new receiver event or chosen action; user confirmed lights remained off. |
| Re-enable and reload | Fresh session, event reset; reload traces rejected old data and did not execute the chosen action. |
| Newly spoken phrase after reload | New generic event and completed Blueprint/action; user confirmed correct lights and acceptable response. |

The corrected runtime **85e21d4** was downloaded through HACS and activated with a Core restart. Package metadata now runs in HA's executor; its blocking warnings did not recur in the new process. After restart, reception restored enabled with a fresh session and no old voice replay. The user then confirmed a new lights-off phrase worked with acceptable response. Its Blueprint/action completed; a subsequent ambient phrase also completed. This final runtime has **66 passing tests**, mypy, Ruff, and passing [tests/hassfest/HACS CI](https://github.com/vincent97277/ha-alexa-voice-events/actions/runs/39482568150).

The released component and Blueprint are byte-identical to `85e21d4`; only release documentation follows that runtime commit. The initial off/re-enable/reload tests above exercised the same reception/session/Blueprint logic; the correction moves startup metadata I/O and updates evidence labels, without changing that logic. No legacy evidence or mock result substitutes for the new speech checks.

Scope: acceptance covers voice-to-action and reception/reload authority on this instance. It does not measure exact speech-end latency, certify Amazon delivery, test other speakers, claim long-term recovery, or recreate legacy spoken replies/music recovery. The official Alexa account and the existing independent BLE/scene consumer were preserved. Household mappings and private account/device identifiers are not part of this public repository.

## Unreleased reply candidate: 2026-10-22

Acceptance is **in progress**. This section does not change the scope of the
v0.1.0 release above. Component and Blueprint runtime are pinned to
`e5fd04015b3bc3349da48abf702e3bc2f3f37ea4`; subsequent commit `809a7b3` changes
documentation only. The candidate was exported locally and manually installed;
no new release has been published. Core 2026.10.2, HAOS 18.3 and Python 3.14.6
were read from the live instance. The 16.3.2 client baseline is supported
indirectly by the runtime version gate and ready status, rather than a separate
live package-metadata read.

The installed component files matched the pinned export after restart. The
imported Blueprint matched the candidate after normalization with the same Core
Blueprint schema. Original component, actual Blueprint content and complete
household automation settings/enabled states were saved privately before
replacement. Existing BLE consumers and shared household actions were preserved.

| Capability | Hardware evidence and limit |
|---|---|
| Source speaker Speak | Three consecutive complete sensor replies with acceptable response, explicitly confirmed by the user. A later combined test also ended with three complete, acceptable replies. This is scoped evidence, not a cloud-delivery guarantee. |
| Isolated Speak | One direct official Speak call with HA-rendered sensor values completed audibly with acceptable response. Target lookup used this integration; there was no preceding Stop or spoken trigger. This single trial is not three-trial acceptance. |
| Native interruption | Unreliable. The initial four matched queries produced two reported interruptions. A household-action test without any custom reply also failed to interrupt. In a later combined test the first query produced an HA reply but did not interrupt native speech; later attempts succeeded. All inspected matched runs issued one official Stop without a visible service error. Do not attribute that combined failure to an unmatched phrase. |
| Existing household actions | Three corrected on/off rounds produced the expected physical effects with acceptable response. The phrase correction stayed in household automation settings. Some early traces rotated out; user confirmation and retained traces are distinguished. |
| Unmatched native requests | Three normal native answers, with no household actions or custom speech; inspected automations exited before managed Stop/notify calls. |
| Interruption disabled, reply blank | Three matched household-action runs issued no managed Stop or notify. The user confirmed correct lights, uninterrupted native answers and no HA speech in all three. Response speed was not separately confirmed. The interruption setting was restored and read back afterward. |
| Reception disabled and re-enabled | Three utterances while disabled produced no chosen action or HA reply. One re-enable cycle produced no old replay. New-query stability and recognition were investigated separately. This is one switch cycle, not three. |
| Rapid instructions | One valid query/native pair had no audible late reply interference; two other attempted pairs did not match the query phrase and do not count as successful pairs. Additional valid-pair acceptance remains pending. |
| Announce, active-media effects, other speakers and cross-speaker audio | Unverified. No automatic music restoration was added. |

Recognition mismatches can prevent an automation from running at all. This is
separate from a matched run that sends Stop but fails to end native dialogue.
Local service completion does not confirm that Amazon delivered, stopped or
finished audio. Native short-answer, long-answer and Follow-Up behavior are not
individually certified. Rapid-event and self-recognition acceptance is not yet
complete. No runtime retry, text-command fallback, fixed speech wait or permanent
Follow-Up setting change was introduced to hide these limitations.
