"""feat/signal-crossref §1 — cross-reference index of every signal used in
a project, across all four namespaces ARCHITECTURE.md §10 names: physical
DI/DO, analog points, internal bits/registers, and system signals. Pure
logic, no Qt — fully testable headless, and reusable later by a
documentation exporter (§5's CSV export already is one).

Deliberately duplicates a SUBSET of compiler/validator.py's rules (§1.4).
That's intentional, not an oversight: this index has to work WITHOUT
compiling the project, live while the schematic is still being drawn —
the signals panel rebuilds it after every edit (§2.4), which a full
Validator.run() (topological sort, internal-bit registry validation,
system-catalog lookups tangled with everything else) isn't shaped for at
that frequency. The validator's own rules stay the sole authority on what
actually blocks a compile; this module's find_issues() is a live,
advisory second opinion, not a replacement. See ARCHITECTURE.md
"Cross-reference sygnałów" for the full rationale, and do not try to share
code between the two here.
"""
from dataclasses import dataclass, field

from logic_studio.blocks.pin import Pin
from logic_studio.core.device_model import DeviceModel
from logic_studio.core.internal_bits import internal_bit_id
from logic_studio.core import system_signals

KIND_PHYSICAL_DI = "physical_di"
KIND_PHYSICAL_DO = "physical_do"
KIND_ANALOG_IN = "analog_in"
KIND_ANALOG_OUT = "analog_out"
KIND_INTERNAL_BIT = "internal_bit"
KIND_INTERNAL_REG = "internal_reg"
KIND_SYSTEM = "system"
# Not a real namespace — a bookkeeping kind for the "IO block with no
# assigned address" rule (§1.4), which needs its own reserved slot in the
# index; see UNASSIGNED_SIGNAL_ID below.
KIND_UNASSIGNED = "unassigned"

# "" can never be a real signal_id (a block only ever gets scanned as a
# real reader/writer when its Address/Bit/Sygnał is non-empty — see
# _scan_block()), so it's safe to reserve as the key collecting every
# addressable block that has NO address assigned yet.
UNASSIGNED_SIGNAL_ID = ""

# type_ids whose "Address" property is actually meant to be filled in —
# used ONLY for the unassigned-address rule. Every other classification in
# this module is deliberately type_id-independent (§1.3: "zakwalifikuj
# blok... na podstawie kierunku jego pinu, nie na podstawie type_id"), but
# that trick doesn't work here: "Address" exists (empty) on EVERY block via
# BaseLogicBlock.__init__ regardless of type, unlike "Bit"/"Sygnał" (only
# ever added by the block types that use them) — so its mere presence
# can't tell "this block type needs one filled in" apart from "this block
# type carries the key but never uses it" the way an empty Bit/Sygnał
# naturally can (a block scan simply skips those). This is the one
# deliberate, narrow exception.
_ADDRESSABLE_TYPE_IDS = ("input.di", "output.do", "input.ai", "output.ao")


@dataclass
class SignalUsage:
    signal_id: str
    kind: str
    data_type: str = "BOOL"
    label: str = ""
    readers: list = field(default_factory=list)  # [(block_uuid, short_id, pin_name), ...]
    writers: list = field(default_factory=list)
    defined: bool = True


@dataclass
class Issue:
    severity: str  # "error" | "warning" | "info"
    signal_id: str
    text: str


def classify_signal_id(project, coarse_kind: str, signal_id: str) -> str:
    """Maps a SignalPickerDialog-style coarse kind ("physical"/"internal"/
    "system", ui/signal_picker.py's KIND_ROLE) plus its chosen signal_id to
    one of this module's finer-grained KIND_* constants above — the same
    classification _resolve_address() below uses internally, exposed here
    for a caller (feat/signal-watch's WatchPanel) that only has a
    SignalPickerDialog result to work from, not an already-built crossref
    index scanned from blocks on the canvas (a signal an engineer wants to
    watch need not be wired to any block yet)."""
    if coarse_kind == "physical":
        if signal_id in DeviceModel.get_ela_addresses(project):
            return KIND_PHYSICAL_DI
        if signal_id in DeviceModel.get_ada_addresses(project):
            return KIND_PHYSICAL_DO
        if signal_id in DeviceModel.get_analog_output_addresses(project):
            return KIND_ANALOG_OUT
        # Defensive fallback for an address SignalPickerDialog's "physical"
        # section could only ever have offered as an analog INPUT in the
        # first place (every other case matched above) — never raises.
        return KIND_ANALOG_IN
    if coarse_kind == "internal":
        entry = DeviceModel.get_internal_bit(project, signal_id)
        return KIND_INTERNAL_REG if entry and entry.get("type") == "REAL" else KIND_INTERNAL_BIT
    if coarse_kind == "system":
        return KIND_SYSTEM
    return KIND_UNASSIGNED


