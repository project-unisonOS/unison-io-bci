"""Device registry for known BLE/Serial EEG headsets (metadata only)."""

DEVICE_PROFILES = {
    "ble:muse-s": {
        "name": "Muse-S",
        "channel_labels": ["TP9", "AF7", "AF8", "TP10", "DRL"],
        "sample_rate": 256,
        "decoder": {"name": "rms", "threshold": 50.0, "window_samples": 64},
        "notify_uuid": "0000fe8d-0000-1000-8000-00805f9b34fb",
        "parser": "muse_simple",
        "scale": 1.0,
    },
    "ble:muse-2": {
        "name": "Muse-2",
        "channel_labels": ["TP9", "AF7", "AF8", "TP10"],
        "sample_rate": 256,
        "decoder": {"name": "rms", "threshold": 50.0, "window_samples": 64},
        "notify_uuid": "0000fe8d-0000-1000-8000-00805f9b34fb",
        "parser": "muse_simple",
        "scale": 1.0,
    },
    "ble:openbci-cyton": {
        "name": "OpenBCI Cyton",
        "channel_labels": [f"CH{i}" for i in range(1, 9)],
        "sample_rate": 250,
        "decoder": {"name": "window", "threshold": 30.0, "window_samples": 50},
    },
    "serial:openbci": {
        "name": "OpenBCI Serial",
        "channel_labels": [f"CH{i}" for i in range(1, 9)],
        "sample_rate": 250,
        "decoder": {"name": "window", "threshold": 30.0, "window_samples": 50},
        "serial_baud": 115200,
        "parser": "csv",
    },
}


def get_profile(device_id: str):
    return DEVICE_PROFILES.get(device_id.lower())


def parse_muse_simple(packet: bytes):
    return parse_muse_simple_with_meta(packet, None)


def parse_muse_simple_with_meta(packet: bytes, meta: dict | None):
    channel_count = len(meta.get("channel_labels", [])) if meta else 4
    scale = float(meta.get("scale", 1.0)) if meta else 1.0
    if channel_count <= 0:
        channel_count = 4
    step = 2 * channel_count
    if len(packet) < step:
        return []
    samples = []
    for i in range(0, len(packet), step):
        chunk = packet[i : i + step]
        if len(chunk) < step:
            continue
        vals = []
        for j in range(0, step, 2):
            vals.append(int.from_bytes(chunk[j : j + 2], byteorder="little", signed=True) * scale)
        samples.append(vals)
    return samples


def parse_csv_line(line: bytes, meta: dict | None = None):
    try:
        parts = line.decode().strip().split(",")
        vals = [float(x) for x in parts if x]
        if meta and meta.get("channel_labels") and len(meta["channel_labels"]) > 0:
            # Ensure fixed length by padding/truncating
            needed = len(meta["channel_labels"])
            if len(vals) < needed:
                vals.extend([0.0] * (needed - len(vals)))
            else:
                vals = vals[:needed]
        return [vals] if vals else []
    except Exception:
        return []


PARSER_REGISTRY = {
    "muse_simple": parse_muse_simple_with_meta,
    "csv": parse_csv_line,
}


def get_parser(name: str, meta: dict | None = None):
    fn = PARSER_REGISTRY.get(name)
    if not fn:
        return None
    return lambda data: fn(data, meta)
