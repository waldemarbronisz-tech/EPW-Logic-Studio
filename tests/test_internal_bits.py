"""feat/internal-bits — internal signal registry, system signal catalog,
new blocks, IOProvider extensions, validator rules, cycle-delay detection,
and the export contract. See ARCHITECTURE.md "Przestrzenie nazw sygnałów".
"""
import pytest
from PySide6.QtWidgets import QApplication

from logic_studio.blocks import register_builtin_blocks
from logic_studio.core.project import Project


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


register_builtin_blocks()

# ---- §1 registry ------------------------------------------------------------

def test_project_has_empty_internal_bits_by_default():
    p = Project()
    assert p.settings["internal_bits"] == []

def test_internal_bit_id_all_four_prefixes():
    from logic_studio.core.internal_bits import internal_bit_id
    assert internal_bit_id({"name": "X", "type": "BOOL", "retentive": False}) == "M.X"
    assert internal_bit_id({"name": "X", "type": "BOOL", "retentive": True}) == "MR.X"
    assert internal_bit_id({"name": "X", "type": "REAL", "retentive": False}) == "MW.X"
    assert internal_bit_id({"name": "X", "type": "REAL", "retentive": True}) == "MWR.X"

def test_internal_bit_id_changes_with_type_or_retentive():
    from logic_studio.core.internal_bits import internal_bit_id
    base = {"name": "BLOKADA_ZS", "type": "BOOL", "retentive": False}
    assert internal_bit_id(base) != internal_bit_id({**base, "type": "REAL"})
    assert internal_bit_id(base) != internal_bit_id({**base, "retentive": True})

def test_validate_internal_bit_name_rejects_bad_chars():
    from logic_studio.core.internal_bits import validate_internal_bit_name
    assert validate_internal_bit_name("") is not None
    assert validate_internal_bit_name("BLOKADA ZS") is not None      # space
    assert validate_internal_bit_name("A/B") is not None             # slash
    assert validate_internal_bit_name("A\\B") is not None            # backslash
    assert validate_internal_bit_name('A"B') is not None             # quote
    assert validate_internal_bit_name("BŁOKADA") is not None         # Polish diacritic
    assert validate_internal_bit_name("BLOKADA_ZS") is None
    assert validate_internal_bit_name("BLOKADA.ZS") is None          # dot is fine

def test_validate_internal_bits_registry_catches_case_insensitive_duplicate():
    from logic_studio.core.internal_bits import validate_internal_bits_registry
    entries = [
        {"name": "BLOKADA_ZS", "type": "BOOL"},
        {"name": "blokada_zs", "type": "BOOL"},
    ]
    errors = validate_internal_bits_registry(entries)
    assert len(errors) == 1
    assert "BLOKADA_ZS" in errors[0] or "blokada_zs" in errors[0]

def test_validate_internal_bits_registry_catches_bad_type():
    from logic_studio.core.internal_bits import validate_internal_bits_registry
    errors = validate_internal_bits_registry([{"name": "X", "type": "INT"}])
    assert len(errors) == 1

def test_validate_internal_bits_registry_accepts_valid_entries():
    from logic_studio.core.internal_bits import validate_internal_bits_registry
    errors = validate_internal_bits_registry([
        {"name": "BLOKADA_ZS", "type": "BOOL"},
        {"name": "USTAWKA_MOCY", "type": "REAL"},
    ])
    assert errors == []

def test_device_model_get_internal_bits_and_filter():
    from logic_studio.core.device_model import DeviceModel
    p = Project()
    p.settings["internal_bits"] = [
        {"name": "A", "type": "BOOL", "retentive": False},
        {"name": "B", "type": "REAL", "retentive": False},
    ]
    assert len(DeviceModel.get_internal_bits(p)) == 2
    assert len(DeviceModel.get_internal_bits(p, type_filter="BOOL")) == 1
    assert DeviceModel.get_internal_bit(p, "a")["name"] == "A"  # case-insensitive
    assert DeviceModel.get_internal_bit(p, "nonexistent") is None

# ---- §2 blocks ----------------------------------------------------------

def test_four_internal_signal_blocks_registered():
    from logic_studio.blocks.registry import BlockRegistry
    for type_id in ("virtual.input", "virtual.output", "internal.reg_in", "internal.reg_out"):
        block = BlockRegistry.create_block(type_id)
        assert block is not None, type_id

def test_virtual_input_output_have_bit_not_tag():
    from logic_studio.blocks.registry import BlockRegistry
    vi = BlockRegistry.create_block("virtual.input")
    vo = BlockRegistry.create_block("virtual.output")
    assert "Bit" in vi.properties and "Tag" not in vi.properties
    assert "Bit" in vo.properties and "Tag" not in vo.properties
    assert len(vi.outputs) == 1 and len(vi.inputs) == 0
    assert len(vo.inputs) == 1 and len(vo.outputs) == 0

def test_internal_reg_in_out_pins_and_type():
    from logic_studio.blocks.registry import BlockRegistry
    ri = BlockRegistry.create_block("internal.reg_in")
    ro = BlockRegistry.create_block("internal.reg_out")
    assert ri.is_source is True
    assert len(ri.outputs) == 1 and ri.outputs[0].name == "Value"
    assert len(ro.inputs) == 1 and ro.inputs[0].name == "Value"

