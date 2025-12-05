import logging
from typing import Dict, Optional

logger = logging.getLogger("unison-io-bci.hid")

try:
    import evdev  # type: ignore
    from evdev import UInput, ecodes as e
    _EVDEV_AVAILABLE = True
except Exception:
    _EVDEV_AVAILABLE = False


class HIDEmitter:
    """Optional virtual HID emitter (keyboard) using evdev/uinput."""

    def __init__(self):
        self.ui: Optional[UInput] = None
        if _EVDEV_AVAILABLE:
            try:
                self.ui = UInput(
                    {e.EV_KEY: list(e.ecodes.values())},
                    name="unison-bci-virtual",
                    bustype=0x03,
                )
                logger.info("hid_uinput_created")
            except Exception as exc:  # pragma: no cover
                logger.warning("hid_uinput_failed %s", exc)
                self.ui = None
        else:
            logger.info("evdev_not_available; HID events will be logged only")

    def send(self, keycode: str) -> None:
        if not keycode:
            return
        if self.ui:
            try:
                code = getattr(e, keycode, None)
                if not code:
                    logger.warning("hid_unknown_key %s", keycode)
                    return
                self.ui.write(e.EV_KEY, code, 1)
                self.ui.write(e.EV_KEY, code, 0)
                self.ui.syn()
                return
            except Exception as exc:  # pragma: no cover
                logger.warning("hid_send_failed %s", exc)
        logger.info("hid_event_logged %s", keycode)


def is_valid_keycode(keycode: str) -> bool:
    """Validate keycodes against evdev when available."""
    if not keycode:
        return False
    if not _EVDEV_AVAILABLE:
        return True
    return hasattr(e, keycode)
