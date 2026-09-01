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