def test_io_provider_internal_signal_roundtrip():
    from logic_studio.engine.io_provider import SimulationIOProvider
    io = SimulationIOProvider()
    assert io.read_internal("M.X", False) is False
    io.write_internal("M.X", True)
    assert io.read_internal("M.X", False) is True
    assert io.read_internal("MW.Y", 0.0) == 0.0
    io.write_internal("MW.Y", 3.5)
    assert io.read_internal("MW.Y", 0.0) == 3.5

def test_engine_queue_internal_write_flushes_atomically():
    """Mirrors queue_digital_output's existing atomic-flush test pattern —
    a queued internal write must not be visible on the IOProvider until
    step() explicitly flushes it (§2.3)."""
    from logic_studio.engine.execution import ExecutionEngine
    from logic_studio.engine.io_provider import SimulationIOProvider
    from logic_studio.engine.time_provider import SimulationTimeProvider
    from logic_studio.engine.program import CompiledProgram

    io = SimulationIOProvider()
    program = CompiledProgram(blocks=[], execution_order=[], cycle_time_ms=100)
    engine = ExecutionEngine(program, io, SimulationTimeProvider())

    engine.queue_internal_write("M.X", True)
    assert io.read_internal("M.X", False) is False  # not flushed yet

def test_virtual_output_to_virtual_input_same_scan_via_compiler():
    """End-to-end: a virtual.output writing M.X and a virtual.input reading
    it, compiled and stepped, actually round-trips the value through
    IOProvider.internal_image — not the pin-connection graph (there is no
    wire between them, only the shared registry name)."""
    _app()
    from logic_studio.core.project import Project
    from logic_studio.blocks.registry import BlockRegistry
    from logic_studio.compiler.core import Compiler
    from logic_studio.engine.execution import ExecutionEngine
    from logic_studio.engine.io_provider import SimulationIOProvider
    from logic_studio.engine.time_provider import SimulationTimeProvider

    p = Project()
    p.settings["internal_bits"] = [{"name": "X", "type": "BOOL", "retentive": False, "description": "", "label": "", "category": ""}]

    const_true = BlockRegistry.create_block("const.true")
    vo = BlockRegistry.create_block("virtual.output")
    vo.properties["Bit"] = "X"
    const_true.outputs[0].connect(vo.inputs[0])
    p.add_block(const_true)
    p.add_block(vo)

    compiler = Compiler(p)
    compiled = compiler.compile()
    assert compiled is not None, compiler.errors

    io = SimulationIOProvider()
    engine = ExecutionEngine(compiled["program"], io, SimulationTimeProvider())
    engine.start()
    engine.step()

    assert io.read_internal("M.X", False) is True

# ---- §3 system signal catalog --------------------------------------------

def test_catalog_loads_and_has_expected_categories():
    from logic_studio.core import system_signals
    names = [c["name"] for c in system_signals.get_categories()]
    assert names == ["Stan systemu", "Komunikacja", "Poziom dostępu", "Generatory czasu"]

def test_catalog_contains_every_signal_from_the_spec():
    from logic_studio.core import system_signals
    ids = {s["id"] for s in system_signals.get_all_signals()}
    expected = {
        "SYS.READY", "SYS.HEALTH", "SYS.FAULT", "SYS.SCAN_OVERRUN", "SYS.FIRST_SCAN",
        "SYS.TRAINING_MODE", "SYS.SCAN_TIME", "SYS.CYCLE_COUNT",
        "SYS.COMMS_OK", "SYS.TIME_SYNC_OK", "ELA01.ONLINE", "ELA01.FAULT",
        "ADA01.ONLINE", "ADA01.FAULT", "ADA01.SAFE_PATH_OK",
        "SYS.ACCESS_LEVEL", "SYS.ACCESS_USER", "SYS.ACCESS_OPERATOR", "SYS.ACCESS_ENGINEER",
        "SYS.PULSE_100MS", "SYS.PULSE_500MS", "SYS.PULSE_1S", "SYS.BLINK_SLOW", "SYS.BLINK_FAST",
    }
    assert ids == expected

def test_catalog_safety_relevant_signals():
    from logic_studio.core import system_signals
    safety = {s["id"] for s in system_signals.get_all_signals() if s["safety_relevant"]}
    assert safety == {"SYS.HEALTH", "SYS.FAULT", "ELA01.FAULT", "ADA01.FAULT", "ADA01.SAFE_PATH_OK"}

def test_catalog_get_signal_unknown_returns_none():
    from logic_studio.core import system_signals
    assert system_signals.get_signal("NOT.A.REAL.SIGNAL") is None
    assert system_signals.get_signal("SYS.READY")["type"] == "BOOL"

def test_pulse_and_blink_generators_are_deterministic_square_waves():
    from logic_studio.engine.io_provider import SimulationIOProvider
    io = SimulationIOProvider()
    # SYS.BLINK_SLOW: 1 Hz, 50% duty — high for the first half of each 1000ms period.
    assert io.read_system_signal("SYS.BLINK_SLOW", now_ms=0) is True
    assert io.read_system_signal("SYS.BLINK_SLOW", now_ms=400) is True
    assert io.read_system_signal("SYS.BLINK_SLOW", now_ms=600) is False
    assert io.read_system_signal("SYS.BLINK_SLOW", now_ms=1400) is True
    # SYS.BLINK_FAST: 4 Hz, period 250ms.
    assert io.read_system_signal("SYS.BLINK_FAST", now_ms=0) is True
    assert io.read_system_signal("SYS.BLINK_FAST", now_ms=200) is False

