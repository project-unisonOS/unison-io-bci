from collections import deque
from typing import Deque, Dict, List, Tuple
import math


class WindowedDecoder:
    """Simple windowed amplitude/RMS decoder for EEG streams."""

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
