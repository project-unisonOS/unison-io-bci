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
- `POST /bci/devices/attach` — attach a discovered stream to a decoder profile (supports `decoder {name: window|rms, threshold, window_samples}` and optional `person_id`).
- `GET /bci/decoders` — list available decoders and defaults.
- `GET /bci/devices` — list attached streams.
- `WS /bci/intents` — subscribe to decoded intents (requires `bci.intent.subscribe` scope; push-only).
- `WS /bci/raw` — diagnostics/raw mirror (requires `bci.raw.read`); supports `?stream=<id>` and `?limit=<n>` (default 100, capped by `UNISON_BCI_MAX_RAW_SNAPSHOT`).
- `POST /bci/hid-map` — configure BCI→virtual HID mappings (requires `bci.hid.map`).
- `POST /bci/export` — export buffered raw to XDF/EDF (requires `bci.export`; XDF path best effort).
- Best-effort `caps.report` emission on startup (`bci_adapter: {present: true}`).
- Best-effort BLE scan and serial probe to detect known EEG devices; LSL ingest for EEG streams.
- BLE streaming stubs (e.g., Muse-S notify UUID + simple parser) and serial CSV streaming hooks (e.g., OpenBCI serial) feed samples into the decoder pipeline.
- Optional virtual HID output using `evdev/uinput` when available; otherwise logs.

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
- `UNISON_BCI_WINDOW_SAMPLES` — window size for amplitude averaging before decoding.
- `UNISON_BCI_SCOPE_INTENTS` / `UNISON_BCI_SCOPE_RAW` / `UNISON_BCI_SCOPE_HID` — required scopes checked on WS/endpoints.
- `UNISON_BCI_AUTH_JWKS_URL`, `UNISON_BCI_AUTH_AUDIENCE`, `UNISON_BCI_AUTH_ISSUER` — JWT validation for scopes (recommended).
- `UNISON_BCI_CONSENT_INTROSPECT_URL` — optional consent introspection endpoint (e.g., consent `/introspect`).
- `UNISON_BCI_SCOPE_EXPORT` — scope required for export endpoints (default `bci.export`).
- `UNISON_BCI_MAX_BUFFER_SAMPLES` — max samples retained per stream for raw mirror/export.
- `UNISON_BCI_MAX_RAW_SNAPSHOT` — cap for samples returned per stream in raw snapshots.
- `UNISON_CONTEXT_HOST` / `UNISON_CONTEXT_PORT` — optional context service for per-person decoder/HID prefs.

## Quickstart (profiles + scopes)

1. Attach a device stream (BLE/serial/LSL) with a decoder profile and person context:
   ```bash
   curl -X POST http://localhost:8089/bci/devices/attach \
     -H "Authorization: Bearer <token with bci.intent.subscribe>" \
     -d '{"device_id":"ble:muse-s","decoder":{"name":"ssvep","targets":[10,12,15],"threshold":2.0},"person_id":"local-user"}'
   ```
   Available decoders: `window`, `rms`, `bandpower`, `ssvep`, `smr` (see `/bci/decoders`).
2. Subscribe to intents: `ws://localhost:8089/bci/intents?token=<jwt>` requires `bci.intent.subscribe`.
3. Subscribe to raw snapshots: `ws://localhost:8089/bci/raw?stream=ble:muse-s&compress=true` requires `bci.raw.read`. `format=cbor` is supported when `cbor2` is installed.
4. Export buffered raw: `POST /bci/export` with scope `bci.export` supports `format: xdf|edf`; enforced by `UNISON_BCI_MAX_EXPORT_SECONDS`.
5. HID mapping: `POST /bci/hid-map` with scope `bci.hid.map` and optional `person_id` persists mappings via context service when configured.

Platform requirements: BLE/serial paths rely on `bleak`/`pyserial`; EDF export uses `pyedflib` wheels; HID output uses `evdev/uinput` and falls back to logging when `/dev/uinput` is unavailable (WSL-friendly).

## Repo layout
- `src/` — FastAPI service, LSL discovery stub, demo intent emitter, WS endpoints.
- `decoders/` — reserved for built-in decoders (mock SSVEP/blink for MVP), plugin contracts.
- `tests/` — unit/integration tests (TODO).

## Next steps (what’s needed)
- **Device-accurate parsers**: need real captures or vendor specs for Muse notify payloads (byte layout, scaling to µV) and OpenBCI Cyton serial framing (ASCII/binary, AUX channels, gain factors) to finalize parsers and channel ordering.
- **Telemetry wiring**: share target metrics backend (Prometheus/OTel) and naming/label conventions so ingest latency, decoder pass rates, and drop counters can be exported, not just exposed via `/metrics`.
- **Profile persistence**: confirm context-service schema for storing per-person decoder/HID defaults and calibration artifacts; currently best-effort via `/profile/{person_id}`.
- **HID/platform checks**: validate `/dev/uinput` availability on target hosts; falls back to logging in WSL/CI.