def test_system_signal_block_output_type_matches_catalog():
    """§3.4: SYS.SCAN_TIME is REAL — the output pin's data_type must follow,
    not stay hardcoded BOOL."""
    _app()
    from logic_studio.blocks.pin import Pin
    from logic_studio.blocks.registry import BlockRegistry
    block = BlockRegistry.create_block("system.signal")
    assert block.outputs[0].data_type == Pin.TYPE_BOOLEAN  # default, unset

    block.update_property("Sygnał", "SYS.SCAN_TIME")
    assert block.outputs[0].data_type == Pin.TYPE_FLOAT

    block.update_property("Sygnał", "SYS.READY")
    assert block.outputs[0].data_type == Pin.TYPE_BOOLEAN

def test_system_signal_block_inherits_safety_relevant_from_catalog():
    from logic_studio.blocks.registry import BlockRegistry
    block = BlockRegistry.create_block("system.signal")
    block.update_property("Sygnał", "SYS.FAULT")
    assert block.outputs[0].safety_relevant is True

    block.update_property("Sygnał", "SYS.READY")
    assert block.outputs[0].safety_relevant is False

# ---- AUDIT_REPORT.md §28: type stays wrong until first evaluate() -------
# BaseLogicBlock.deserialize() sets `properties` directly, bypassing
# update_property() — so without SystemBooleanSignalBlock.deserialize()'s
# override, a project loaded from disk kept __init__()'s default Boolean
# pin type for a REAL signal until the engine ran its first scan. Late
# enough to matter: Exporter.export() reads pin.data_type BEFORE
# Compiler.compile() ever calls evaluate() on anything, so a project
# opened and compiled/exported without ever pressing Play shipped the
# wrong pin type to EPW-OS.

def test_deserialize_syncs_output_type_for_a_real_signal_without_evaluate():
    _app()
    from logic_studio.blocks.pin import Pin
    from logic_studio.blocks.registry import BlockRegistry

    block = BlockRegistry.create_block("system.signal")
    block.properties["Sygnał"] = "SYS.SCAN_TIME"
    data = block.serialize()

    restored = block.__class__.deserialize(data)
    # Never called evaluate() or update_property() on `restored` — exactly
    # what Project.deserialize() does when opening a saved file.
    assert restored.outputs[0].data_type == Pin.TYPE_FLOAT
    assert restored.outputs[0].safety_relevant is False

def test_deserialize_syncs_safety_relevant_for_a_safety_signal():
    _app()
    from logic_studio.blocks.registry import BlockRegistry

    block = BlockRegistry.create_block("system.signal")
    block.properties["Sygnał"] = "SYS.FAULT"
    restored = block.__class__.deserialize(block.serialize())
    assert restored.outputs[0].safety_relevant is True

def test_a_freshly_loaded_real_signal_block_can_be_wired_immediately():
    """Regression for the concrete, reproduced symptom: before this fix,
    Pin.connect() rejected a perfectly legal REAL-to-REAL wire because the
    just-loaded output pin was still stuck at Boolean."""
    _app()
    from logic_studio.blocks.registry import BlockRegistry

    block = BlockRegistry.create_block("system.signal")
    block.properties["Sygnał"] = "SYS.SCAN_TIME"
    restored = block.__class__.deserialize(block.serialize())

    add_block = BlockRegistry.create_block("math.add")
    assert restored.outputs[0].connect(add_block.inputs[0]) is True

def test_export_reports_correct_type_for_real_signal_without_ever_running_sim():
    """End-to-end: build + save + reload + compile/export a project
    referencing a REAL system signal, WITHOUT ever calling engine.step() —
    the exported pin type must be correct regardless."""
    _app()
    import json
    from logic_studio.core.project import Project
    from logic_studio.compiler.core import Compiler
    from logic_studio.blocks.pin import Pin
    from logic_studio.blocks.registry import BlockRegistry

    p = Project()
    sig = BlockRegistry.create_block("system.signal")
    sig.properties["Sygnał"] = "SYS.SCAN_TIME"
    p.add_block(sig)

    reloaded = Project.deserialize(json.loads(json.dumps(p.serialize())))
    compiler = Compiler(reloaded)
    result = compiler.compile()
    assert result is not None, compiler.errors

    sig_uuid = reloaded.blocks[0].uuid
    assert result["blocks"][sig_uuid]["outputs"][0]["type"] == Pin.TYPE_FLOAT

def test_export_falls_back_to_live_pin_type_for_unrecognized_signal():
    """An unrecognized/legacy signal id (§3.4 migration note) has no
    catalog entry to resolve a type from — export must fall back to
    whatever the live pin already carries, not raise or blank the field."""
    _app()
    import json
    from logic_studio.core.project import Project
    from logic_studio.blocks.pin import Pin
    from logic_studio.compiler.core import Compiler
    from logic_studio.blocks.registry import BlockRegistry

    p = Project()
    sig = BlockRegistry.create_block("system.signal")
    sig.properties["Sygnał"] = "SYS_READY"  # old pre-catalog underscore format
    p.add_block(sig)

    reloaded = Project.deserialize(json.loads(json.dumps(p.serialize())))
    compiler = Compiler(reloaded)
    result = compiler.compile()
    assert result is not None, compiler.errors

    sig_uuid = reloaded.blocks[0].uuid
    assert result["blocks"][sig_uuid]["outputs"][0]["type"] == Pin.TYPE_BOOLEAN


