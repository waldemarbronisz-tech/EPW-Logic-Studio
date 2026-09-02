class IOProvider:
    """Abstract interface for hardware IO interactions."""
    def read_digital_input(self, address: str) -> bool:
        raise NotImplementedError()

    def write_digital_output(self, address: str, value: bool):
        raise NotImplementedError()

    def read_digital_output(self, address: str) -> bool:
        raise NotImplementedError()

    def read_analog_input(self, address: str) -> float:
        raise NotImplementedError()

    def write_analog_output(self, address: str, value: float):
        raise NotImplementedError()

    def read_analog_output(self, address: str) -> float:
        raise NotImplementedError()

    # ---- Internal signals (feat/internal-bits §2.3) ---------------------
    # A SEPARATE address space from physical digital/analog IO — an
    # internal signal name is never a physical channel address, and vice
    # versa, so these never share a dict with read_digital_input/
    # write_digital_output above.

    def read_internal(self, name: str, default=False):
        raise NotImplementedError()

    def write_internal(self, name: str, value):
        raise NotImplementedError()

    # ---- System signals (feat/internal-bits §3.3) ------------------------
    # A third, separate address space again — a fixed platform catalog, not
    # project-defined like internal signals. `now_ms` is required for the
    # PULSE_*/BLINK_* generators, which must be computed from the engine's
    # own TimeProvider, never a wall clock (determinism).

    def read_system_signal(self, signal_id: str, now_ms: int = 0):
        raise NotImplementedError()

class SimulationIOProvider(IOProvider):
    """Memory-backed IO for headless testing and Logic Studio GUI simulation."""
    def __init__(self):
        self.input_image = {
            "digital": {},
            "analog": {}
        }
        self.output_image = {
            "digital": {},
            "analog": {}
        }
        # Internal signals — a single dict since a name is unambiguous
        # regardless of BOOL/REAL (the registry enforces one type per name).
        self.internal_image = {}
        # System signals default to a healthy/online simulated system —
        # overridable per-test/per-scenario (e.g. forcing SYS.FAULT True to
        # exercise a fault-handling schematic).
        self.system_signal_overrides = {
            "SYS.READY": True,
            "SYS.HEALTH": True,
            "SYS.FAULT": False,
            "SYS.SCAN_OVERRUN": False,
            "SYS.FIRST_SCAN": False,
            "SYS.TRAINING_MODE": False,
            "SYS.COMMS_OK": True,
            "SYS.TIME_SYNC_OK": True,
            "ELA01.ONLINE": True,
            "ELA01.FAULT": False,
            "ADA01.ONLINE": True,
            "ADA01.FAULT": False,
            "ADA01.SAFE_PATH_OK": True,
            "SYS.ACCESS_LEVEL": 0.0,
            "SYS.ACCESS_USER": False,
            "SYS.ACCESS_OPERATOR": False,
            "SYS.ACCESS_ENGINEER": False,
        }
        # Diagnostics the engine itself keeps current (see
        # ExecutionEngine.step()) — not part of system_signal_overrides
        # since they change every scan, unlike the mostly-static defaults
        # above.
        self.scan_time_ms = 0.0
        self.cycle_count = 0.0

    def read_digital_input(self, address: str) -> bool:
        return self.input_image["digital"].get(address, False)

    def write_digital_output(self, address: str, value: bool):
        self.output_image["digital"][address] = value

    def read_digital_output(self, address: str) -> bool:
        return self.output_image["digital"].get(address, False)

    def read_analog_input(self, address: str) -> float:
        return self.input_image["analog"].get(address, 0.0)

    def write_analog_output(self, address: str, value: float):
        self.output_image["analog"][address] = value

    def read_analog_output(self, address: str) -> float:
        return self.output_image["analog"].get(address, 0.0)

    def set_digital_input(self, address: str, value: bool):
        self.input_image["digital"][address] = value

    def set_analog_input(self, address: str, value: float):
        self.input_image["analog"][address] = value

    # ---- Internal signals -------------------------------------------------

    def read_internal(self, name: str, default=False):
        return self.internal_image.get(name, default)

    def write_internal(self, name: str, value):
        self.internal_image[name] = value

    # ---- System signals -----------------------------------------------------

    def read_system_signal(self, signal_id: str, now_ms: int = 0):
        if signal_id == "SYS.SCAN_TIME":
            return self.scan_time_ms
        if signal_id == "SYS.CYCLE_COUNT":
            return self.cycle_count
        if signal_id in _PULSE_PERIODS_MS:
            period = _PULSE_PERIODS_MS[signal_id]
            return (now_ms % period) < (period / 2)
        return self.system_signal_overrides.get(signal_id, False)


# Square-wave period for each generator signal (§3.2/§3.3) — deterministic,
# computed from engine.time, never time.time().
_PULSE_PERIODS_MS = {
    "SYS.PULSE_100MS": 100,
    "SYS.PULSE_500MS": 500,
    "SYS.PULSE_1S": 1000,
    "SYS.BLINK_SLOW": 1000,   # 1 Hz
    "SYS.BLINK_FAST": 250,    # 4 Hz
}
