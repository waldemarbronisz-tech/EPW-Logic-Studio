from logic_studio.blocks.base import BaseLogicBlock
from logic_studio.blocks.pin import Pin
from logic_studio.blocks.registry import BlockRegistry

@BlockRegistry.register
class SystemBooleanSignalBlock(BaseLogicBlock):
    """feat/internal-bits §3.4: reads a signal from the fixed system-signal
    catalog (core/system_signals_catalog.json) via
    IOProvider.read_system_signal() — a THIRD address space, separate from
    both physical DI/DO and the project's internal-bits registry. Used to
    overload "Tag" and go through read_digital_input(), meaning a system
    signal and a physical DI channel could collide by address — see
    PROBLEM in the audit. type_id/class name unchanged for file
    back-compat; the "Tag"->"Sygnał" property rename is handled by
    Project's v2->v3 migration (core/project.py)."""

    def __init__(self, type_id="system.signal", default_name="Sygnał systemowy", category="Inne", description="System Signal"):
        super().__init__(type_id, default_name, category, description)

        self.color = "#800080"  # Purple
        self.outputs.append(Pin("Out", Pin.DIR_OUTPUT, Pin.TYPE_BOOLEAN))

        self.properties["Sygnał"] = ""
        self.is_source = True
        self._sync_output_type()

    def _sync_output_type(self):
        """Output pin type must match the selected catalog signal's own
        type (§3.4: "typ wyjścia zgodny z typem sygnału w katalogu") — most
        signals are BOOL, but SYS.SCAN_TIME/SYS.CYCLE_COUNT/
        SYS.ACCESS_LEVEL are REAL. Called from evaluate() too (cheap,
        idempotent) AND from deserialize() below — a project loaded via
        Project.deserialize() sets `properties` directly, bypassing
        update_property(), so without the deserialize() call this stayed
        wrong (defaulting to Boolean) until the engine ran its first scan;
        see AUDIT_REPORT.md §28 for the reproduced bug this closes."""
        from logic_studio.core import system_signals
        signal_id = self.properties.get("Sygnał", "")
        entry = system_signals.get_signal(signal_id) if signal_id else None
        self.outputs[0].data_type = Pin.TYPE_FLOAT if entry and entry.get("type") == "REAL" else Pin.TYPE_BOOLEAN
        # §3.4: a catalog signal marked safety_relevant carries that flag
        # onto the pin (ElementPreviewPanel highlights it, §6 of the
        # rendering-library PR).
        self.outputs[0].safety_relevant = bool(entry.get("safety_relevant")) if entry else False

    def update_property(self, key, value):
        super().update_property(key, value)
        if key == "Sygnał":
            self._sync_output_type()

    @classmethod
    def deserialize(cls, data: dict):
        """AUDIT_REPORT.md §28: BaseLogicBlock.deserialize() sets
        `properties` directly (never through update_property()), so
        without this override a project loaded from disk kept whatever
        pin type __init__() set (Boolean, since "Sygnał" starts empty)
        regardless of the actually-saved "Sygnał" value — wrong for any
        REAL-typed signal (SYS.SCAN_TIME/SYS.CYCLE_COUNT/SYS.ACCESS_LEVEL)
        until the engine ran at least one scan. That's late enough to
        matter: Exporter.export() (compiler/exporter.py) reads pin.data_type
        straight off the live block, and runs BEFORE any evaluate() call in
        Compiler.compile()'s pipeline — a project opened and compiled/
        exported without ever pressing Play shipped the wrong pin type to
        EPW-OS. (Exporter.export() also independently re-resolves this
        project-aware, straight from the catalog, rather than trusting the
        live pin — see its own comment — so this override alone would not
        have been a complete fix.)"""
        block = super().deserialize(data)
        block._sync_output_type()
        return block

    def evaluate(self, engine=None):
        self._sync_output_type()
        signal_id = self.properties.get("Sygnał", "")
        if engine and hasattr(engine, 'io') and engine.io is not None and signal_id:
            now_ms = engine.time.current_time_ms() if hasattr(engine, 'time') and engine.time else 0
            self.outputs[0].value = engine.io.read_system_signal(signal_id, now_ms)
        else:
            # Safe value for an unset/unrecognized signal (§3.4 migration
            # note) — False for BOOL, 0.0 for REAL, never None.
            self.outputs[0].value = 0.0 if self.outputs[0].data_type == Pin.TYPE_FLOAT else False
        self.simulation_state["sim_value"] = self.outputs[0].value