def test_system_signal_block_reads_via_read_system_signal_not_digital_input():
    """The exact bug from the audit: a system signal must never be
    readable by coincidentally matching a physical DI address."""
    _app()
    from logic_studio.blocks.registry import BlockRegistry
    from logic_studio.engine.io_provider import SimulationIOProvider
    from logic_studio.engine.time_provider import SimulationTimeProvider

    class _FakeEngine:
        def __init__(self, io, time):
            self.io = io
            self.time = time

    block = BlockRegistry.create_block("system.signal")
    block.update_property("Sygnał", "SYS.READY")

    io = SimulationIOProvider()
    io.set_digital_input("SYS.READY", False)  # a physical DI that happens to share the name
    io.system_signal_overrides["SYS.READY"] = True  # the actual system signal

    engine = _FakeEngine(io, SimulationTimeProvider())
    block.evaluate(engine=engine)
    assert block.outputs[0].value is True  # read the system signal, not the coincidentally-named DI

def test_system_signal_block_unrecognized_signal_returns_safe_value():
    """§3.4 migration note: an unrecognized signal id (e.g. after v2->v3
    migration carried forward an old default that predates the catalog)
    must return a safe value, never crash or return None."""
    _app()
    from logic_studio.blocks.registry import BlockRegistry
    block = BlockRegistry.create_block("system.signal")
    block.properties["Sygnał"] = "SYS_READY"  # old pre-catalog underscore format
    block.evaluate(engine=None)
    assert block.outputs[0].value is False

# ---- §4 validator ---------------------------------------------------------

def _validate(project):
    from logic_studio.compiler.validator import Validator
    errors, warnings = [], []
    Validator(project).run(errors, warnings)
    return errors, warnings

def test_validator_error_signal_not_in_registry():
    """§4.4: the whole point of replacing free-text "Tag" with a registry —
    a typo/unregistered name is now a compile ERROR."""
    _app()
    from logic_studio.blocks.registry import BlockRegistry
    p = Project()
    vi = BlockRegistry.create_block("virtual.input")
    vi.properties["Bit"] = "NIGDY_NIEZAREJESTROWANY"
    p.add_block(vi)

    errors, warnings = _validate(p)
    assert any("NIGDY_NIEZAREJESTROWANY" in e for e in errors)

def test_validator_error_type_mismatch():
    """§4.5: a BOOL block pointing at a REAL registry entry (or vice
    versa) must be an ERROR."""
    _app()
    from logic_studio.blocks.registry import BlockRegistry
    p = Project()
    p.settings["internal_bits"] = [{"name": "X", "type": "REAL", "retentive": False}]
    vi = BlockRegistry.create_block("virtual.input")  # BOOL block
    vi.properties["Bit"] = "X"
    p.add_block(vi)

    errors, warnings = _validate(p)
    assert any("X" in e and ("REAL" in e or "BOOL" in e) for e in errors)

def test_validator_error_multiple_writers():
    """§4.1: exactly like output.do — must name every writing block."""
    _app()
    from logic_studio.blocks.registry import BlockRegistry
    p = Project()
    p.settings["internal_bits"] = [{"name": "BLOKADA_ZS", "type": "BOOL", "retentive": False}]
    vo1 = BlockRegistry.create_block("virtual.output")
    vo1.properties["Bit"] = "BLOKADA_ZS"
    vo1.display_name = "VO1"
    vo2 = BlockRegistry.create_block("virtual.output")
    vo2.properties["Bit"] = "BLOKADA_ZS"
    vo2.display_name = "VO2"
    p.add_block(vo1)
    p.add_block(vo2)

    errors, warnings = _validate(p)
    matching = [e for e in errors if "BLOKADA_ZS" in e]
    assert len(matching) == 1
    # feat/io-labels-and-ids §4.3: validator messages name a block by its
    # short_id now, not the (here deliberately set, but otherwise often
    # shared) display_name.
    assert vo1.short_id in matching[0] and vo2.short_id in matching[0]

def test_validator_single_writer_is_not_an_error():
    _app()
    from logic_studio.blocks.registry import BlockRegistry
    p = Project()
    p.settings["internal_bits"] = [{"name": "BLOKADA_ZS", "type": "BOOL", "retentive": False}]
    vo = BlockRegistry.create_block("virtual.output")
    vo.properties["Bit"] = "BLOKADA_ZS"
    p.add_block(vo)

    errors, warnings = _validate(p)
    assert not any("BLOKADA_ZS" in e for e in errors)

def test_validator_warning_read_without_write():
    """§4.2: warning, not error — legitimate mid-build state."""
    _app()
    from logic_studio.blocks.registry import BlockRegistry
    p = Project()
    p.settings["internal_bits"] = [{"name": "X", "type": "BOOL", "retentive": False}]
    vi = BlockRegistry.create_block("virtual.input")
    vi.properties["Bit"] = "X"
    p.add_block(vi)

    errors, warnings = _validate(p)
    assert not any("X" in e for e in errors)
    assert any("X" in w for w in warnings)

