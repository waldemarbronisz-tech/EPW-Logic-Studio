from logic_studio.blocks.base import BaseLogicBlock
from logic_studio.blocks.pin import Pin
from logic_studio.blocks.registry import BlockRegistry


class HysteresisDelayMixin:
    """Shared debounce machinery for every comparator (>, <, >=, <=, ==, !=,
    BETWEEN) — see AUDIT_REPORT.md §5. Mixed into ComparatorBase (2-input
    ordering/equality ops) and BetweenBlock (3-input window op) so all of them
    share identical Hysteresis/T On/T Off semantics from one place.

    Three properties, all optional and defaulting to 0/disabled:
      "Hysteresis"  — output-side Schmitt-trigger band. Once True, a
                       comparator only returns False after the value has
                       moved `Hysteresis` further past the raw threshold, not
                       merely back across it. Prevents chatter from a signal
                       sitting right at the boundary.
      "T On (ms)"   — the (possibly hysteresis-debounced) result must hold
                       True for this long before the output actually goes
                       True.
      "T Off (ms)"  — same, for the transition back to False.
    When all three are 0, a comparator behaves exactly as it did before this
    feature existed — every subclass's `raw` expression is untouched, and
    _debounce() short-circuits straight to it.
    """

    # feat/help-system: shared by every comparator subclass via
    # BaseLogicBlock._merged_class_dict() walking the full MRO — a mixin
    # class's own __dict__ is picked up exactly like a base class's.
    PROPERTY_DESCRIPTIONS = {
        "Hysteresis": "Pasmo histerezy po stronie wyjścia (Schmitt trigger): gdy wyjście jest już PRAWDA, wartość musi cofnąć się o tyle POZA surowy próg, zanim wyjście wróci na FAŁSZ. 0 = wyłączone (brak histerezy).",
        "T On (ms)": "Czas, przez jaki wynik (po ewentualnej histerezie) musi utrzymać się jako PRAWDA, zanim wyjście faktycznie przejdzie na PRAWDA. 0 = brak opóźnienia.",
        "T Off (ms)": "Jak T On (ms), ale dla przejścia z powrotem na FAŁSZ. 0 = brak opóźnienia.",
    }
    PROPERTY_UNITS = {"T On (ms)": "ms", "T Off (ms)": "ms"}

    def _init_hysteresis_delay(self):
        self.properties["Hysteresis"] = 0.0
        self.properties["T On (ms)"] = 0
        self.properties["T Off (ms)"] = 0

        self._latched = None        # last hysteresis-debounced boolean
        self._output_state = False  # last value after the T On/T Off delay
        self._pending_state = None
        self._pending_since = None

    @property
    def is_stateful(self):
        """Computed live from properties, not a fixed flag set once at
        construction — Hysteresis/T On/T Off can be edited on an existing
        block, and the compiler must see the current configuration when it
        decides whether a feedback loop through this block is legal."""
        return (
            float(self.properties.get("Hysteresis", 0.0)) > 0
            or int(self.properties.get("T On (ms)", 0)) > 0
            or int(self.properties.get("T Off (ms)", 0)) > 0
        )

    @is_stateful.setter
    def is_stateful(self, value):
        pass  # derived from properties; direct assignment is a deliberate no-op

    def reset_runtime_state(self):
        self._latched = None
        self._output_state = False
        self._pending_state = None
        self._pending_since = None

    def _get_time(self, engine):
        if engine and hasattr(engine, 'time') and engine.time:
            return engine.time.current_time_ms()
        raise RuntimeError(
            "TimeProvider missing. ExecutionEngine must inject deterministic "
            "time for a comparator's T On/T Off delay."
        )

    def _debounce(self, raw: bool, stay_true, engine) -> bool:
        """raw: the plain comparison result (identical to this operator's
        pre-hysteresis expression). stay_true: no-arg callable — a superset
        of `raw`'s True condition widened by Hysteresis; consulted only once
        already latched True, so it must reduce to `raw` when Hysteresis==0
        (each subclass's formula is chosen to guarantee this)."""
        hysteresis = float(self.properties.get("Hysteresis", 0.0))
        pending = (stay_true() if self._latched else raw) if hysteresis > 0 else raw
        self._latched = pending

        t_on = int(self.properties.get("T On (ms)", 0))
        t_off = int(self.properties.get("T Off (ms)", 0))
        if t_on <= 0 and t_off <= 0:
            self._output_state = pending
            return pending

        now = self._get_time(engine)
        if pending != self._pending_state:
            self._pending_state = pending
            self._pending_since = now

        delay = t_on if pending else t_off
        if now - self._pending_since >= delay:
            self._output_state = pending
        # else: still waiting out the delay, output holds its previous value.
        return self._output_state


class ComparatorBase(BaseLogicBlock, HysteresisDelayMixin):
    PIN_DESCRIPTIONS = {
        "In1": "Lewy operand porównania.",
        "In2": "Prawy operand porównania.",
        "Out": "Wynik porównania In1 z In2 (z uwzględnieniem histerezy/opóźnienia, jeśli skonfigurowane).",
    }

    def __init__(self, type_id, default_name, category, description):
        super().__init__(type_id, default_name, category, description)
        self.color = "#000080" # Classic Navy for comparators
        self.width = 80
        self.height = 80

        self.inputs.append(Pin("In1", Pin.DIR_INPUT, Pin.TYPE_FLOAT))
        self.inputs.append(Pin("In2", Pin.DIR_INPUT, Pin.TYPE_FLOAT))
        self.outputs.append(Pin("Out", Pin.DIR_OUTPUT, Pin.TYPE_BOOLEAN))

        self._init_hysteresis_delay()

    def _get_vals(self):
        v1 = float(self.inputs[0].value) if self.inputs[0].value is not None else 0.0
        v2 = float(self.inputs[1].value) if self.inputs[1].value is not None else 0.0
        return v1, v2

