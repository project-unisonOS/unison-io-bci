import asyncio
import logging
from typing import Any, Callable, Dict, Optional

try:
    from bleak import BleakClient  # type: ignore
    _BLE_AVAILABLE = True
except Exception:
    _BLE_AVAILABLE = False

logger = logging.getLogger("unison-io-bci.ble_stream")


class BLEStream:
    """
    Minimal BLE streaming loop for EEG devices that expose a notify characteristic.
    This is a placeholder: real UUIDs and parsing must be provided per device.
    """

    def __init__(
        self,
        address: str,
        notify_uuid: str,
        sample_rate: float,
        channel_count: int,
        on_samples: Callable[[list[list[float]]], None],
        parse_fn: Callable[[bytes], list[list[float]]],
    ):
        self.address = address
        self.notify_uuid = notify_uuid
        self.sample_rate = sample_rate
        self.channel_count = channel_count
        self.on_samples = on_samples
        self.parse_fn = parse_fn
        self._stop = asyncio.Event()

    async def run(self):
        if not _BLE_AVAILABLE:
            logger.info("bleak_not_available; skipping BLE stream")
            return
        try:
            async with BleakClient(self.address) as client:
                if not client.is_connected:
                    logger.warning("ble_client_not_connected %s", self.address)
                    return

                def _callback(sender: int, data: bytearray):
                    try:
                        samples = self.parse_fn(bytes(data))
                        if samples:
                            self.on_samples(samples)
                    except Exception as exc:  # pragma: no cover
                        logger.warning("ble_parse_error %s", exc)

                await client.start_notify(self.notify_uuid, _callback)
                logger.info("ble_stream_started %s", self.address)
                await self._stop.wait()
                await client.stop_notify(self.notify_uuid)
        except Exception as exc:  # pragma: no cover
            logger.warning("ble_stream_error %s", exc)

    def stop(self):
        if not self._stop.is_set():
            self._stop.set()