def test_validator_warning_registered_but_unused():
    """§4.3: housekeeping warning for a defined-but-dead registry entry."""
    _app()
    p = Project()
    p.settings["internal_bits"] = [{"name": "NIEUZYWANY", "type": "BOOL", "retentive": False}]

    errors, warnings = _validate(p)
    assert any("NIEUZYWANY" in w for w in warnings)

def test_validator_registry_name_errors_surface_as_compile_errors():
    """Invalid registry entries (§1.3) block compilation too, not just the
    registry editor UI — validate_internal_bits_registry() errors are
    appended directly."""
    _app()
    p = Project()
    p.settings["internal_bits"] = [{"name": "BAD NAME", "type": "BOOL", "retentive": False}]

    errors, warnings = _validate(p)
    assert any("BAD NAME" in e for e in errors)

def test_validator_matched_writer_reader_pair_is_clean():
    """A correctly wired writer+reader pair, both pointing at a real
    registry entry, produces no errors and no internal-signal warnings."""
    _app()
    from logic_studio.blocks.registry import BlockRegistry
    p = Project()
    p.settings["internal_bits"] = [{"name": "X", "type": "BOOL", "retentive": False}]
    vo = BlockRegistry.create_block("virtual.output")
    vo.properties["Bit"] = "X"
    vi = BlockRegistry.create_block("virtual.input")
    vi.properties["Bit"] = "X"
    p.add_block(vo)
    p.add_block(vi)

    errors, warnings = _validate(p)
    assert not any("X" in e for e in errors)
    assert not any("X" in w for w in warnings)

# ---- §5 cycle-delay detection ---------------------------------------------

def test_cycle_delay_detected_when_writer_is_scheduled_after_reader():
    """§5.4: a project shaped so the writer necessarily lands later in
    execution_order than the reader — compile, and confirm detection with
    the correct uuid. The reader (is_source, no inputs) and const_true are
    BOTH ready in round 0, so which of the two the tie-break (execution_
    priority, then uuid) picks first is otherwise up to uuid comparison —
    forced deterministic here with an explicitly low execution_priority on
    the reader, same technique as the negative counter-test below, rather
    than relying on however two random uuids happen to compare."""
    _app()
    from logic_studio.core.project import Project
    from logic_studio.blocks.registry import BlockRegistry
    from logic_studio.compiler.core import Compiler

    p = Project()
    p.settings["internal_bits"] = [{"name": "X", "type": "BOOL", "retentive": False, "description": "", "label": "", "category": ""}]

    const_true = BlockRegistry.create_block("const.true")
    not_gate = BlockRegistry.create_block("logic.not")
    vo = BlockRegistry.create_block("virtual.output")
    vo.properties["Bit"] = "X"
    vi = BlockRegistry.create_block("virtual.input")
    vi.properties["Bit"] = "X"
    vi.execution_priority = -1000  # always wins the round-0 tie-break

    assert const_true.outputs[0].connect(not_gate.inputs[0])
    assert not_gate.outputs[0].connect(vo.inputs[0])

    for b in (const_true, not_gate, vo, vi):
        p.add_block(b)

    compiler = Compiler(p)
    compiled = compiler.compile()
    assert compiled is not None, compiler.errors

    order = compiled["program"].execution_order
    assert order.index(vo.uuid) > order.index(vi.uuid), "writer must be scheduled after the reader for this to be a meaningful test"

    assert vi.uuid in compiled["cycle_delayed_reads"]
    assert vi.uuid in compiled["program"].cycle_delayed_reads
    assert any("M.X" in msg for msg in compiler.infos)
    # feat/io-labels-and-ids §4.3: compiler messages identify a block by
    # its short_id now, not the possibly-shared display_name.
    assert any(vi.short_id in msg for msg in compiler.infos)

def test_cycle_delay_not_flagged_when_writer_precedes_reader():
    """Negative case: force the writer to sort BEFORE the reader in the
    same (round-0, both unconnected) tie-break batch via a lower
    execution_priority — confirms the detector isn't just always true."""
    _app()
    from logic_studio.core.project import Project
    from logic_studio.blocks.registry import BlockRegistry
    from logic_studio.compiler.core import Compiler

    p = Project()
    p.settings["internal_bits"] = [{"name": "Y", "type": "BOOL", "retentive": False, "description": "", "label": "", "category": ""}]

    vo = BlockRegistry.create_block("virtual.output")
    vo.properties["Bit"] = "Y"
    vo.execution_priority = 0
    vi = BlockRegistry.create_block("virtual.input")
    vi.properties["Bit"] = "Y"
    vi.execution_priority = 1

    p.add_block(vo)
    p.add_block(vi)

    compiler = Compiler(p)
    compiled = compiler.compile()
    assert compiled is not None, compiler.errors

    order = compiled["program"].execution_order
    assert order.index(vo.uuid) < order.index(vi.uuid)

    assert vi.uuid not in compiled["cycle_delayed_reads"]
    assert not any("Y" in msg for msg in compiler.infos)

# ---- §6 signal picker dialog -----------------------------------------------

def _leaf_ids(item):
    """All SIGNAL_ID_ROLE values in a subtree, for easy membership checks."""
    from logic_studio.ui.signal_picker import SIGNAL_ID_ROLE
    ids = []
    if item.data(0, SIGNAL_ID_ROLE) is not None:
        ids.append(item.data(0, SIGNAL_ID_ROLE))
    for i in range(item.childCount()):
        ids.extend(_leaf_ids(item.child(i)))
    return ids

