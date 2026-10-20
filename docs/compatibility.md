# Supported upstream baseline

Reviewed 2026-10-21 (Asia/Taipei) before installation. The live instance reports Core **2026.10.2**, Python **3.14.6**, and its built-in Alexa Devices manifest requires **aioamazondevices 16.3.2**. Core 2026.10.1 was the previous development baseline; no downgrade or version-check bypass was used.

Compared official Core tags `2026.10.1` and `2026.10.2`: Alexa Devices `coordinator.py`, `event.py` and `__init__.py` are byte-identical. These contain the coordinator/device lookup, native dispatcher and account lifecycle seams used here. The client requirement is unchanged. The adapter retains an exact Core/client gate and runtime ownership/structure checks. This candidate supports only Core 2026.10.2/client 16.3.2; later patches still need review.

The matching test harness is pytest-homeassistant-custom-component **0.13.373**, whose package metadata pins Core 2026.10.2; `.python-version` is **3.14.6**. `uv.lock` records the resolved environment. The existing real HA lifecycle, upstream parser/push and real Blueprint tests run against this environment. Software tests do not substitute for live speech/action acceptance.

Primary sources: [Core Alexa Devices](https://github.com/home-assistant/core/tree/2026.10.2/homeassistant/components/alexa_devices), [Core manifest](https://github.com/home-assistant/core/blob/2026.10.2/homeassistant/components/alexa_devices/manifest.json), [test harness package metadata](https://pypi.org/pypi/pytest-homeassistant-custom-component/0.13.373/json).

Hardware acceptance remains pending. Marshall Uxbridge's profile is still based on legacy evidence, and all other speakers remain unverified. No formal release is created until the new hardware gate passes.
