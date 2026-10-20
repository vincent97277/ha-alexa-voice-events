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