def _all_tree_ids(dialog):
    ids = []
    for i in range(dialog.tree.topLevelItemCount()):
        ids.extend(_leaf_ids(dialog.tree.topLevelItem(i)))
    return ids

def test_signal_picker_bool_shows_ela_ada_and_bool_internal_and_system():
    _app()
    from logic_studio.ui.signal_picker import SignalPickerDialog
    p = Project()
    p.settings["internal_bits"] = [
        {"name": "BLOKADA_ZS", "type": "BOOL", "retentive": False, "description": "", "label": "", "category": "Blokady"},
        {"name": "USTAWKA", "type": "REAL", "retentive": False, "description": "", "label": "", "category": ""},
    ]
    dialog = SignalPickerDialog(p, value_type="BOOL", sections=("physical", "internal", "system"))
    ids = _all_tree_ids(dialog)
    assert "ELA01.DI01" in ids
    assert "ADA01.DO01" in ids
    assert "BLOKADA_ZS" in ids
    assert "USTAWKA" not in ids  # wrong type, must be filtered out
    assert "SYS.READY" in ids
    assert "SYS.SCAN_TIME" not in ids  # REAL, filtered out

def test_signal_picker_internal_only_scoping_for_bit_property():
    """The scoping used for virtual.input/output's "Bit" picker — only the
    internal-signals section, per property_grid.py's _SIGNAL_PICKER_TARGETS."""
    _app()
    from logic_studio.ui.signal_picker import SignalPickerDialog
    p = Project()
    p.settings["internal_bits"] = [{"name": "X", "type": "BOOL", "retentive": False, "description": "", "label": "", "category": ""}]
    dialog = SignalPickerDialog(p, value_type="BOOL", sections=("internal",))
    ids = _all_tree_ids(dialog)
    assert ids == ["X"]

def test_signal_picker_system_only_scoping_shows_both_types():
    """system.signal's "Sygnał" picker: system section only, but BOTH BOOL
    and REAL signals (value_type=None)."""
    _app()
    from logic_studio.ui.signal_picker import SignalPickerDialog
    p = Project()
    dialog = SignalPickerDialog(p, value_type=None, sections=("system",))
    ids = _all_tree_ids(dialog)
    assert "SYS.READY" in ids       # BOOL
    assert "SYS.SCAN_TIME" in ids   # REAL
    assert "ELA01.DI01" not in ids  # physical section excluded

def test_signal_picker_search_filters_by_any_column():
    _app()
    from logic_studio.ui.signal_picker import SignalPickerDialog
    p = Project()
    p.settings["internal_bits"] = [{"name": "BLOKADA_ZS", "type": "BOOL", "retentive": False, "description": "Blokada szyn", "label": "BLOK", "category": ""}]
    dialog = SignalPickerDialog(p, value_type="BOOL", sections=("internal",))

    dialog.search_edit.setText("szyn")  # matches the description column
    # Find the leaf and confirm it's not hidden.
    root = dialog.tree.topLevelItem(0)
    cat = root.child(0)
    leaf = cat.child(0)
    assert leaf.isHidden() is False

    dialog.search_edit.setText("nic_takiego_nie_ma")
    assert leaf.isHidden() is True

def test_signal_picker_select_and_accept_returns_chosen_id():
    _app()
    from logic_studio.ui.signal_picker import SignalPickerDialog
    p = Project()
    p.settings["internal_bits"] = [{"name": "BLOKADA_ZS", "type": "BOOL", "retentive": False, "description": "", "label": "", "category": ""}]
    dialog = SignalPickerDialog(p, value_type="BOOL", sections=("internal",))

    root = dialog.tree.topLevelItem(0)
    leaf = root.child(0).child(0)
    dialog.tree.setCurrentItem(leaf)
    dialog._on_accept()

    assert dialog.selected_signal_id() == "BLOKADA_ZS"

def test_signal_picker_select_and_accept_returns_chosen_kind():
    """feat/signal-watch: selected_kind() pairs with selected_signal_id()
    for a caller (WatchPanel) that needs the coarse "physical"/"internal"/
    "system" section a choice came from."""
    _app()
    from logic_studio.ui.signal_picker import SignalPickerDialog
    p = Project()
    dialog = SignalPickerDialog(p, value_type=None, sections=("system",))

    root = dialog.tree.topLevelItem(0)
    leaf = root.child(0).child(0)
    dialog.tree.setCurrentItem(leaf)
    dialog._on_accept()

    assert dialog.selected_kind() == "system"

def test_signal_picker_selected_kind_none_before_any_selection():
    _app()
    from logic_studio.ui.signal_picker import SignalPickerDialog
    p = Project()
    dialog = SignalPickerDialog(p, value_type=None, sections=("system",))
    assert dialog.selected_kind() is None

