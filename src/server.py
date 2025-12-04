import asyncio
import json
import logging
import os
import threading
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

import httpx
from fastapi import Body, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect, Depends
from fastapi import status
import uvicorn

from .auth import AuthValidator
from .decoders import WindowedDecoder, RMSDecoder, DECODER_REGISTRY, make_decoder
from .drivers.ble import BLEIngestor
from .drivers.ble_stream import BLEStream
from .drivers.serial import SerialIngestor
from .drivers.registry import get_profile, get_parser
from .hid import HIDEmitter
from .middleware import ScopeMiddleware

try:
    from pylsl import StreamInlet, resolve_byprop  # type: ignore
    _PYLSL_AVAILABLE = True
except Exception:
    _PYLSL_AVAILABLE = False

try:
    from unison_common.logging import configure_logging, log_json
    from unison_common.baton import get_current_baton
    from unison_common import BatonMiddleware
except Exception:  # pragma: no cover - fallback if unison_common not present
    BatonMiddleware = None

APP_NAME = "unison-io-bci"
ORCH_HOST = os.getenv("UNISON_ORCH_HOST", "orchestrator")
ORCH_PORT = os.getenv("UNISON_ORCH_PORT", "8080")
DEFAULT_PERSON_ID = os.getenv("UNISON_DEFAULT_PERSON_ID", "local-user")
SERVICE_HOST = os.getenv("BCI_SERVICE_HOST", "0.0.0.0")
SERVICE_PORT = int(os.getenv("BCI_SERVICE_PORT", "8089"))
ENABLE_DEMO = os.getenv("UNISON_BCI_ENABLE_DEMO", "false").lower() in {"1", "true", "yes", "on"}
AMPLITUDE_THRESHOLD = float(os.getenv("UNISON_BCI_AMPLITUDE_THRESHOLD", "75.0"))
INTENT_COOLDOWN_SEC = float(os.getenv("UNISON_BCI_INTENT_COOLDOWN_SEC", "3.0"))
WINDOW_SAMPLES = int(os.getenv("UNISON_BCI_WINDOW_SAMPLES", "50"))
MAX_BUFFER_SAMPLES = int(os.getenv("UNISON_BCI_MAX_BUFFER_SAMPLES", "5000"))
DEFAULT_DECODER_NAME = os.getenv("UNISON_BCI_DECODER", "window")
MAX_RAW_SNAPSHOT = int(os.getenv("UNISON_BCI_MAX_RAW_SNAPSHOT", "200"))
REQUIRED_SCOPE_INTENTS = os.getenv("UNISON_BCI_SCOPE_INTENTS", "bci.intent.subscribe")
REQUIRED_SCOPE_RAW = os.getenv("UNISON_BCI_SCOPE_RAW", "bci.raw.read")
REQUIRED_SCOPE_HID = os.getenv("UNISON_BCI_SCOPE_HID", "bci.hid.map")
REQUIRED_SCOPE_EXPORT = os.getenv("UNISON_BCI_SCOPE_EXPORT", "bci.export")
AUTH_JWKS_URL = os.getenv("UNISON_BCI_AUTH_JWKS_URL", "")
AUTH_AUDIENCE = os.getenv("UNISON_BCI_AUTH_AUDIENCE", "")
AUTH_ISSUER = os.getenv("UNISON_BCI_AUTH_ISSUER", "")
CONSENT_INTROSPECT_URL = os.getenv("UNISON_BCI_CONSENT_INTROSPECT_URL", "")

logger = configure_logging(APP_NAME) if "configure_logging" in globals() else logging.getLogger(APP_NAME)
app = FastAPI(title=APP_NAME)
if BatonMiddleware:
    app.add_middleware(BatonMiddleware)
app.add_middleware(ScopeMiddleware, auth=_auth)