def build_crossref(project) -> dict:
    """The full cross-reference index, keyed by signal_id."""
    index = {}

    def get_or_create(signal_id, kind, data_type, label="", defined=True):
        usage = index.get(signal_id)
        if usage is None:
            usage = SignalUsage(signal_id=signal_id, kind=kind, data_type=data_type, label=label, defined=defined)
            index[signal_id] = usage
        return usage

    # §1.2/§1.4: seed from the two registries that have a "defined but
    # unused" rule of their own — analog points and internal bits. Physical
    # DI/DO and the system catalog have no such rule (fixed platform
    # contracts, not meant to all show up "unused" on every single
    # project) — they only enter the index once a block actually
    # references them, in the block scan below.
    for point in DeviceModel.get_analog_points(project):
        addr = point.get("address", "")
        if not addr:
            continue
        kind = KIND_ANALOG_IN if point.get("direction") == "input" else KIND_ANALOG_OUT
        label = DeviceModel.get_io_label(project, addr) or point.get("name", "")
        get_or_create(addr, kind, "REAL", label=label, defined=True)

    for entry in DeviceModel.get_internal_bits(project):
        sid = internal_bit_id(entry)
        kind = KIND_INTERNAL_REG if entry.get("type") == "REAL" else KIND_INTERNAL_BIT
        label = entry.get("description", "") or entry.get("label", "")
        get_or_create(sid, kind, entry.get("type", "BOOL"), label=label, defined=True)

    # §1.3: block scan, reader/writer role from pin direction.
    for block in project.blocks:
        if block.type_id in _ADDRESSABLE_TYPE_IDS and not block.properties.get("Address", ""):
            usage = get_or_create(UNASSIGNED_SIGNAL_ID, KIND_UNASSIGNED, "BOOL", defined=True)
            _record(usage, block)
        _scan_block(project, block, get_or_create)

    return index


def _block_role(block):
    """('reader'|'writer'|None, pin_name) for the ONE pin that carries the
    signal this block's Address/Bit/Sygnał names. A pure SOURCE (has
    outputs, no inputs) reads an external value INTO the graph; a pure
    SINK (has inputs, no outputs) writes the graph's computed value OUT to
    one — every current block shaped this way (DI/AI/virtual.input/
    internal.reg_in/system.signal are sources; DO/AO/virtual.output/
    internal.reg_out are sinks) has exactly one pin on the relevant side,
    so outputs[0]/inputs[0] is always the right one. A block with both or
    neither can't be classified this way and is simply skipped — none of
    today's block types are shaped like that."""
    if block.outputs and not block.inputs:
        return "reader", block.outputs[0].name
    if block.inputs and not block.outputs:
        return "writer", block.inputs[0].name
    return None, None


def _record(usage: SignalUsage, block):
    role, pin_name = _block_role(block)
    if role is None:
        return
    entry = (block.uuid, block.short_id, pin_name)
    target = usage.readers if role == "reader" else usage.writers
    if entry not in target:
        target.append(entry)


def _scan_block(project, block, get_or_create):
    props = block.properties

    address = props.get("Address", "")
    if address:
        usage = _resolve_address(project, block, address, get_or_create)
        _record(usage, block)

    bit_name = props.get("Bit", "")
    if bit_name:
        usage = _resolve_bit(project, block, bit_name, get_or_create)
        _record(usage, block)

    sygnal = props.get("Sygnał", "")
    if sygnal:
        usage = _resolve_system_signal(project, sygnal, get_or_create)
        _record(usage, block)


