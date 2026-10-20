# Supported upstream baseline

Reviewed 2026-10-21 (Asia/Taipei) before installation. The live instance reports Core **2026.10.2**, Python **3.14.6**, and its built-in Alexa Devices manifest requires **aioamazondevices 16.3.2**. Core 2026.10.1 was the previous development baseline; no downgrade or version-check bypass was used.

Compared official Core tags `2026.10.1` and `2026.10.2`: Alexa Devices `coordinator.py`, `event.py` and `__init__.py` are byte-identical. These contain the coordinator/device lookup, native dispatcher and account lifecycle seams used here. The client requirement is unchanged. The adapter retains an exact Core/client gate and runtime ownership/structure checks. This candidate supports only Core 2026.10.2/client 16.3.2; later patches still need review.

The matching test harness is pytest-homeassistant-custom-component **0.13.373**, whose package metadata pins Core 2026.10.2; `.python-version` is **3.14.6**. `uv.lock` records the resolved environment. The existing real HA lifecycle, upstream parser/push and real Blueprint tests run against this environment. Software tests do not substitute for live speech/action acceptance.

Primary sources: [Core Alexa Devices](https://github.com/home-assistant/core/tree/2026.10.2/homeassistant/components/alexa_devices), [Core manifest](https://github.com/home-assistant/core/blob/2026.10.2/homeassistant/components/alexa_devices/manifest.json), [test harness package metadata](https://pypi.org/pypi/pytest-homeassistant-custom-component/0.13.373/json).

Uxbridge positive/disabled/reload speech checks were confirmed on 2026-10-21; see the [hardware report](hardware-acceptance.md) for the exact tested builds and limits. The known profile is `uxbridge_volume_push`; other speakers and methods remain unverified. Client metadata reads run in HA's executor before receiver binding, retaining the exact version guard without filesystem I/O on HA's event loop.
