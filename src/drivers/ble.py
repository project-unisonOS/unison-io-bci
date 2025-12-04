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

    def __init__(self, on_detect) -> None:
        self._on_detect = on_detect
        self._stop = asyncio.Event()

    async def scan(self, interval: float = 5.0):
        if not _BLE_AVAILABLE:
            logger.info("bleak_not_available; skipping BLE scan")
            return
        logger.info("ble_scan_started")
        while not self._stop.is_set():
            try:
                devices = await BleakScanner.discover(timeout=3.0)
                for d in devices:
                    meta: Dict[str, Any] = {"name": d.name, "address": d.address}
                    if "EEG" in (d.name or "").upper():
                        self._on_detect(f"ble:{d.address}", "eeg", meta)
            except Exception as exc:  # pragma: no cover
                logger.warning("ble_scan_error %s", exc)
            await asyncio.sleep(interval)

    def stop(self):
        if not self._stop.is_set():
            self._stop.set()