def _resolve_address(project, block, address, get_or_create):
    if address in DeviceModel.get_ela_addresses(project):
        kind, data_type, defined = KIND_PHYSICAL_DI, "BOOL", True
    elif address in DeviceModel.get_ada_addresses(project):
        kind, data_type, defined = KIND_PHYSICAL_DO, "BOOL", True
    elif address in DeviceModel.get_analog_input_addresses(project):
        kind, data_type, defined = KIND_ANALOG_IN, "REAL", True
    elif address in DeviceModel.get_analog_output_addresses(project):
        kind, data_type, defined = KIND_ANALOG_OUT, "REAL", True
    else:
        # §1.3: used, but not in any registry — still indexed, defined=
        # False (this IS the problem the panel needs to show). Kind can't
        # be looked up, so fall back to this block's own shape: a reader
        # (source-shaped) block reading an unknown address behaves like a
        # DI; a writer (sink-shaped) one behaves like a DO.
        role, _ = _block_role(block)
        kind = KIND_PHYSICAL_DO if role == "writer" else KIND_PHYSICAL_DI
        data_type, defined = "BOOL", False

    label = DeviceModel.get_io_label(project, address)
    return get_or_create(address, kind, data_type, label=label, defined=defined)


def _resolve_bit(project, block, bit_name, get_or_create):
    entry = DeviceModel.get_internal_bit(project, bit_name)
    if entry is not None:
        sid = internal_bit_id(entry)
        kind = KIND_INTERNAL_REG if entry.get("type") == "REAL" else KIND_INTERNAL_BIT
        data_type = entry.get("type", "BOOL")
        label = entry.get("description", "") or entry.get("label", "")
        return get_or_create(sid, kind, data_type, label=label, defined=True)

    # §1.3: undefined — no registry entry to derive the M./MW./MR./MWR.
    # prefix from, so the raw name the engineer typed is the best
    # identifier available. The pin's own data_type is the only type hint
    # left without a registry entry to ask instead.
    role, _ = _block_role(block)
    pin = block.outputs[0] if role == "reader" else (block.inputs[0] if role == "writer" else None)
    is_real = bool(pin) and pin.data_type == Pin.TYPE_FLOAT
    kind = KIND_INTERNAL_REG if is_real else KIND_INTERNAL_BIT
    return get_or_create(bit_name, kind, "REAL" if is_real else "BOOL", defined=False)


def _resolve_system_signal(project, sig_id, get_or_create):
    entry = system_signals.get_signal(sig_id, project)
    if entry is not None:
        data_type = entry.get("type", "BOOL")
        label = entry.get("description", "") or entry.get("label", "")
        return get_or_create(sig_id, KIND_SYSTEM, data_type, label=label, defined=True)
    return get_or_create(sig_id, KIND_SYSTEM, "BOOL", defined=False)


def find_issues(crossref: dict) -> list:
    """§1.4 — advisory rules, purely from an already-built index. Order:
    error, then warning, then info (the panel/CSV export don't have to
    re-sort)."""
    issues = []

    for signal_id, usage in crossref.items():
        if usage.kind == KIND_UNASSIGNED:
            for (_uuid, short_id, _pin) in usage.readers + usage.writers:
                issues.append(Issue("warning", short_id, f"Blok '{short_id}' nie ma przypisanego adresu."))
            continue

        if not usage.defined:
            issues.append(Issue("error", signal_id, f"Sygnał '{signal_id}' jest używany, ale nie istnieje w żadnym rejestrze."))
            continue  # further rules (writer count, unused, ...) aren't meaningful for a signal that doesn't exist

        if usage.kind in (KIND_INTERNAL_BIT, KIND_INTERNAL_REG):
            if len(usage.writers) > 1:
                issues.append(Issue("error", signal_id, f"Sygnał wewnętrzny '{signal_id}' ma więcej niż jeden blok zapisujący."))
            if usage.readers and not usage.writers:
                issues.append(Issue("warning", signal_id, f"Sygnał wewnętrzny '{signal_id}' jest czytany, ale przez nikogo niezapisywany."))
            if not usage.readers and not usage.writers:
                issues.append(Issue("warning", signal_id, f"Sygnał wewnętrzny '{signal_id}' jest zdefiniowany w rejestrze, ale nieużywany."))

        if usage.kind in (KIND_ANALOG_IN, KIND_ANALOG_OUT):
            if not usage.readers and not usage.writers:
                issues.append(Issue("warning", signal_id, f"Punkt analogowy '{signal_id}' jest zdefiniowany, ale nieużywany."))

        if usage.kind in (KIND_PHYSICAL_DI, KIND_ANALOG_IN) and len(usage.readers) > 1:
            issues.append(Issue("info", signal_id, f"Adres wejściowy '{signal_id}' jest czytany przez {len(usage.readers)} bloki."))

    return issues