@BlockRegistry.register
class ButtonBlock(BaseLogicBlock):
    def __init__(self, type_id="system.button", default_name="Przycisk", category="Przyciski", description="Przycisk interfejsu"):
        super().__init__(type_id, default_name, category, description)
        self.color = "#000000"
        self.outputs.append(Pin("Out", Pin.DIR_OUTPUT, Pin.TYPE_BOOLEAN))
        self.properties["Tag"] = ""
        self.properties["Mode"] = "Monostabilny"
        self.is_source = True

        # Bistable latch state. "pressed" itself lives in simulation_state because
        # it is driven externally (HMI/UI), not computed by this block's own logic.
        self._latched = False
        self._last_pressed = False

    def reset_runtime_state(self):
        self._latched = False
        self._last_pressed = False

    def evaluate(self, engine=None):
        pressed = bool(self.simulation_state.get("pressed", False))
        mode = self.properties.get("Mode", "Monostabilny")

        if mode == "Bistabilny":
            if pressed and not self._last_pressed:
                self._latched = not self._latched
            self._last_pressed = pressed
            out = self._latched
        else:
            out = pressed

        self.outputs[0].value = out
        self.simulation_state["sim_value"] = out

@BlockRegistry.register
class LedBlock(BaseLogicBlock):
    def __init__(self, type_id="system.led", default_name="LED", category="LED", description="Dioda sygnalizacyjna"):
        super().__init__(type_id, default_name, category, description)
        self.color = "#000000"
        self.inputs.append(Pin("In", Pin.DIR_INPUT, Pin.TYPE_BOOLEAN))
        self.properties["Tag"] = ""

    def evaluate(self, engine=None):
        # LED is a sink. Store state for UI visualization.
        val = bool(self.inputs[0].value) if self.inputs and self.inputs[0].value is not None else False
        self.simulation_state["sim_value"] = val

@BlockRegistry.register
class UserMessageBlock(BaseLogicBlock):
    def __init__(self, type_id="system.message", default_name="Komunikat użytkownika", category="Telemechanika", description="Wiadomość tekstowa dla operatora"):
        super().__init__(type_id, default_name, category, description)
        self.color = "#000000"
        self.width = 120
        self.height = 40
        self.inputs.append(Pin("In", Pin.DIR_INPUT, Pin.TYPE_BOOLEAN))
        self.properties["Message 0"] = "Brak alarmu"
        self.properties["Message 1"] = "Aktywny alarm"

    def evaluate(self, engine=None):
        # User message is a sink. Store message string in simulation state based on input.
        val = bool(self.inputs[0].value) if self.inputs and self.inputs[0].value is not None else False
        msg = self.properties.get("Message 1", "") if val else self.properties.get("Message 0", "")
        self.simulation_state["display_message"] = msg
        self.simulation_state["sim_value"] = val

@BlockRegistry.register
class SignalGeneratorBlock(BaseLogicBlock):
    def __init__(self, type_id="system.generator", default_name="Generator sygnału", category="Inne", description="Generator przebiegu prostokątnego"):
        super().__init__(type_id, default_name, category, description)
        self.color = "#000000"
        self.outputs.append(Pin("Out", Pin.DIR_OUTPUT, Pin.TYPE_BOOLEAN))
        self.properties["Period (s)"] = 1.0
        self.is_stateful = True
        self.is_source = True

    def reset_runtime_state(self):
        pass # relies strictly on global engine clock for deterministic frequency, not local memory

    def evaluate(self, engine=None):
        period_ms = float(self.properties.get("Period (s)", 1.0)) * 1000.0
        if period_ms <= 0:
            self.outputs[0].value = False
            return

        if engine and hasattr(engine, 'time') and engine.time is not None:
            now = engine.time.current_time_ms()
            # Simple 50% duty cycle
            cycle_pos = now % period_ms
            self.outputs[0].value = cycle_pos >= (period_ms / 2.0)
        else:
            self.outputs[0].value = False
