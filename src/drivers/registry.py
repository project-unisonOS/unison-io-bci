"""Device registry for known BLE/Serial EEG headsets (metadata only)."""

DEVICE_PROFILES = {
    "ble:muse-s": {
        "name": "Muse-S",
        "channel_labels": ["TP9", "AF7", "AF8", "TP10", "DRL"],
        "sample_rate": 256,
        "decoder": {"name": "rms", "threshold": 50.0, "window_samples": 64},
    },
    "ble:openbci-cyton": {
        "name": "OpenBCI Cyton",
        "channel_labels": [f"CH{i}" for i in range(1, 9)],
        "sample_rate": 250,
        "decoder": {"name": "window", "threshold": 30.0, "window_samples": 50},
    },
}


def get_profile(device_id: str):
    return DEVICE_PROFILES.get(device_id.lower())
