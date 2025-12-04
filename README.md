# unison-io-bci

Brain-computer interface (BCI) ingest and decoding service for UnisonOS.

## Status
Phase 1 MVP scaffold — joins devstack alongside other `unison-io-*` services.

## Purpose
- Discover and ingest BCI device streams (LSL, BLE GATT, USB/serial, vendor SDK adapters).
- Normalize raw neural samples into timestamped buffers with time-sync metadata.
- Run pluggable decoders to emit `bci.intent` events and optional HID mappings for legacy apps.
- Provide scoped access to raw data (diagnostics/research) guarded by consent/policy.
- Emit `caps.report` with `bci_adapter` presence for startup modality planning.

## APIs (MVP)
- `GET /health`, `GET /ready`, `GET /metrics`
- `POST /bci/devices/attach` — attach a discovered stream to a decoder profile.
- `GET /bci/devices` — list attached streams.
- `WS /bci/intents` — subscribe to decoded intents (requires `bci.intent.subscribe` scope; push-only).
- `WS /bci/raw` — diagnostics/raw mirror (stubbed for now; requires `bci.raw.read`).
- `POST /bci/hid-map` — configure BCI→virtual HID mappings (requires `bci.hid.map`).
- Best-effort `caps.report` emission on startup (`bci_adapter: {present: true}`).

## Running locally
```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -c ../constraints.txt -r requirements.txt
cp .env.example .env
python src/server.py  # listens on 8089 by default
```

Environment:
- `UNISON_ORCH_HOST` / `UNISON_ORCH_PORT` — orchestrator target for EventEnvelopes.
- `UNISON_DEFAULT_PERSON_ID` — person id for capability reports/demo intents.
- `BCI_SERVICE_HOST` / `BCI_SERVICE_PORT` — bind host/port (default 0.0.0.0:8089).
- `UNISON_BCI_ENABLE_DEMO` — emit periodic demo `bci.intent` events (default false).
- `UNISON_HAS_BCI_ADAPTER` — advertise BCI capability in `caps.report` (default true).
- `UNISON_BCI_AMPLITUDE_THRESHOLD` — simple amplitude threshold for demo LSL decoder (µV-ish units).
- `UNISON_BCI_INTENT_COOLDOWN_SEC` — cooldown between decoded intents per stream.

## Repo layout
- `src/` — FastAPI service, LSL discovery stub, demo intent emitter, WS endpoints.
- `decoders/` — reserved for built-in decoders (mock SSVEP/blink for MVP), plugin contracts.
- `tests/` — unit/integration tests (TODO).

## Next steps
- Harden LSL ingest with buffering/windowed features and add BLE/USB drivers.
- Enforce auth/consent scopes on WS and attach/export endpoints.
- Add HID mapping layer and virtual device integration.