@BlockRegistry.register
class GreaterBlock(ComparatorBase):
    def __init__(self, type_id="compare.gt", default_name=">", category="Elementy Analogowe", description="Większe niż (>) — prawda, gdy In1 > In2."):
        super().__init__(type_id, default_name, category, description)

    def evaluate(self, engine=None):
        v1, v2 = self._get_vals()
        h = float(self.properties.get("Hysteresis", 0.0))
        raw = v1 > v2
        self.outputs[0].value = self._debounce(raw, lambda: v1 > v2 - h, engine)

@BlockRegistry.register
class LessBlock(ComparatorBase):
    def __init__(self, type_id="compare.lt", default_name="<", category="Elementy Analogowe", description="Mniejsze niż (<) — prawda, gdy In1 < In2."):
        super().__init__(type_id, default_name, category, description)

    def evaluate(self, engine=None):
        v1, v2 = self._get_vals()
        h = float(self.properties.get("Hysteresis", 0.0))
        raw = v1 < v2
        self.outputs[0].value = self._debounce(raw, lambda: v1 < v2 + h, engine)

@BlockRegistry.register
class GreaterEqBlock(ComparatorBase):
    def __init__(self, type_id="compare.gte", default_name=">=", category="Elementy Analogowe", description="Większe lub równe (>=) — prawda, gdy In1 >= In2."):
        super().__init__(type_id, default_name, category, description)

    def evaluate(self, engine=None):
        v1, v2 = self._get_vals()
        h = float(self.properties.get("Hysteresis", 0.0))
        raw = v1 >= v2
        self.outputs[0].value = self._debounce(raw, lambda: v1 >= v2 - h, engine)

@BlockRegistry.register
class LessEqBlock(ComparatorBase):
    def __init__(self, type_id="compare.lte", default_name="<=", category="Elementy Analogowe", description="Mniejsze lub równe (<=) — prawda, gdy In1 <= In2."):
        super().__init__(type_id, default_name, category, description)

    def evaluate(self, engine=None):
        v1, v2 = self._get_vals()
        h = float(self.properties.get("Hysteresis", 0.0))
        raw = v1 <= v2
        self.outputs[0].value = self._debounce(raw, lambda: v1 <= v2 + h, engine)

@BlockRegistry.register
class EqualBlock(ComparatorBase):
    def __init__(self, type_id="compare.eq", default_name="==", category="Elementy Analogowe", description="Równość (==) — prawda, gdy In1 == In2."):
        super().__init__(type_id, default_name, category, description)

    def evaluate(self, engine=None):
        v1, v2 = self._get_vals()
        h = float(self.properties.get("Hysteresis", 0.0))
        raw = v1 == v2
        # Hysteresis widens "equal" into a tolerance band once matched, so
        # floating-point noise right at equality doesn't chatter the output.
        self.outputs[0].value = self._debounce(raw, lambda: abs(v1 - v2) <= h, engine)

@BlockRegistry.register
class NotEqualBlock(ComparatorBase):
    def __init__(self, type_id="compare.neq", default_name="!=", category="Elementy Analogowe", description="Różność (!=) — prawda, gdy In1 != In2."):
        super().__init__(type_id, default_name, category, description)

    def evaluate(self, engine=None):
        v1, v2 = self._get_vals()
        raw = v1 != v2
        # != is true everywhere except a single point (v1 == v2); there is no
        # useful widened superset of that region, so Hysteresis is inert here
        # by construction (the property still exists for schema consistency
        # across all comparators — T On/T Off still work normally).
        self.outputs[0].value = self._debounce(raw, lambda: v1 != v2, engine)

@BlockRegistry.register
class BetweenBlock(BaseLogicBlock, HysteresisDelayMixin):
    PIN_DESCRIPTIONS = {
        "Min": "Dolna granica zakresu.",
        "Val": "Wartość sprawdzana względem zakresu Min..Max.",
        "Max": "Górna granica zakresu.",
        "Out": "Prawda, gdy Val mieści się w zakresie Min..Max (z uwzględnieniem histerezy/opóźnienia, jeśli skonfigurowane).",
    }

    def __init__(self, type_id="compare.between", default_name="Between", category="Elementy Analogowe", description="W zakresie — prawda, gdy Val mieści się między Min i Max."):
        super().__init__(type_id, default_name, category, description)
        self.color = "#000080"
        self.width = 80
        self.height = 100

        self.inputs.append(Pin("Min", Pin.DIR_INPUT, Pin.TYPE_FLOAT))
        self.inputs.append(Pin("Val", Pin.DIR_INPUT, Pin.TYPE_FLOAT))
        self.inputs.append(Pin("Max", Pin.DIR_INPUT, Pin.TYPE_FLOAT))
        self.outputs.append(Pin("Out", Pin.DIR_OUTPUT, Pin.TYPE_BOOLEAN))

        self._init_hysteresis_delay()

    def evaluate(self, engine=None):
        vmin = float(self.inputs[0].value) if self.inputs[0].value is not None else 0.0
        vval = float(self.inputs[1].value) if self.inputs[1].value is not None else 0.0
        vmax = float(self.inputs[2].value) if self.inputs[2].value is not None else 0.0

        h = float(self.properties.get("Hysteresis", 0.0))
        raw = (vmin <= vval <= vmax)
        # Once inside, Hysteresis widens the window by h on both sides before
        # the block reports "outside" again.
        self.outputs[0].value = self._debounce(raw, lambda: (vmin - h) <= vval <= (vmax + h), engine)
