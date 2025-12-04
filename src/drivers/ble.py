import asyncio
import logging
from typing import Any, Dict, List

try:
    from bleak import BleakScanner  # type: ignore
    _BLE_AVAILABLE = True
except Exception:
    _BLE_AVAILABLE = False

logger = logging.getLogger("unison-io-bci.ble")


class BLEIngestor:
    """Placeholder BLE ingestor for EEG headsets using Bleak scanning."""

    def __init__(self, on_detect, profile_lookup=None) -> None:
        self._on_detect = on_detect
        self._stop = asyncio.Event()
        self._profile_lookup = profile_lookup

    async def scan(self, interval: float = 5.0):
        if not _BLE_AVAILABLE:
            logger.info("bleak_not_available; skipping BLE scan")
            return
        logger.info("ble_scan_started")
        while not self._stop.is_set():
            try:
                devices = await BleakScanner.discover(timeout=3.0)
                for d in devices:
                    device_id = f"ble:{d.address}"
                    meta: Dict[str, Any] = {"name": d.name, "address": d.address}
                    profile = self._profile_lookup(device_id) if self._profile_lookup else None
                    if profile:
                        meta.update(profile)
                    if "EEG" in (d.name or "").upper() or profile:
                        self._on_detect(device_id, "eeg", meta)
            except Exception as exc:  # pragma: no cover
                logger.warning("ble_scan_error %s", exc)
            await asyncio.sleep(interval)

    def stop(self):
        if not self._stop.is_set():
            self._stop.set()
