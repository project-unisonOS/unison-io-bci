# unison-io-bci

Brain-computer interface (BCI) ingest and decoding service for UnisonOS.

## Status
Planned (Phase 1 MVP in progress) — will join devstack alongside other `unison-io-*` services.

## Purpose
- Discover and ingest BCI device streams (LSL, BLE GATT, USB/serial, vendor SDK adapters).
- Normalize raw neural samples into timestamped buffers with time-sync metadata.
- Run pluggable decoders to emit `bci.intent` events and optional HID mappings for legacy apps.
- Provide scoped access to raw data (diagnostics/research) guarded by consent/policy.
- Emit `caps.report` with `bci_adapter` presence for startup modality planning.

## Planned APIs (MVP)
- `GET /health`, `GET /ready`, `GET /metrics`
- `POST /bci/devices/attach` — attach a discovered stream to a decoder profile.
- `WS /bci/intents` — subscribe to decoded intents (requires `bci.intent.subscribe` scope).
- `WS /bci/raw` — diagnostics/raw mirror (requires `bci.raw.read` + consent).
- `POST /bci/hid-map` — configure BCI→virtual HID mappings (requires `bci.hid.map`).
- Best-effort `caps.report` emission on startup (`bci_adapter: {present: true}`).

## Repo layout (planned)
- `src/` — FastAPI service, device interfaces (LSL/BLE/USB), decoder plugin host.
- `decoders/` — built-in decoders (mock SSVEP/blink for MVP), plugin contracts.
- `tests/` — unit/integration tests (ingest → intent emission, HID mapping).

## Next steps
- Wire devstack service entry and base Dockerfile.
- Implement LSL ingest + mock decoder → `bci.intent` EventEnvelopes.
- Add consent/policy enforcement for raw/export/device-pair endpoints.
