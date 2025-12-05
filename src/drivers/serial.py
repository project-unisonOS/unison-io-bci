import logging
from typing import Any, Dict

try:
    import serial  # type: ignore
    _SERIAL_AVAILABLE = True
except Exception:
    _SERIAL_AVAILABLE = False

logger = logging.getLogger("unison-io-bci.serial")


class SerialIngestor:
    """Serial/USB ingestor for EEG bridges (OpenBCI-style CSV)."""

    def __init__(self, on_detect, on_samples=None) -> None:
        self._on_detect = on_detect
        self._on_samples = on_samples

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

    def stream(self, port: str, baudrate: int = 115200, parser=None, meta: Dict[str, Any] | None = None):
        if not _SERIAL_AVAILABLE:
            logger.info("pyserial_not_available; skipping serial stream")
            return
        try:
            ser = serial.Serial(port, baudrate=baudrate, timeout=1)
        except Exception as exc:  # pragma: no cover
            logger.warning("serial_open_error %s", exc)
            return
        logger.info("serial_stream_started %s", port)
        try:
            while True:
                line = ser.readline()
                if not line:
                    continue
                try:
                    samples = parser(line) if parser else None
                    if samples and self._on_samples:
                        self._on_samples(samples, meta or {})
                except Exception as exc:  # pragma: no cover
                    logger.warning("serial_parse_error %s", exc)
        except Exception as exc:
            logger.warning("serial_stream_error %s", exc)
        finally:
            ser.close()
