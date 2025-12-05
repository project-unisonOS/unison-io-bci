from collections import deque
from typing import Deque, Dict, List, Tuple, Sequence
import math
import numpy as np

DECODER_REGISTRY = [
    {
        "name": "window",
        "description": "Mean absolute amplitude over sliding window",
        "params": {"threshold": "float", "window_samples": "int"},
    },
    {
        "name": "rms",
        "description": "Root-mean-square amplitude over sliding window",
        "params": {"threshold": "float", "window_samples": "int"},
    },
    {
        "name": "bandpower",
        "description": "Average bandpower over a frequency band (Welch FFT)",
        "params": {"threshold": "float", "window_samples": "int", "band": "[float,float]", "sample_rate": "float"},
    },
    {
        "name": "ssvep",
        "description": "Steady-state visually evoked potential detector (power at target frequencies)",
        "params": {"threshold": "float", "window_samples": "int", "targets": "list<float>", "sample_rate": "float"},
    },
    {
        "name": "smr",
        "description": "Sensorimotor rhythm bandpower detector",
        "params": {"threshold": "float", "window_samples": "int", "band": "[float,float]", "sample_rate": "float"},
    },
]


class WindowedDecoder:
    """Simple windowed amplitude decoder for EEG streams."""

    def __init__(self, window_size: int, threshold: float):
        self.window_size = window_size
        self.threshold = threshold
        self.windows: Dict[str, Deque[float]] = {}

    def _window(self, stream_id: str) -> Deque[float]:
        if stream_id not in self.windows:
            self.windows[stream_id] = deque(maxlen=self.window_size)
        return self.windows[stream_id]

    def add_samples(self, stream_id: str, samples: List[List[float]]) -> Tuple[float, bool]:
        window = self._window(stream_id)
        for sample in samples:
            magnitude = sum(abs(x) for x in sample) / max(len(sample), 1)
            window.append(magnitude)
        if len(window) < self.window_size:
            return 0.0, False
        avg_mag = sum(window) / max(len(window), 1)
        return avg_mag, avg_mag >= self.threshold


class RMSDecoder:
    """Root-mean-square decoder across channels over a window."""

    def __init__(self, window_size: int, threshold: float):
        self.window_size = window_size
        self.threshold = threshold
        self.windows: Dict[str, Deque[float]] = {}

    def _window(self, stream_id: str) -> Deque[float]:
        if stream_id not in self.windows:
            self.windows[stream_id] = deque(maxlen=self.window_size)
        return self.windows[stream_id]

    def add_samples(self, stream_id: str, samples: List[List[float]]) -> Tuple[float, bool]:
        window = self._window(stream_id)
        for sample in samples:
            rms = math.sqrt(sum(x * x for x in sample) / max(len(sample), 1))
            window.append(rms)
        if len(window) < self.window_size:
            return 0.0, False
        avg_rms = sum(window) / max(len(window), 1)
        return avg_rms, avg_rms >= self.threshold


def make_decoder(name: str, window_size: int, threshold: float, sample_rate: float | None = None, params: dict | None = None):
    params = params or {}
    sr = sample_rate or float(params.get("sample_rate") or 250.0)
    if name == "rms":
        return RMSDecoder(window_size, threshold)
    if name == "bandpower":
        return BandpowerDecoder(window_size, threshold, band=params.get("band"), sample_rate=sr)
    if name == "ssvep":
        return SSVEPDecoder(window_size, threshold, targets=params.get("targets"), sample_rate=sr)
    if name == "smr":
        return SMRDecoder(window_size, threshold, band=params.get("band"), sample_rate=sr)
    return WindowedDecoder(window_size, threshold)


