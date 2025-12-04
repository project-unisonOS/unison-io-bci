import logging
from typing import Any, Dict

try:
    import serial  # type: ignore
    _SERIAL_AVAILABLE = True
except Exception:
    _SERIAL_AVAILABLE = False

logger = logging.getLogger("unison-io-bci.serial")


class SerialIngestor:
    """Placeholder serial/USB ingestor for EEG bridges."""

    def __init__(self, on_detect) -> None:
        self._on_detect = on_detect

    def probe(self) -> None:
        if not _SERIAL_AVAILABLE:
            logger.info("pyserial_not_available; skipping serial probe")
            return
        try:
            ports = serial.tools.list_ports.comports()  # type: ignore
        except Exception as exc:  # pragma: no cover
            logger.warning("serial_probe_error %s", exc)
            return
        for port in ports:
            meta: Dict[str, Any] = {"device": port.device, "description": port.description}
            self._on_detect(f"serial:{port.device}", "eeg", meta)