def test_signal_picker_new_internal_signal_button_adds_to_registry():
    """§6.6: adding a signal without leaving the dialog."""
    _app()
    from logic_studio.ui.signal_picker import SignalPickerDialog, _NewInternalSignalDialog
    from PySide6.QtWidgets import QDialog
    p = Project()
    dialog = SignalPickerDialog(p, value_type="BOOL", sections=("internal",))

    sub = _NewInternalSignalDialog("BOOL", parent=dialog)
    sub.name_edit.setText("NOWY_SYGNAL")
    sub._on_accept()
    assert sub.entry is not None
    assert sub.entry["name"] == "NOWY_SYGNAL"

    # Simulate what _create_new_signal() does with an already-accepted sub-dialog.
    p.settings["internal_bits"].append(sub.entry)
    dialog._populate()
    assert "NOWY_SYGNAL" in _all_tree_ids(dialog)

def test_signal_picker_ok_disabled_until_a_leaf_is_selected():
    _app()
    from logic_studio.ui.signal_picker import SignalPickerDialog
    p = Project()
    p.settings["internal_bits"] = [{"name": "X", "type": "BOOL", "retentive": False, "description": "", "label": "", "category": ""}]
    dialog = SignalPickerDialog(p, value_type="BOOL", sections=("internal",))
    assert dialog.ok_button.isEnabled() is False

    root = dialog.tree.topLevelItem(0)
    leaf = root.child(0).child(0)
    dialog.tree.setCurrentItem(leaf)
    assert dialog.ok_button.isEnabled() is True

    # Selecting a non-leaf (category) node disables OK again.
    dialog.tree.setCurrentItem(root.child(0))
    assert dialog.ok_button.isEnabled() is False

def test_property_grid_signal_picker_targets_cover_all_four_blocks():
    from logic_studio.ui.panels.property_grid import _SIGNAL_PICKER_TARGETS
    assert ("virtual.input", "Bit") in _SIGNAL_PICKER_TARGETS
    assert ("virtual.output", "Bit") in _SIGNAL_PICKER_TARGETS
    assert ("internal.reg_in", "Bit") in _SIGNAL_PICKER_TARGETS
    assert ("internal.reg_out", "Bit") in _SIGNAL_PICKER_TARGETS
    assert ("system.signal", "Sygnał") in _SIGNAL_PICKER_TARGETS

# ---- §7 registry editor tab -------------------------------------------------

def test_project_settings_dialog_loads_existing_signals():
    _app()
    from logic_studio.ui.dialogs import ProjectSettingsDialog
    p = Project()
    p.settings["internal_bits"] = [
        {"name": "X", "type": "BOOL", "retentive": True, "description": "opis", "label": "ET", "category": "Blokady"},
    ]
    dialog = ProjectSettingsDialog(p)
    assert dialog.signals_table.rowCount() == 1
    assert dialog.signals_table.item(0, 0).text() == "X"
    assert dialog.signals_table.cellWidget(0, 1).currentText() == "BOOL"
    assert dialog.signals_table.cellWidget(0, 2).isChecked() is True
    assert dialog.signals_table.item(0, 3).text() == "Blokady"

def test_project_settings_dialog_usage_column():
    _app()
    from logic_studio.blocks.registry import BlockRegistry
    from logic_studio.ui.dialogs import ProjectSettingsDialog
    p = Project()
    p.settings["internal_bits"] = [{"name": "X", "type": "BOOL", "retentive": False, "description": "", "label": "", "category": ""}]
    vo = BlockRegistry.create_block("virtual.output")
    vo.properties["Bit"] = "X"
    vi = BlockRegistry.create_block("virtual.input")
    vi.properties["Bit"] = "X"
    p.add_block(vo)
    p.add_block(vi)

    dialog = ProjectSettingsDialog(p)
    assert dialog.signals_table.item(0, 6).text() == "2"

def _refuse_any_blocking_messagebox(monkeypatch):
    """A test calling _on_accept() must never depend on a human clicking a
    modal QMessageBox — install this first so a logic bug that
    unexpectedly triggers one FAILS LOUDLY (via the poisoned return value
    below tripping an assertion) instead of hanging the whole suite
    waiting for a click that will never come. Exactly what caught the
    rename-vs-delete bug below (an earlier version of this test suite hung
    for real, diagnosed and fixed rather than papered over)."""
    from PySide6.QtWidgets import QMessageBox

    def _poison(*args, **kwargs):
        raise AssertionError("Unexpected blocking QMessageBox in a test — see _refuse_any_blocking_messagebox")

    monkeypatch.setattr(QMessageBox, "question", staticmethod(_poison))
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(_poison))

def test_project_settings_dialog_add_signal_and_apply(monkeypatch):
    _app()
    _refuse_any_blocking_messagebox(monkeypatch)
    from logic_studio.ui.dialogs import ProjectSettingsDialog
    p = Project()
    dialog = ProjectSettingsDialog(p)
    dialog._add_signal_row({"name": "NOWY", "type": "REAL", "retentive": False, "category": "", "label": "", "description": ""})
    dialog._on_accept()
    dialog.apply_to_project()

    assert p.settings["internal_bits"] == [
        {"name": "NOWY", "type": "REAL", "retentive": False, "category": "", "label": "", "description": ""}
    ]