class BandpowerDecoder:
    """Compute power in a frequency band using FFT magnitude."""

    def __init__(self, window_size: int, threshold: float, band: Sequence[float] | None = None, sample_rate: float = 250.0):
        self.window_size = window_size
        self.threshold = threshold
        self.band = band or (8.0, 12.0)
        self.sample_rate = sample_rate
        self.windows: Dict[str, Deque[List[float]]] = {}

    def _window(self, stream_id: str) -> Deque[List[float]]:
        if stream_id not in self.windows:
            self.windows[stream_id] = deque(maxlen=self.window_size)
        return self.windows[stream_id]

    def add_samples(self, stream_id: str, samples: List[List[float]]) -> Tuple[float, bool]:
        window = self._window(stream_id)
        window.extend(samples)
        if len(window) < self.window_size:
            return 0.0, False
        arr = np.asarray(window, dtype=float)
        if arr.ndim == 1:
            arr = arr[:, np.newaxis]
        freqs = np.fft.rfftfreq(arr.shape[0], d=1.0 / max(self.sample_rate, 1e-6))
        spectrum = np.abs(np.fft.rfft(arr, axis=0)) ** 2
        mask = (freqs >= self.band[0]) & (freqs <= self.band[1])
        if not mask.any():
            return 0.0, False
        power = float(np.mean(spectrum[mask]))
        return power, power >= self.threshold


class SSVEPDecoder:
    """Detects peaks at target SSVEP frequencies."""

    def __init__(self, window_size: int, threshold: float, targets: Sequence[float] | None = None, sample_rate: float = 250.0):
        self.window_size = window_size
        self.threshold = threshold
        self.targets = list(targets or [10.0, 12.0, 15.0])
        self.sample_rate = sample_rate
        self.windows: Dict[str, Deque[List[float]]] = {}

    def _window(self, stream_id: str) -> Deque[List[float]]:
        if stream_id not in self.windows:
            self.windows[stream_id] = deque(maxlen=self.window_size)
        return self.windows[stream_id]

    def add_samples(self, stream_id: str, samples: List[List[float]]) -> Tuple[float, bool]:
        window = self._window(stream_id)
        window.extend(samples)
        if len(window) < self.window_size:
            return 0.0, False
        arr = np.asarray(window, dtype=float)
        if arr.ndim == 1:
            arr = arr[:, np.newaxis]
        freqs = np.fft.rfftfreq(arr.shape[0], d=1.0 / max(self.sample_rate, 1e-6))
        spectrum = np.abs(np.fft.rfft(arr, axis=0)) ** 2
        baseline = float(np.mean(spectrum))
        max_ratio = 0.0
        for target in self.targets:
            idx = (np.abs(freqs - target)).argmin()
            target_power = float(np.mean(spectrum[idx]))
            if baseline > 1e-6:
                ratio = target_power / baseline
            else:
                ratio = 0.0
            max_ratio = max(max_ratio, ratio)
        return max_ratio, max_ratio >= self.threshold


class SMRDecoder:
    """Simple SMR detector based on bandpower in sensorimotor band."""

    def __init__(self, window_size: int, threshold: float, band: Sequence[float] | None = None, sample_rate: float = 250.0):
        self.window_size = window_size
        self.threshold = threshold
        self.band = band or (12.0, 15.0)
        self.sample_rate = sample_rate
        self.windows: Dict[str, Deque[List[float]]] = {}

    def _window(self, stream_id: str) -> Deque[List[float]]:
        if stream_id not in self.windows:
            self.windows[stream_id] = deque(maxlen=self.window_size)
        return self.windows[stream_id]

    def add_samples(self, stream_id: str, samples: List[List[float]]) -> Tuple[float, bool]:
        window = self._window(stream_id)
        window.extend(samples)
        if len(window) < self.window_size:
            return 0.0, False
        arr = np.asarray(window, dtype=float)
        freqs = np.fft.rfftfreq(arr.shape[0], d=1.0 / max(self.sample_rate, 1e-6))
        spectrum = np.abs(np.fft.rfft(arr, axis=0)) ** 2
        mask = (freqs >= self.band[0]) & (freqs <= self.band[1])
        band_power = float(np.mean(spectrum[mask])) if mask.any() else 0.0
        return band_power, band_power >= self.threshold
