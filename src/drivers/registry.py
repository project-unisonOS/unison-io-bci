"""Device registry for known BLE/Serial EEG headsets (metadata only)."""

DEVICE_PROFILES = {
    "ble:muse-s": {
        "name": "Muse-S",
        "channel_labels": ["TP9", "AF7", "AF8", "TP10", "DRL"],
        "sample_rate": 256,
        "decoder": {"name": "rms", "threshold": 50.0, "window_samples": 64},
        "notify_uuid": "0000fe8d-0000-1000-8000-00805f9b34fb",
        "parser": "muse_simple",
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
    # Placeholder: treat packet as little-endian int16 pairs per channel
    if len(packet) < 8:
        return []
    samples = []
    step = 2 * 4  # 4 channels * int16
    for i in range(0, len(packet), step):
        chunk = packet[i : i + step]
        if len(chunk) < step:
            continue
        vals = []
        for j in range(0, step, 2):
            vals.append(int.from_bytes(chunk[j : j + 2], byteorder="little", signed=True))
        samples.append(vals)
    return samples


def parse_csv_line(line: bytes):
    try:
        parts = line.decode().strip().split(",")
        vals = [float(x) for x in parts if x]
        return [vals] if vals else []
    except Exception:
        return []


PARSER_REGISTRY = {
    "muse_simple": parse_muse_simple,
    "csv": parse_csv_line,
}


def get_parser(name: str):
    return PARSER_REGISTRY.get(name)