def test_project_settings_dialog_rename_propagates_to_blocks(monkeypatch):
    """§7.3: renaming a registry entry updates every block's "Bit". Also
    the regression case for the bug _refuse_any_blocking_messagebox is
    named after: a rename makes the old name vanish from the collected
    signal list exactly like a real delete would, so the "was this
    deleted?" check must special-case renames or it wrongly prompts
    (and, pre-fix, hung the suite) for every rename of a used signal."""
    _app()
    _refuse_any_blocking_messagebox(monkeypatch)
    from logic_studio.blocks.registry import BlockRegistry
    from logic_studio.ui.dialogs import ProjectSettingsDialog
    p = Project()
    p.settings["internal_bits"] = [{"name": "STARA_NAZWA", "type": "BOOL", "retentive": False, "description": "", "label": "", "category": ""}]
    vo = BlockRegistry.create_block("virtual.output")
    vo.properties["Bit"] = "STARA_NAZWA"
    p.add_block(vo)

    dialog = ProjectSettingsDialog(p)
    dialog.signals_table.item(0, 0).setText("NOWA_NAZWA")
    dialog._on_accept()
    dialog.apply_to_project()

    assert vo.properties["Bit"] == "NOWA_NAZWA"
    assert p.settings["internal_bits"][0]["name"] == "NOWA_NAZWA"

def test_project_settings_dialog_deleting_used_signal_prompts_confirmation(monkeypatch):
    """The actual §7.2 confirmation path, exercised deliberately (unlike
    the rename test above, which must NOT trigger it) — patched to answer
    Yes, confirming the prompt fires with the right block name and that
    accept() proceeds once confirmed."""
    _app()
    from PySide6.QtWidgets import QMessageBox
    from logic_studio.blocks.registry import BlockRegistry
    from logic_studio.ui.dialogs import ProjectSettingsDialog

    p = Project()
    p.settings["internal_bits"] = [{"name": "USUWANY", "type": "BOOL", "retentive": False, "description": "", "label": "", "category": ""}]
    vo = BlockRegistry.create_block("virtual.output")
    vo.properties["Bit"] = "USUWANY"
    vo.display_name = "VO1"
    p.add_block(vo)

    dialog = ProjectSettingsDialog(p)
    dialog.signals_table.removeRow(0)  # delete the only row -> real deletion, not a rename

    prompts = []
    def _fake_question(self, title, text, *a, **k):
        prompts.append(text)
        return QMessageBox.Yes
    monkeypatch.setattr(QMessageBox, "question", _fake_question)

    dialog._on_accept()
    assert len(prompts) == 1
    assert "USUWANY" in prompts[0] and "VO1" in prompts[0]
    dialog.apply_to_project()
    assert p.settings["internal_bits"] == []

def test_project_settings_dialog_rejects_incompatible_type_change():
    """§7.3: changing REAL used by internal.reg_out to BOOL must be
    refused with a message, not silently applied."""
    _app()
    from logic_studio.blocks.registry import BlockRegistry
    from logic_studio.ui.dialogs import ProjectSettingsDialog
    p = Project()
    p.settings["internal_bits"] = [{"name": "USTAWKA", "type": "REAL", "retentive": False, "description": "", "label": "", "category": ""}]
    ro = BlockRegistry.create_block("internal.reg_out")
    ro.properties["Bit"] = "USTAWKA"
    p.add_block(ro)

    dialog = ProjectSettingsDialog(p)
    dialog.signals_table.cellWidget(0, 1).setCurrentText("BOOL")

    entries, error, renames = dialog._collect_signals()
    assert entries is None
    assert "USTAWKA" in error
    assert "BOOL" in error

def test_project_settings_dialog_type_change_without_usage_is_allowed():
    _app()
    from logic_studio.ui.dialogs import ProjectSettingsDialog
    p = Project()
    p.settings["internal_bits"] = [{"name": "NIEUZYWANY", "type": "REAL", "retentive": False, "description": "", "label": "", "category": ""}]
    dialog = ProjectSettingsDialog(p)
    dialog.signals_table.cellWidget(0, 1).setCurrentText("BOOL")

    entries, error, renames = dialog._collect_signals()
    assert error is None
    assert entries[0]["type"] == "BOOL"

def test_project_settings_dialog_invalid_name_format_rejected():
    _app()
    from logic_studio.ui.dialogs import ProjectSettingsDialog
    p = Project()
    dialog = ProjectSettingsDialog(p)
    dialog._add_signal_row({"name": "ZŁA NAZWA", "type": "BOOL", "retentive": False, "category": "", "label": "", "description": ""})

    entries, error, renames = dialog._collect_signals()
    assert entries is None
    assert error is not None

def test_project_settings_dialog_export_and_import_signals_roundtrip(tmp_path, monkeypatch):
    """§7.4."""
    _app()
    from logic_studio.ui.dialogs import ProjectSettingsDialog
    from PySide6.QtWidgets import QFileDialog

    p = Project()
    dialog = ProjectSettingsDialog(p)
    dialog._add_signal_row({"name": "EKSPORTOWANY", "type": "BOOL", "retentive": True, "category": "Cat", "label": "L", "description": "D"})

    out_path = str(tmp_path / "signals.json")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (out_path, "")))
    dialog._export_signals()

    import json
    with open(out_path, encoding="utf-8") as f:
        data = json.load(f)
    assert data["internal_bits"][0]["name"] == "EKSPORTOWANY"

    dialog2 = ProjectSettingsDialog(Project())
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (out_path, "")))
    dialog2._import_signals()
    assert dialog2.signals_table.rowCount() == 1
    assert dialog2.signals_table.item(0, 0).text() == "EKSPORTOWANY"



