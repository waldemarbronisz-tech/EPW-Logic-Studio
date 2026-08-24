import time

class TimeProvider:
    """Abstract interface for time tracking (decouples logic from wall clock)."""
    def current_time_ms(self) -> int:
        raise NotImplementedError()

class SystemTimeProvider(TimeProvider):
    """Uses the real monotonic system clock."""
    def __init__(self):
        # Monotonic gives ns, divide by 1_000_000 for ms
        self._start_time_ns = time.monotonic_ns()

    def current_time_ms(self) -> int:
        return (time.monotonic_ns() - self._start_time_ns) // 1_000_000

class SimulationTimeProvider(TimeProvider):
    """Uses a synthetic clock that increments by cycle_time_ms explicitly."""
    def __init__(self):
        self._current_ms = 0

    def current_time_ms(self) -> int:
        return self._current_ms

    def advance(self, ms: int):
        self._current_ms += ms
