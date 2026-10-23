# Development and verification

[User setup](../README.md) · [Reception architecture](architecture.md)


The target environment is Python **3.14.6**, HA **2026.10.2**, test plugin **0.13.373** and aioamazondevices **16.3.2**. The lockfile records exact resolved dependencies. The plugin's package metadata explicitly pins the required Core version; tests assert the Core/client versions.

```sh
uv sync --locked
uv run pytest
uv run mypy
uv run ruff check .
uv run ruff format --check .
```

Recovery tests exercise actual HA account unload/setup, API replacement with late callbacks, per-speaker availability/method changes, restore-storage startup, queue revocation after account rebind, timeout/backoff, ownership conflicts and unsupported paths. Tests cover multiple accounts (including equal raw speaker identifiers), same-name speakers, native and compatibility methods, opt-in, targeted selection changes, concurrent switch persistence, rename/device association, bounded cross-speaker handoff and queued Blueprint source snapshots. Tests use the real HA config/entity lifecycle and real automation/script engine, with a real upstream coordinator, dispatcher and parser. Remote history responses, clocks and the official Stop/notify service boundaries are controlled; Amazon speaker calls are not executed. The suite disables external sockets; synthetic source identifiers and phrases are not household recordings. These tests prove software behavior, not Amazon delivery, physical action success or other-speaker compatibility.


CI also runs hassfest and HACS packaging checks. Software tests do not establish physical playback or UI rendering. New matching behavior in v0.3.1 is tested through the real HA automation engine; the prior hardware report remains scoped to its recorded candidate.