_metrics = defaultdict(int)
_start_time = time.time()
_hid_mappings: Dict[str, str] = {}
_hid = HIDEmitter()
_auth = AuthValidator(
    jwks_url=AUTH_JWKS_URL or None,
    audience=AUTH_AUDIENCE or None,
    issuer=AUTH_ISSUER or None,
    consent_introspect_url=CONSENT_INTROSPECT_URL or None,
)
_ble_ingestor: Optional[BLEIngestor] = None
_serial_ingestor: Optional[SerialIngestor] = None
_raw_state: Dict[str, Dict[str, Any]] = {}
_decoder_overrides: Dict[str, Dict[str, Any]] = {}
_stream_decoders: Dict[str, Any] = {}
_last_emit: Dict[str, float] = {}
_ble_stream_threads: Dict[str, threading.Thread] = {}


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


def http_post_json(host: str, port: str, path: str, payload: dict, headers: Dict[str, str] | None = None) -> tuple[bool, int, dict | None]:
    try:
        url = f"http://{host}:{port}{path}"
        merged_headers = {"Accept": "application/json"}
        baton = get_current_baton() if "get_current_baton" in globals() else None
        if baton:
            merged_headers["X-Context-Baton"] = baton
        if headers:
            merged_headers.update(headers)
        with httpx.Client(timeout=2.0) as client:
            resp = client.post(url, json=payload, headers=merged_headers)
        parsed = None
        try:
            parsed = resp.json()
        except Exception:
            parsed = None
        return (resp.status_code >= 200 and resp.status_code < 300, resp.status_code, parsed)
    except Exception:
        return (False, 0, None)


