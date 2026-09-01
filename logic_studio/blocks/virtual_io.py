from logic_studio.blocks.base import BaseLogicBlock
from logic_studio.blocks.pin import Pin
from logic_studio.blocks.registry import BlockRegistry
from logic_studio.core.internal_bits import internal_bit_id


class _InternalSignalMixin:
    """Shared compile-time id resolution for the four internal-signal
    blocks below (feat/internal-bits §2). A block's "Bit" property only
    names a registry entry — its TYPE and retentive flag (which together
    determine the actual M./MR./MW./MWR.<name> id, see
    core/internal_bits.internal_bit_id()) live in
    project.settings["internal_bits"], not on the block. The
    ExecutionEngine/CompiledProgram deliberately never holds a live Project
    reference (AUDIT_REPORT.md §2.1), so — exactly like AnalogInputBlock's
    set_range() — the Compiler resolves this ONCE at compile time and
    stores it here; evaluate() then never needs the Project.

    A block that was never compiled (constructed directly in a test, or
    just placed on the canvas and evaluated ad hoc) falls back to computing
    the id from the block's OWN default type/retentive=False — correct for
    the common case, but not authoritative once a real registry entry with
    a non-default retentive flag exists; that's what set_signal_id() is for.
    """
    _SIGNAL_TYPE = "BOOL"  # overridden by the REAL-typed register blocks

    def set_signal_id(self, resolved_id: str):
        self._resolved_signal_id = resolved_id

    def _signal_id(self) -> str:
        resolved = getattr(self, "_resolved_signal_id", None)
        if resolved:
            return resolved
        name = self.properties.get("Bit", "")
        return internal_bit_id({"name": name, "type": self._SIGNAL_TYPE, "retentive": False}) if name else ""


@BlockRegistry.register
class VirtualInputBlock(_InternalSignalMixin, BaseLogicBlock):
    """feat/internal-bits §2.1: reads a project-registered BOOL internal
    signal (project.settings["internal_bits"]) — its "Bit" property names
    the registry entry, picked via SignalPickerDialog (ui/signal_picker.py)
    rather than typed freehand like the old "Tag" property. type_id is
    unchanged for file back-compat; the "Tag"->"Bit" property rename is
    handled by Project's v2->v3 migration (core/project.py)."""

    def __init__(self, type_id="virtual.input", default_name="Wejście bitowe (wewn.)", category="Wejścia / Wyjścia", description="Internal Boolean Input"):
        super().__init__(type_id, default_name, category, description)
        # Purple family, distinct from physical DI's green/DO's red/AI's
        # amber/AO's steel blue — an engineer must tell an internal signal
        # apart from a physical terminal at a glance (§2.4).
        self.color = "#663399"
        self.width = 100
        self.height = 60
        del self.properties["Tag"]  # replaced by "Bit" (§2.1) — see below
        self.properties["Bit"] = ""
        self.is_source = True

        self.outputs = [Pin("State", Pin.DIR_OUTPUT, Pin.TYPE_BOOLEAN)]

    def evaluate(self, engine=None):
        # Force is runtime-only, see AUDIT_REPORT.md §5.1 — never persisted in `properties`.
        force_state = self.simulation_state.get("force_state", "NO FORCE")

        if force_state == "FORCE TRUE":
            self.outputs[0].value = True
        elif force_state == "FORCE FALSE":
            self.outputs[0].value = False
        else:
            signal_id = self._signal_id()
            if engine and hasattr(engine, 'io') and engine.io is not None and signal_id:
                self.outputs[0].value = engine.io.read_internal(signal_id, False)
            elif "sim_value" in self.simulation_state:
                self.outputs[0].value = self.simulation_state["sim_value"]
            else:
                self.outputs[0].value = False


@BlockRegistry.register
class VirtualOutputBlock(_InternalSignalMixin, BaseLogicBlock):
    """feat/internal-bits §2.1: writes a project-registered BOOL internal
    signal — "Bit" property, picked via SignalPickerDialog. See
    VirtualInputBlock for the type_id/migration note."""

    def __init__(self, type_id="virtual.output", default_name="Wyjście bitowe (wewn.)", category="Wejścia / Wyjścia", description="Internal Boolean Output"):
        super().__init__(type_id, default_name, category, description)
        self.color = "#4B0082"  # Purple family — see VirtualInputBlock
        self.width = 100
        self.height = 60
        del self.properties["Tag"]
        self.properties["Bit"] = ""

        self.inputs = [Pin("Cmd", Pin.DIR_INPUT, Pin.TYPE_BOOLEAN)]

    def evaluate(self, engine=None):
        v = self.inputs[0].value
        val = v if v is not None else False
        self.simulation_state["sim_value"] = val

        signal_id = self._signal_id()
        if engine and hasattr(engine, 'queue_internal_write') and signal_id:
            engine.queue_internal_write(signal_id, val)


@BlockRegistry.register
class InternalRegisterInputBlock(_InternalSignalMixin, BaseLogicBlock):
    """feat/internal-bits §2.2: reads a project-registered REAL internal
    signal ("register") — the analog counterpart of VirtualInputBlock."""
    _SIGNAL_TYPE = "REAL"

    def __init__(self, type_id="internal.reg_in", default_name="Wejście rejestru (wewn.)", category="Wejścia / Wyjścia", description="Internal Analog (REAL) Register Input"):
        super().__init__(type_id, default_name, category, description)
        self.color = "#8A2BE2"  # Purple family — see VirtualInputBlock
        self.width = 100
        self.height = 60
        del self.properties["Tag"]
        self.properties["Bit"] = ""
        self.is_source = True

        self.outputs = [Pin("Value", Pin.DIR_OUTPUT, Pin.TYPE_FLOAT)]

    def evaluate(self, engine=None):
        signal_id = self._signal_id()
        if engine and hasattr(engine, 'io') and engine.io is not None and signal_id:
            self.outputs[0].value = engine.io.read_internal(signal_id, 0.0)
        else:
            self.outputs[0].value = self.simulation_state.get("sim_value", 0.0)
        self.simulation_state["sim_value"] = self.outputs[0].value


@BlockRegistry.register
class InternalRegisterOutputBlock(_InternalSignalMixin, BaseLogicBlock):
    """feat/internal-bits §2.2: writes a project-registered REAL internal
    signal — the analog counterpart of VirtualOutputBlock."""
    _SIGNAL_TYPE = "REAL"

    def __init__(self, type_id="internal.reg_out", default_name="Wyjście rejestru (wewn.)", category="Wejścia / Wyjścia", description="Internal Analog (REAL) Register Output"):
        super().__init__(type_id, default_name, category, description)
        self.color = "#6A5ACD"  # Purple family — see VirtualInputBlock
        self.width = 100
        self.height = 60
        del self.properties["Tag"]
        self.properties["Bit"] = ""

        self.inputs = [Pin("Value", Pin.DIR_INPUT, Pin.TYPE_FLOAT)]

    def evaluate(self, engine=None):
        v = self.inputs[0].value
        val = float(v) if v is not None else 0.0
        self.simulation_state["sim_value"] = val

        signal_id = self._signal_id()
        if engine and hasattr(engine, 'queue_internal_write') and signal_id:
            engine.queue_internal_write(signal_id, val)