class DeviceRegistry:
    def __init__(self) -> None:
        self._devices: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def attach(self, device_id: str, kind: str, meta: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            self._devices[device_id] = {"id": device_id, "kind": kind, "meta": meta, "attached_at": time.time()}
            return self._devices[device_id]

    def list(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._devices.values())

    def meta(self, device_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            dev = self._devices.get(device_id)
            if not dev:
                return None
            return dev.get("meta", {})


class IntentBroadcaster:
    def __init__(self) -> None:
        self._clients: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def register(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)
        await ws.send_json({"event": "connected", "service": APP_NAME, "ts": time.time()})

    async def unregister(self, ws: WebSocket) -> None:
        async with self._lock:
            if ws in self._clients:
                self._clients.remove(ws)

    async def broadcast(self, payload: Dict[str, Any]) -> None:
        async with self._lock:
            clients = list(self._clients)
        for ws in clients:
            try:
                await ws.send_json(payload)
            except Exception:
                try:
                    await self.unregister(ws)
                except Exception:
                    pass


devices = DeviceRegistry()
broadcaster = IntentBroadcaster()
_lsl_ingestor = None


def _require_scope_request(request: Request, required: str | None):
    if not required:
        return
    token = _auth.extract_token(request.headers.get("Authorization"))
    if not token or not _auth.authorize(token, required):
        raise HTTPException(status_code=403, detail=f"missing required scope: {required}")


def _require_scope_ws(ws: WebSocket, required: str | None) -> bool:
    if not required:
        return True
    token = _auth.extract_token(ws.headers.get("Authorization"), ws.query_params.get("token"))
    return bool(token and _auth.authorize(token, required))


def require_scope_dep(required: str):
    async def _dep(request: Request):
        _require_scope_request(request, required)
        return True
    return _dep


def _caps_payload() -> Dict[str, Any]:
    return {
        "bci_adapter": {"present": _env_flag("UNISON_HAS_BCI_ADAPTER", True), "confidence": 0.8},
    }


def _decode_config(meta: Dict[str, Any]) -> Dict[str, Any]:
    decoder_cfg = meta.get("decoder", {}) if isinstance(meta, dict) else {}
    name = str(decoder_cfg.get("name") or DEFAULT_DECODER_NAME)
    threshold = float(decoder_cfg.get("threshold", AMPLITUDE_THRESHOLD))
    window = int(decoder_cfg.get("window_samples", WINDOW_SAMPLES))
    return {"name": name, "threshold": threshold, "window_samples": window}


def _get_decoder(stream_id: str, meta: Dict[str, Any]):
    cfg = _decoder_overrides.get(stream_id) or _decode_config(meta)
    decoder = _stream_decoders.get(stream_id)
    if decoder is None:
        decoder = make_decoder(cfg["name"], cfg["window_samples"], cfg["threshold"])
        _stream_decoders[stream_id] = decoder
    return decoder, cfg


def _should_emit(stream_id: str, magnitude: float, threshold: float) -> bool:
    now = time.time()
    last = _last_emit.get(stream_id, 0)
    if now - last < INTENT_COOLDOWN_SEC:
        return False
    if magnitude < threshold:
        return False
    _last_emit[stream_id] = now
    return True


def _process_samples(stream_id: str, samples: List[List[float]], meta: Dict[str, Any]) -> None:
    decoder, cfg = _get_decoder(stream_id, meta)
    avg_metric, passed = decoder.add_samples(stream_id, samples)
    # Accumulate raw
    state = _raw_state.setdefault(
        stream_id,
        {
            "samples": [],
            "sample_rate": meta.get("sample_rate") or 250,
            "channel_labels": meta.get("channel_labels") or [],
            "start_time": time.time(),
            "sample_index": 0,
        },
    )
    for sample in samples:
        state["samples"].append(sample)
        state["sample_index"] += 1
        if len(state["samples"]) > MAX_BUFFER_SAMPLES:
            state["samples"] = state["samples"][-MAX_BUFFER_SAMPLES:]

    threshold = cfg.get("threshold", AMPLITUDE_THRESHOLD)
    if passed and _should_emit(stream_id, avg_metric, threshold):
        confidence = min(1.0, avg_metric / max(threshold, 1e-3))
        intent_event = _build_bci_intent("click", confidence=confidence, decoder_name=cfg.get("name", "demo"))
        intent_event["metadata"]["source_stream"] = stream_id
        intent_event["intent"]["latency_ms"] = 0
        asyncio.run(_emit_bci_intent_event(intent_event))


def _emit_caps_report() -> None:
    caps = _caps_payload()
    envelope = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": APP_NAME,
        "intent": "caps.report",
        "payload": {"person_id": DEFAULT_PERSON_ID, "caps": caps},
    }
    ok, status, _ = http_post_json(ORCH_HOST, ORCH_PORT, "/event", envelope)
    logger.info("caps_report", extra={"ok": ok, "status": status, "caps": caps})


def _build_bci_intent(command: str, axes: Optional[Dict[str, float]] = None, confidence: float = 0.5, decoder_name: str = "demo") -> Dict[str, Any]:
    return {
        "schema_version": "2.0",
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": APP_NAME,
        "event_type": "bci.intent",
        "intent": {
            "type": "input.command",
            "command": command,
            "axes": axes or {"dx": 0.0, "dy": 0.0},
            "mode": "discrete" if axes is None else "continuous",
            "confidence": confidence,
            "latency_ms": 0,
            "decoder": {"name": decoder_name, "version": "0.0.1"},
        },
        "person": {"id": DEFAULT_PERSON_ID, "session_id": "local-session"},
        "context": {"interaction": "navigation"},
        "auth_scope": "bci.intent.subscribe",
        "metadata": {"source_stream": "demo"},
    }


async def _emit_bci_intent_event(intent_event: Dict[str, Any]) -> None:
    _metrics["bci_intents_emitted"] += 1
    ok, status, _ = http_post_json(ORCH_HOST, ORCH_PORT, "/event", intent_event)
    log_json(
        logging.INFO,
        "bci_intent_emit",
        service=APP_NAME,
        ok=ok,
        status=status,
        command=intent_event.get("intent", {}).get("command"),
        confidence=intent_event.get("intent", {}).get("confidence"),
    )
    await broadcaster.broadcast(intent_event)
    _emit_hid_mapping_if_any(intent_event)


def _emit_hid_mapping_if_any(intent_event: Dict[str, Any]) -> None:
    cmd = (intent_event.get("intent") or {}).get("command")
    if cmd and cmd in _hid_mappings:
        _hid.send(_hid_mappings[cmd])
        hid_event = {
            "schema_version": "2.0",
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": APP_NAME,
            "event_type": "input.hid",
            "payload": {"mapping": cmd, "hid_event": _hid_mappings[cmd]},
            "person": intent_event.get("person"),
            "auth_scope": "bci.hid.map",
        }
        http_post_json(ORCH_HOST, ORCH_PORT, "/event", hid_event)


class LSLIngestor:
    """Best-effort LSL ingest with per-stream decoder selection (window or RMS)."""

    def __init__(self, registry: DeviceRegistry, emit_cb) -> None:
        self._registry = registry
        self._emit_cb = emit_cb
        self._stop = threading.Event()
        self._last_emit: Dict[str, float] = {}
        self._decoders: Dict[str, Any] = {}

    def start(self) -> None:
        t = threading.Thread(target=self._run, daemon=True, name="bci-lsl-ingest")
        t.start()

    def _should_emit(self, stream_id: str, magnitude: float, threshold: float) -> bool:
        now = time.time()
        last = self._last_emit.get(stream_id, 0)
        if now - last < INTENT_COOLDOWN_SEC:
            return False
        if magnitude < threshold:
            return False
        self._last_emit[stream_id] = now
        return True

    def _run(self) -> None:
        if not _PYLSL_AVAILABLE:
            logger.info("pylsl_not_available; skipping LSL ingest")
            return
        log_json(logging.INFO, "lsl_ingest_start", service=APP_NAME, threshold=AMPLITUDE_THRESHOLD)
        while not self._stop.is_set():
            try:
                streams = resolve_byprop("type", "EEG", timeout=2.0)
            except Exception as exc:  # pragma: no cover
                logger.warning("lsl_resolve_error %s", exc)
                time.sleep(2)
                continue

            for info in streams:
                try:
                    stream_id = f"lsl:{info.uid()}"
                    inlet = StreamInlet(info, max_buflen=1)
                    sr = info.nominal_srate() or 250
                    channel_labels: List[str] = []
                    try:
                        desc = info.desc()
                        ch = desc.child("channels").child("channel")
                        while ch:
                            label = ch.child_value("label")
                            if label:
                                channel_labels.append(label)
                            ch = ch.next_sibling()
                    except Exception:
                        channel_labels = []
                    meta = {"name": info.name(), "type": info.type(), "sample_rate": sr, "channel_labels": channel_labels}
                    self._registry.attach(stream_id, "eeg", meta)
                    cfg = _decode_config(meta)
                    self._decoders[stream_id] = make_decoder(cfg["name"], cfg["window_samples"], cfg["threshold"])
                    _raw_state.setdefault(
                        stream_id,
                        {
                            "samples": [],
                            "sample_rate": sr,
                            "channel_labels": channel_labels,
                            "start_time": time.time(),
                            "sample_index": 0,
                        },
                    )
                    log_json(logging.INFO, "lsl_inlet_opened", service=APP_NAME, stream_id=stream_id, name=info.name())

                    while not self._stop.is_set():
                        chunk, timestamps = inlet.pull_chunk(timeout=0.0)
                        if not chunk:
                            time.sleep(0.05)
                            continue
                        _process_samples(stream_id, chunk, meta)
                except Exception as exc:  # pragma: no cover
                    logger.warning("lsl_ingest_error %s", exc)
                    time.sleep(1)
            time.sleep(2)

    def stop(self) -> None:
        self._stop.set()


def _demo_loop():
    """Emit a demo BCI intent periodically for quick plumbing verification."""
    while True:
        try:
            intent_event = _build_bci_intent("click", confidence=0.9)
            asyncio.run(_emit_bci_intent_event(intent_event))
        except Exception as exc:  # pragma: no cover
            logger.warning("demo_intent_failed %s", exc)
        time.sleep(10)


def _start_demo_if_enabled():
    if not ENABLE_DEMO:
        return
    t = threading.Thread(target=_demo_loop, daemon=True, name="bci-demo-loop")
    t.start()
    logger.info("demo_intent_loop_started")


def _start_lsl_ingest():
    global _lsl_ingestor
    _lsl_ingestor = LSLIngestor(devices, emit_cb=_emit_bci_intent_event)
    _lsl_ingestor.start()


def _on_device_detect(device_id: str, kind: str, meta: Dict[str, Any]) -> None:
    profile = get_profile(device_id)
    if profile:
        meta = {**meta, **profile}
    devices.attach(device_id, kind, meta)
    log_json(logging.INFO, "device_detected", service=APP_NAME, device_id=device_id, kind=kind)
    # Start BLE stream if notify UUID provided
    notify_uuid = meta.get("notify_uuid")
    parser_name = meta.get("parser")
    if notify_uuid and parser_name and device_id not in _ble_stream_threads:
        parser_fn = get_parser(parser_name, meta)
        if parser_fn:
            stream = BLEStream(
                address=meta.get("address") or device_id.replace("ble:", ""),
                notify_uuid=notify_uuid,
                sample_rate=meta.get("sample_rate") or 250,
                channel_count=len(meta.get("channel_labels") or []),
                parse_fn=parser_fn,
                on_samples=lambda samples, sid=device_id, m=meta: _process_samples(sid, samples, m),
            )

            def _runner():
                asyncio.run(stream.run())

            t = threading.Thread(target=_runner, daemon=True, name=f"ble-stream-{device_id}")
            _ble_stream_threads[device_id] = t
            t.start()
    # Start serial stream if parser/baud provided
    if device_id.startswith("serial:") and parser_name and meta.get("serial_baud"):
        parser_fn = get_parser(parser_name, meta)
        if parser_fn:
            port = device_id.replace("serial:", "")
            threading.Thread(
                target=lambda: _serial_ingestor.stream(port, baudrate=int(meta.get("serial_baud", 115200)), parser=parser_fn),
                daemon=True,
                name=f"serial-stream-{port}",
            ).start()


def _start_ble_ingest():
    global _ble_ingestor
    _ble_ingestor = BLEIngestor(_on_device_detect, profile_lookup=get_profile)

    async def _runner():
        await _ble_ingestor.scan()

    t = threading.Thread(target=lambda: asyncio.run(_runner()), daemon=True, name="bci-ble-scan")
    t.start()


def _start_serial_probe():
    global _serial_ingestor
    _serial_ingestor = SerialIngestor(_on_device_detect)
    t = threading.Thread(target=_serial_ingestor.probe, daemon=True, name="bci-serial-probe")
    t.start()


@app.on_event("startup")
def _on_startup():
    try:
        _emit_caps_report()
    except Exception as exc:  # pragma: no cover
        logger.warning("caps_report_failed %s", exc)
    _start_demo_if_enabled()
    _start_lsl_ingest()
    _start_ble_ingest()
    _start_serial_probe()


@app.get("/healthz")
@app.get("/health")
def health(request: Request):
    _metrics["/health"] += 1
    event_id = request.headers.get("X-Event-ID")
    log_json(logging.INFO, "health", service=APP_NAME, event_id=event_id)
    return {"status": "ok", "service": APP_NAME}


@app.get("/readyz")
@app.get("/ready")
def ready(request: Request):
    _metrics["/ready"] += 1
    event_id = request.headers.get("X-Event-ID")
    _require_scope_request(request, REQUIRED_SCOPE_INTENTS)
    ok, _, _ = http_post_json(ORCH_HOST, ORCH_PORT, "/health", {}, headers={"X-Event-ID": event_id})
    log_json(logging.INFO, "ready", service=APP_NAME, event_id=event_id, orchestrator_ok=ok)
    return {"ready": ok, "orchestrator": {"host": ORCH_HOST, "port": ORCH_PORT, "ok": ok}}


@app.get("/metrics")
def metrics():
    uptime = time.time() - _start_time
    lines = [
        "# HELP unison_io_bci_requests_total Total number of requests by endpoint",
        "# TYPE unison_io_bci_requests_total counter",
    ]
    for k, v in _metrics.items():
        lines.append(f'unison_io_bci_requests_total{{endpoint="{k}"}} {v}')
    lines.extend([
        "",
        "# HELP unison_io_bci_uptime_seconds Service uptime in seconds",
        "# TYPE unison_io_bci_uptime_seconds gauge",
        f"unison_io_bci_uptime_seconds {uptime}",
    ])
    return "\n".join(lines)


@app.post("/bci/devices/attach")
def attach_device(payload: Dict[str, Any] = Body(...), _: bool = Depends(require_scope_dep(REQUIRED_SCOPE_INTENTS))):
    _metrics["/bci/devices/attach"] += 1
    device_id = payload.get("device_id") or f"manual:{uuid.uuid4()}"
    kind = payload.get("kind", "eeg")
    meta = payload.get("meta", {})
    if not isinstance(meta, dict):
        raise HTTPException(status_code=400, detail="meta must be an object")
    decoder_cfg = _decode_config({"decoder": payload.get("decoder", {})})
    meta["decoder"] = decoder_cfg
    if payload.get("person_id"):
        meta["person_id"] = payload.get("person_id")
    record = devices.attach(device_id, kind, meta)
    log_json(logging.INFO, "bci_device_attached", service=APP_NAME, device_id=device_id, kind=kind)
    return {"ok": True, "device": record}


@app.get("/bci/devices")
def list_devices(_: bool = Depends(require_scope_dep(REQUIRED_SCOPE_INTENTS))):
    _metrics["/bci/devices"] += 1
    return {"devices": devices.list()}


@app.get("/bci/decoders")
def list_decoders():
    return {"decoders": DECODER_REGISTRY, "default": DEFAULT_DECODER_NAME}


@app.post("/bci/hid-map")
def set_hid_map(request: Request, payload: Dict[str, Any] = Body(...), _: bool = Depends(require_scope_dep(REQUIRED_SCOPE_HID))):
    _metrics["/bci/hid-map"] += 1
    # Stub: store mapping in memory for now
    mappings = payload.get("mappings")
    if not isinstance(mappings, dict):
        raise HTTPException(status_code=400, detail="mappings must be an object")
    _hid_mappings.clear()
    _hid_mappings.update({str(k): str(v) for k, v in mappings.items()})
    log_json(logging.INFO, "hid_map_updated", service=APP_NAME, mappings=list(_hid_mappings.keys()))
    return {"ok": True, "mappings": _hid_mappings}


@app.post("/bci/export")
def export_raw(request: Request, format: str = Body(..., embed=True, default="xdf"), _: bool = Depends(require_scope_dep(REQUIRED_SCOPE_EXPORT))):
    fmt = format.lower()
    if fmt not in {"xdf", "edf"}:
        raise HTTPException(status_code=400, detail="unsupported format; use xdf or edf")
    filename = f"/tmp/bci_export_{int(time.time())}.{fmt}"
    try:
        if fmt == "xdf":
            # Minimal XDF with one stream containing concatenated samples
            import pyxdf  # type: ignore
            streams = []
            for sid, state in _raw_state.items():
                samples = state.get("samples", [])
                if not samples:
                    continue
                sr = state.get("sample_rate") or 250
                start = state.get("start_time", time.time())
                labels = state.get("channel_labels") or []
                streams.append(
                    {
                        "info": {"name": sid, "type": "EEG", "sample_rate": sr, "channel_labels": labels},
                        "time_series": samples,
                        "time_stamps": [start + i / sr for i in range(len(samples))],
                    }
                )
            if not streams:
                raise HTTPException(status_code=400, detail="no samples available to export")
            pyxdf.save_xdf(filename, streams)
        else:
            import pyedflib  # type: ignore

            # Flatten buffers into signals; pad/truncate to same length
            max_len = max((len(state.get("samples", [])) for state in _raw_state.values()), default=0)
            if max_len == 0:
                raise HTTPException(status_code=400, detail="no samples available to export")
            channel_names = []
            signals = []
            sample_rates = []
            for sid, state in _raw_state.items():
                samples = state.get("samples", [])
                if not samples:
                    continue
                sr = state.get("sample_rate") or 250
                labels = state.get("channel_labels") or []
                sample_rates.append(sr)
                if labels:
                    channel_names.extend(labels)
                    # transpose channel-major
                    transposed = list(map(list, zip(*samples)))
                    for chan_samples in transposed:
                        sig = chan_samples[:max_len]
                        if len(sig) < max_len:
                            sig.extend([0.0] * (max_len - len(sig)))
                        signals.append(sig)
                else:
                    channel_names.append(sid)
                    flattened = [sum(s) / max(len(s), 1) for s in samples]
                    if len(flattened) < max_len:
                        flattened.extend([0.0] * (max_len - len(flattened)))
                    else:
                        flattened = flattened[:max_len]
                    signals.append(flattened)

            n_channels = len(signals)
            f = pyedflib.EdfWriter(filename, n_channels=n_channels)
            channel_info = []
            for name in channel_names:
                channel_info.append(
                    {
                        "label": name[:16],
                        "dimension": "uV",
                        "sample_rate": sample_rates[0] if sample_rates else 250,
                        "physical_min": -1000,
                        "physical_max": 1000,
                        "digital_min": -32768,
                        "digital_max": 32767,
                        "transducer": "eeg",
                        "prefilter": "",
                    }
                )
            f.setSignalHeaders(channel_info)
            f.writeSamples(signals)
            f.close()
        return {"ok": True, "file": filename}
    except Exception as exc:
        log_json(logging.WARNING, "bci_export_failed", service=APP_NAME, error=str(exc))
        raise HTTPException(status_code=500, detail="export failed")


@app.websocket("/bci/intents")
async def websocket_intents(ws: WebSocket):
    if not _require_scope_ws(ws, REQUIRED_SCOPE_INTENTS):
        await ws.close(code=4403)
        return
    await broadcaster.register(ws)
    try:
        while True:
            _metrics["/bci/intents/ws"] += 1
            try:
                await ws.receive_text()
            except WebSocketDisconnect:
                break
            # Intent stream is push-only; ignore incoming messages
    finally:
        await broadcaster.unregister(ws)


@app.websocket("/bci/raw")
async def websocket_raw(ws: WebSocket):
    if not _require_scope_ws(ws, REQUIRED_SCOPE_RAW):
        await ws.close(code=4403)
        return
    await ws.accept()
    limit_param = ws.query_params.get("limit")
    try:
        limit = int(limit_param) if limit_param else 100
    except Exception:
        limit = 100
    limit = max(1, min(limit, MAX_RAW_SNAPSHOT))
    try:
        while True:
            # Stream snapshot of raw buffers (trimmed) and then sleep briefly
            payload = {"event": "raw.snapshot", "streams": {}}
            requested = ws.query_params.get("stream")
            for sid, state in _raw_state.items():
                if requested and sid != requested:
                    continue
                samples = state.get("samples", [])
                payload["streams"][sid] = {
                    "count": len(samples),
                    "samples": samples[-limit:],  # keep payload small
                    "sample_rate": state.get("sample_rate"),
                    "channel_labels": state.get("channel_labels") or [],
                }
            await ws.send_json(payload)
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        return
    except Exception:
        await ws.close()


if __name__ == "__main__":
    uvicorn.run(app, host=SERVICE_HOST, port=SERVICE_PORT)
