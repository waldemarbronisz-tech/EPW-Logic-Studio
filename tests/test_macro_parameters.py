"""fix/safety-and-macro-params §C — macro instance parameters: the data
model (§C1), UI for creating bindings (§C2), compile-time substitution
(§C3), validation (§C4). Pure-logic tests (core/macros.py, no Qt) are
grouped first, matching test_macros.py's own style; UI/end-to-end tests
(MainWindow, PropertyGridPanel, MacroPinsDialog) follow, matching
test_macro_pin_editing.py's own fixture shape.
"""
import pytest
from PySide6.QtWidgets import QApplication

from logic_studio.blocks import register_builtin_blocks
from logic_studio.blocks.registry import BlockRegistry
from logic_studio.blocks.macro_instance import MacroInstanceBlock
from logic_studio.core.project import Project
from logic_studio.core import macros as M
from logic_studio.compiler.core import Compiler

register_builtin_blocks()


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _close(window):
    window.is_dirty = False
    window.close()


# ---- fixtures (pure logic) ---------------------------------------------

def _ton_macro_definition(preset_ms=500):
    """One TON, In/Q exposed (wired to throwaway DI/DO purely to produce
    the crossings build_definition() needs — see test_macros.py's own
    _and_macro_definition() for the same trick), Preset (ms) NOT yet
    bound to anything — callers add that themselves."""
    ton = BlockRegistry.create_block("timer.ton")
    ton.properties["Preset (ms)"] = preset_ms
    dummy_di = BlockRegistry.create_block("input.di")
    dummy_do = BlockRegistry.create_block("output.do")
    dummy_di.outputs[0].connect(ton.inputs[0])
    ton.outputs[0].connect(dummy_do.inputs[0])
    definition, _ = M.build_definition("BlokadaZwloczna", [ton])
    return definition, ton.uuid


def _make_delay_macro(project, preset_ms=500, bind=True):
    """Registers a TON-based "delay" macro in `project`, with a "Zwloka"
    (INT, ms) parameter bound to Preset (ms) unless `bind=False`. Returns
    (def_id, ton_uuid, param_name_or_None)."""
    definition, ton_uuid = _ton_macro_definition(preset_ms)
    def_id = M.new_def_id()
    M.set_definition(project, def_id, definition)
    param_name = None
    if bind:
        param_name = M.add_parameter(project, def_id, "Zwloka", "INT", preset_ms, unit="ms")
        M.add_parameter_binding(project, def_id, param_name, ton_uuid, "Preset (ms)")
    return def_id, ton_uuid, param_name


def _place_instance(project, def_id, in_addr, out_addr, param_value=None):
    definition = M.get_definition(project, def_id)
    di = BlockRegistry.create_block("input.di")
    di.properties["Address"] = in_addr
    instance = MacroInstanceBlock(def_id)
    instance.configure(definition)
    di.outputs[0].connect(instance.inputs[0])
    do = BlockRegistry.create_block("output.do")
    do.properties["Address"] = out_addr
    instance.outputs[0].connect(do.inputs[0])
    if param_value is not None:
        instance.update_property("Zwloka", str(param_value))
    project.add_block(di)
    project.add_block(instance)
    project.add_block(do)
    return instance


# ---- §C1: data model ---------------------------------------------------

def test_fresh_definition_has_empty_parameters_and_bindings():
    definition, _ = _ton_macro_definition()
    assert definition["parameters"] == []
    assert definition["parameter_bindings"] == []

def test_add_parameter_returns_a_stable_internal_name():
    p = Project()
    def_id, ton_uuid, _ = _make_delay_macro(p, bind=False)
    name = M.add_parameter(p, def_id, "Zwloka", "INT", 500, unit="ms", description="Czas opóźnienia")
    param = M.get_parameter(p, def_id, name)
    assert param["display_name"] == "Zwloka"
    assert param["type"] == "INT"
    assert param["default"] == 500
    assert param["unit"] == "ms"
    assert param["description"] == "Czas opóźnienia"

def test_add_parameter_names_are_unique_and_sequential():
    p = Project()
    def_id, _, _ = _make_delay_macro(p, bind=False)
    n1 = M.add_parameter(p, def_id, "A", "INT", 1)
    n2 = M.add_parameter(p, def_id, "B", "INT", 2)
    assert n1 != n2
    assert {n1, n2} == {"PARAM_1", "PARAM_2"}

def test_remove_parameter_also_removes_its_bindings():
    p = Project()
    def_id, ton_uuid, param_name = _make_delay_macro(p)
    assert M.get_parameter_bindings(p, def_id, param_name)

    assert M.remove_parameter(p, def_id, param_name) is True

    definition = M.get_definition(p, def_id)
    assert definition["parameters"] == []
    assert definition["parameter_bindings"] == []

def test_remove_parameter_returns_false_for_unknown_name():
    p = Project()
    def_id, _, _ = _make_delay_macro(p, bind=False)
    assert M.remove_parameter(p, def_id, "NOT_REAL") is False

def test_update_parameter_edits_fields_in_place():
    p = Project()
    def_id, _, param_name = _make_delay_macro(p)
    assert M.update_parameter(p, def_id, param_name, display_name="Nowa nazwa", unit="s") is True
    param = M.get_parameter(p, def_id, param_name)
    assert param["display_name"] == "Nowa nazwa"
    assert param["unit"] == "s"
    assert param["type"] == "INT"  # untouched field survives

def test_reorder_parameters():
    p = Project()
    def_id, _, _ = _make_delay_macro(p, bind=False)
    a = M.add_parameter(p, def_id, "A", "INT", 1)
    b = M.add_parameter(p, def_id, "B", "INT", 2)
    assert M.reorder_parameters(p, def_id, [b, a]) is True
    names = [p_["name"] for p_ in M.get_parameters(p, def_id)]
    assert names == [b, a]

def test_reorder_parameters_rejects_a_mismatched_set():
    p = Project()
    def_id, _, _ = _make_delay_macro(p, bind=False)
    M.add_parameter(p, def_id, "A", "INT", 1)
    assert M.reorder_parameters(p, def_id, ["NOT_REAL"]) is False

def test_add_parameter_binding_rejects_unknown_block_or_property():
    p = Project()
    def_id, ton_uuid, _ = _make_delay_macro(p, bind=False)
    name = M.add_parameter(p, def_id, "Zwloka", "INT", 500)
    assert M.add_parameter_binding(p, def_id, name, "not-a-real-uuid", "Preset (ms)") is False
    assert M.add_parameter_binding(p, def_id, name, ton_uuid, "Not A Real Property") is False

def test_add_parameter_binding_rejects_duplicate():
    p = Project()
    def_id, ton_uuid, param_name = _make_delay_macro(p)
    assert M.add_parameter_binding(p, def_id, param_name, ton_uuid, "Preset (ms)") is False

def test_remove_parameter_binding():
    p = Project()
    def_id, ton_uuid, param_name = _make_delay_macro(p)
    assert M.remove_parameter_binding(p, def_id, ton_uuid, "Preset (ms)") is True
    assert M.get_parameter_bindings(p, def_id, param_name) == []

def test_binding_for_property():
    p = Project()
    def_id, ton_uuid, param_name = _make_delay_macro(p)
    definition = M.get_definition(p, def_id)
    assert M.binding_for_property(definition, ton_uuid, "Preset (ms)") == param_name
    assert M.binding_for_property(definition, ton_uuid, "Something Else") is None

def test_value_matches_param_type():
    assert M.value_matches_param_type(5, "INT") is True
    assert M.value_matches_param_type(True, "INT") is False  # bool is not INT, same isinstance trap base.py itself avoids
    assert M.value_matches_param_type(5.0, "REAL") is True
    assert M.value_matches_param_type(5, "REAL") is True  # an int is an acceptable REAL
    assert M.value_matches_param_type(True, "BOOL") is True
    assert M.value_matches_param_type("x", "STRING") is True
    assert M.value_matches_param_type("x", "ENUM") is True
    assert M.value_matches_param_type(5, "STRING") is False


# ---- §C1.3/§C1.4: sync_instance_parameters() ----------------------------

def test_sync_gives_a_fresh_instance_the_default_value():
    p = Project()
    def_id, _, _ = _make_delay_macro(p)
    definition = M.get_definition(p, def_id)
    props = {"Address": "", "Tag": "", "Comment": ""}
    resets = M.sync_instance_parameters(props, definition)
    assert props["Zwloka"] == 500
    assert resets == []

def test_sync_preserves_an_existing_compatible_value():
    p = Project()
    def_id, _, _ = _make_delay_macro(p)
    definition = M.get_definition(p, def_id)
    props = {"Zwloka": 777}
    M.sync_instance_parameters(props, definition)
    assert props["Zwloka"] == 777

def test_sync_removes_a_deleted_parameters_leftover_property():
    p = Project()
    def_id, _, param_name = _make_delay_macro(p)
    definition = M.get_definition(p, def_id)
    props = {"Zwloka": 777}
    M.remove_parameter(p, def_id, param_name)
    definition2 = M.get_definition(p, def_id)
    M.sync_instance_parameters(props, definition2)
    assert "Zwloka" not in props

def test_sync_resets_a_value_whose_type_no_longer_matches():
    p = Project()
    def_id, _, param_name = _make_delay_macro(p)
    definition = M.get_definition(p, def_id)
    props = {"Zwloka": 777}
    M.update_parameter(p, def_id, param_name, type="STRING", default="auto")
    definition2 = M.get_definition(p, def_id)
    resets = M.sync_instance_parameters(props, definition2)
    assert props["Zwloka"] == "auto"
    assert resets == [("Zwloka", "STRING")]

def test_sync_never_touches_base_properties():
    p = Project()
    def_id, _, _ = _make_delay_macro(p)
    definition = M.get_definition(p, def_id)
    props = {"Address": "ELA01.DI01", "Tag": "T1", "Comment": "c"}
    M.sync_instance_parameters(props, definition)
    assert props["Address"] == "ELA01.DI01"
    assert props["Tag"] == "T1"
    assert props["Comment"] == "c"


# ---- §C1.3: MacroInstanceBlock.configure() -------------------------------

def test_configure_gives_the_instance_a_property_per_parameter():
    p = Project()
    def_id, _, _ = _make_delay_macro(p)
    definition = M.get_definition(p, def_id)
    instance = MacroInstanceBlock(def_id)
    instance.configure(definition)
    assert instance.properties["Zwloka"] == 500

def test_updating_the_parameter_property_uses_generic_type_casting():
    p = Project()
    def_id, _, _ = _make_delay_macro(p)
    definition = M.get_definition(p, def_id)
    instance = MacroInstanceBlock(def_id)
    instance.configure(definition)
    instance.update_property("Zwloka", "700")
    assert instance.properties["Zwloka"] == 700
    assert isinstance(instance.properties["Zwloka"], int)


# ---- §C5.1: THE flagship test — two instances, independent nastawy -----

def test_two_instances_of_the_same_macro_keep_independent_presets_and_timing():
    from logic_studio.engine.execution import ExecutionEngine
    from logic_studio.engine.io_provider import SimulationIOProvider
    from logic_studio.engine.time_provider import SimulationTimeProvider

    p = Project()
    def_id, ton_uuid, _ = _make_delay_macro(p, preset_ms=500)
    inst1 = _place_instance(p, def_id, "ELA01.DI01", "ADA01.DO01", param_value=300)
    inst2 = _place_instance(p, def_id, "ELA01.DI02", "ADA01.DO02", param_value=700)

    c = Compiler(p)
    res = c.compile()
    assert res is not None, f"Compile failed: {c.errors}"

    eng = ExecutionEngine(res["program"], SimulationIOProvider(), SimulationTimeProvider())
    eng.io.set_digital_input("ELA01.DI01", True)
    eng.io.set_digital_input("ELA01.DI02", True)
    eng.start()

    # step() N is evaluated AT engine time (N-1)*100ms (the clock only
    # moves via advance(), called AFTER each step()) — 4 iterations means
    # the 4th (last) step() runs at t=300ms.
    for _ in range(4):
        eng.step()
        eng.time.advance(100)
    assert eng.io.read_digital_output("ADA01.DO01") is True  # 300ms instance has fired
    assert eng.io.read_digital_output("ADA01.DO02") is False  # 700ms instance hasn't yet

    for _ in range(4):  # 4 more steps reach the 8th, at t=700ms
        eng.step()
        eng.time.advance(100)
    assert eng.io.read_digital_output("ADA01.DO02") is True  # now it has too

def test_compiled_ton_properties_carry_each_instances_own_value():
    p = Project()
    def_id, ton_uuid, _ = _make_delay_macro(p, preset_ms=500)
    inst1 = _place_instance(p, def_id, "ELA01.DI01", "ADA01.DO01", param_value=300)
    inst2 = _place_instance(p, def_id, "ELA01.DI02", "ADA01.DO02", param_value=700)

    expanded, errors = M.expand_project(p)
    assert errors == []
    presets = sorted(b.properties["Preset (ms)"] for b in expanded if b.type_id == "timer.ton")
    assert presets == [300, 700]

def test_unbound_instance_falls_back_to_the_definitions_own_value():
    """An instance whose parameter was never edited from its default —
    the substituted value is just the default, same as if the property
    had never been a parameter at all."""
    p = Project()
    def_id, ton_uuid, _ = _make_delay_macro(p, preset_ms=500)
    _place_instance(p, def_id, "ELA01.DI01", "ADA01.DO01")  # no param_value override

    expanded, errors = M.expand_project(p)
    assert errors == []
    ton = next(b for b in expanded if b.type_id == "timer.ton")
    assert ton.properties["Preset (ms)"] == 500


# ---- §C5.2: nested macro parameter passthrough --------------------------

def test_nested_macro_parameter_reaches_the_deepest_block():
    inner_def, inner_ton_uuid = _ton_macro_definition(preset_ms=111)
    p = Project()
    inner_id = M.new_def_id()
    M.set_definition(p, inner_id, inner_def)
    inner_pname = M.add_parameter(p, inner_id, "Zwloka", "INT", 111, unit="ms")
    M.add_parameter_binding(p, inner_id, inner_pname, inner_ton_uuid, "Preset (ms)")
    inner_def = M.get_definition(p, inner_id)

    # Outer macro: buffer -> inner instance -> buffer (a definition's own
    # exposed pin must anchor a plain internal block, never a nested
    # macro instance directly — AUDIT_REPORT.md §32/ARCHITECTURE.md
    # §24.10, pre-existing and unrelated to parameters).
    inner_instance = MacroInstanceBlock(inner_id)
    inner_instance.configure(inner_def)
    buf_in = BlockRegistry.create_block("logic.buffer")
    buf_out = BlockRegistry.create_block("logic.buffer")
    buf_in.outputs[0].connect(inner_instance.inputs[0])
    inner_instance.outputs[0].connect(buf_out.inputs[0])
    dummy_di = BlockRegistry.create_block("input.di")
    dummy_do = BlockRegistry.create_block("output.do")
    dummy_di.outputs[0].connect(buf_in.inputs[0])
    buf_out.outputs[0].connect(dummy_do.inputs[0])
    outer_def, _ = M.build_definition("Outer", [buf_in, inner_instance, buf_out])

    outer_id = M.new_def_id()
    M.set_definition(p, outer_id, outer_def)
    outer_pname = M.add_parameter(p, outer_id, "OuterZwloka", "INT", 222, unit="ms")
    assert M.add_parameter_binding(p, outer_id, outer_pname, inner_instance.uuid, "Zwloka") is True
    outer_def = M.get_definition(p, outer_id)

    di = BlockRegistry.create_block("input.di"); di.properties["Address"] = "ELA01.DI01"
    outer_instance = MacroInstanceBlock(outer_id)
    outer_instance.configure(outer_def)
    outer_instance.update_property("OuterZwloka", "999")
    di.outputs[0].connect(outer_instance.inputs[0])
    do = BlockRegistry.create_block("output.do"); do.properties["Address"] = "ADA01.DO01"
    outer_instance.outputs[0].connect(do.inputs[0])
    p.add_block(di); p.add_block(outer_instance); p.add_block(do)

    expanded, errors = M.expand_project(p)
    assert errors == []
    ton = next(b for b in expanded if b.type_id == "timer.ton")
    assert ton.properties["Preset (ms)"] == 999


# ---- §C5.3: resync on definition changes --------------------------------

def test_resync_gives_existing_instances_a_newly_added_parameter():
    p = Project()
    def_id, ton_uuid, _ = _make_delay_macro(p, bind=False)
    instance = _place_instance(p, def_id, "ELA01.DI01", "ADA01.DO01")
    assert "Zwloka" not in instance.properties

    name = M.add_parameter(p, def_id, "Zwloka", "INT", 500, unit="ms")
    M.add_parameter_binding(p, def_id, name, ton_uuid, "Preset (ms)")
    M.resync_all_instances(p, def_id, [p.blocks])

    assert instance.properties["Zwloka"] == 500

def test_resync_removes_a_deleted_parameters_property_from_instances():
    p = Project()
    def_id, ton_uuid, param_name = _make_delay_macro(p)
    instance = _place_instance(p, def_id, "ELA01.DI01", "ADA01.DO01", param_value=700)
    assert instance.properties["Zwloka"] == 700

    M.remove_parameter(p, def_id, param_name)
    M.resync_all_instances(p, def_id, [p.blocks])

    assert "Zwloka" not in instance.properties

def test_resync_reports_and_resets_a_type_change():
    p = Project()
    def_id, ton_uuid, param_name = _make_delay_macro(p)
    instance = _place_instance(p, def_id, "ELA01.DI01", "ADA01.DO01", param_value=700)

    M.update_parameter(p, def_id, param_name, type="STRING", default="auto")
    notices = M.resync_all_instances(p, def_id, [p.blocks])

    assert instance.properties["Zwloka"] == "auto"
    assert len(notices) == 1
    assert "Zwloka" in notices[0]
    assert "STRING" in notices[0]
    assert instance.short_id in notices[0] or instance.display_name in notices[0]

def test_resync_touches_a_nested_instance_embedded_as_dict_data():
    """The other kind of instance resync_all_instances() has to handle —
    one embedded in ANOTHER definition's own stored data, not live
    anywhere right now (mirrors test_macros.py's own equivalent pin test
    for the same case)."""
    inner_def, inner_ton_uuid = _ton_macro_definition()
    p = Project()
    inner_id = M.new_def_id()
    M.set_definition(p, inner_id, inner_def)
    name = M.add_parameter(p, inner_id, "Zwloka", "INT", 500, unit="ms")
    M.add_parameter_binding(p, inner_id, name, inner_ton_uuid, "Preset (ms)")
    inner_def = M.get_definition(p, inner_id)

    inner_instance = MacroInstanceBlock(inner_id)
    inner_instance.configure(inner_def)
    inner_instance.update_property("Zwloka", "700")
    buf_in = BlockRegistry.create_block("logic.buffer")
    buf_out = BlockRegistry.create_block("logic.buffer")
    buf_in.outputs[0].connect(inner_instance.inputs[0])
    inner_instance.outputs[0].connect(buf_out.inputs[0])
    dummy_di = BlockRegistry.create_block("input.di")
    dummy_do = BlockRegistry.create_block("output.do")
    dummy_di.outputs[0].connect(buf_in.inputs[0])
    buf_out.outputs[0].connect(dummy_do.inputs[0])
    outer_def, _ = M.build_definition("Outer", [buf_in, inner_instance, buf_out])
    outer_id = M.new_def_id()
    M.set_definition(p, outer_id, outer_def)

    # p.blocks has no LIVE instance of `inner_id` — only inside Outer's own stored data.
    M.remove_parameter(p, inner_id, name)
    M.resync_all_instances(p, inner_id, [p.blocks])

    outer_def_after = M.get_definition(p, outer_id)
    inner_b_data = next(b for b in outer_def_after["blocks"] if b["type_id"] == f"macro.{inner_id}")
    assert "Zwloka" not in inner_b_data["properties"]


# ---- §C5.4: round-trip ----------------------------------------------------

def test_serialize_deserialize_preserves_instance_parameter_values():
    p = Project()
    def_id, ton_uuid, _ = _make_delay_macro(p, preset_ms=500)
    inst1 = _place_instance(p, def_id, "ELA01.DI01", "ADA01.DO01", param_value=300)
    inst2 = _place_instance(p, def_id, "ELA01.DI02", "ADA01.DO02", param_value=700)

    data = p.serialize()
    reloaded = Project.deserialize(data)

    reloaded_insts = {b.properties.get("Address"): None for b in reloaded.blocks}
    by_uuid = {b.uuid: b for b in reloaded.blocks}
    r1 = by_uuid[inst1.uuid]
    r2 = by_uuid[inst2.uuid]
    assert r1.properties["Zwloka"] == 300
    assert r2.properties["Zwloka"] == 700

def test_round_tripped_project_still_compiles_with_the_right_presets():
    p = Project()
    def_id, ton_uuid, _ = _make_delay_macro(p, preset_ms=500)
    _place_instance(p, def_id, "ELA01.DI01", "ADA01.DO01", param_value=300)
    _place_instance(p, def_id, "ELA01.DI02", "ADA01.DO02", param_value=700)

    reloaded = Project.deserialize(p.serialize())
    expanded, errors = M.expand_project(reloaded)
    assert errors == []
    presets = sorted(b.properties["Preset (ms)"] for b in expanded if b.type_id == "timer.ton")
    assert presets == [300, 700]


# ---- §C5.5: validation (§C4) ---------------------------------------------

def test_validation_error_binding_to_a_nonexistent_block():
    p = Project()
    def_id, ton_uuid, param_name = _make_delay_macro(p)
    definition = M.get_definition(p, def_id)
    definition["parameter_bindings"][0]["block_uuid"] = "not-a-real-uuid"
    M.set_definition(p, def_id, definition)

    c = Compiler(p)
    res = c.compile()
    assert res is None
    assert any("nieistniejący blok" in e for e in c.errors)

def test_validation_error_binding_to_a_nonexistent_parameter():
    p = Project()
    def_id, ton_uuid, param_name = _make_delay_macro(p)
    definition = M.get_definition(p, def_id)
    definition["parameter_bindings"][0]["parameter"] = "NOT_REAL"
    M.set_definition(p, def_id, definition)

    c = Compiler(p)
    res = c.compile()
    assert res is None
    assert any("nieistniejący parametr" in e for e in c.errors)

def test_validation_error_type_mismatch_between_parameter_and_property():
    p = Project()
    def_id, ton_uuid, param_name = _make_delay_macro(p)
    M.update_parameter(p, def_id, param_name, type="STRING")

    c = Compiler(p)
    res = c.compile()
    assert res is None
    assert any("nie zgadza się z typem" in e for e in c.errors)

def test_validation_warning_unbound_parameter():
    p = Project()
    def_id, ton_uuid, _ = _make_delay_macro(p, bind=False)
    M.add_parameter(p, def_id, "Zwloka", "INT", 500)

    c = Compiler(p)
    res = c.compile()
    assert res is not None, f"Compile failed: {c.errors}"
    assert any("nie jest powiązany" in w for w in c.warnings)

def test_validation_warning_two_parameters_bound_to_the_same_property():
    p = Project()
    def_id, ton_uuid, param_name = _make_delay_macro(p)
    second = M.add_parameter(p, def_id, "Zwloka2", "INT", 999)
    M.add_parameter_binding(p, def_id, second, ton_uuid, "Preset (ms)")

    c = Compiler(p)
    res = c.compile()
    assert res is not None, f"Compile failed: {c.errors}"
    assert any("Więcej niż jeden parametr" in w for w in c.warnings)

def test_validation_value_out_of_range_uses_the_blocks_own_existing_rule():
    """§C4's third BŁĄD ("wartość parametru poza dopuszczalnym zakresem
    właściwości, np. czas ujemny") needs no macro-specific rule at all —
    substitution already happened before Validator runs, so whatever
    range check the bound property's OWN block type already has (here:
    const.time's "nie może być ujemny") fires on the substituted value
    exactly as if it had been typed in directly."""
    const_time = BlockRegistry.create_block("const.time")
    const_time.properties["Time (ms)"] = 1000
    dummy_do = BlockRegistry.create_block("output.do")
    const_time.outputs[0].connect(dummy_do.inputs[0])
    definition, _ = M.build_definition("NegTest", [const_time])

    p = Project()
    def_id = M.new_def_id()
    M.set_definition(p, def_id, definition)
    name = M.add_parameter(p, def_id, "Czas", "INT", 1000, unit="ms")
    M.add_parameter_binding(p, def_id, name, const_time.uuid, "Time (ms)")
    definition = M.get_definition(p, def_id)

    instance = MacroInstanceBlock(def_id)
    instance.configure(definition)
    instance.update_property("Czas", "-500")
    p.add_block(instance)

    c = Compiler(p)
    res = c.compile()
    assert res is None
    assert any("nie może być ujemn" in e for e in c.errors)


# ---- §C5.6: backward compatibility ---------------------------------------

def test_a_macro_with_no_parameters_compiles_and_behaves_unchanged():
    p = Project()
    def_id, ton_uuid, _ = _make_delay_macro(p, preset_ms=500, bind=False)
    _place_instance(p, def_id, "ELA01.DI01", "ADA01.DO01")

    c = Compiler(p)
    res = c.compile()
    assert res is not None, f"Compile failed: {c.errors}"

    expanded, errors = M.expand_project(p)
    assert errors == []
    ton = next(b for b in expanded if b.type_id == "timer.ton")
    assert ton.properties["Preset (ms)"] == 500  # the definition's own value, untouched

def test_a_definition_missing_the_parameters_key_entirely_still_loads():
    """A hand-crafted / genuinely pre-this-feature definition dict — no
    "parameters"/"parameter_bindings" key at all, not even an empty list —
    _copy_definition() must default both rather than KeyError."""
    p = Project()
    raw = {"name": "Old", "blocks": [], "input_pins": [], "output_pins": []}
    M.set_definition(p, "old1", raw)
    definition = M.get_definition(p, "old1")
    assert definition["parameters"] == []
    assert definition["parameter_bindings"] == []

def test_export_runtime_carries_no_trace_of_macros_or_parameters():
    """§C3.3: confirms the claim directly — nothing in the exported
    EPW_RUNTIME_LOGIC names a macro, a parameter, or a binding; only the
    already-substituted, ordinary property values. Compiler.compile()'s
    OWN return value already IS the exported dict (plus a "program" key
    holding the live CompiledProgram, excluded here — it's not part of
    the export contract, see exporter.py's own CHECKSUM_FIELDS)."""
    p = Project()
    def_id, ton_uuid, _ = _make_delay_macro(p, preset_ms=500)
    _place_instance(p, def_id, "ELA01.DI01", "ADA01.DO01", param_value=300)

    c = Compiler(p)
    res = c.compile()
    assert res is not None, f"Compile failed: {c.errors}"

    exported_only = {k: v for k, v in res.items() if k not in ("program", "cycle_delayed_reads")}
    dumped = str(exported_only)
    assert "macro" not in dumped.lower()
    assert "parameter" not in dumped.lower()
    assert not any(b["type_id"].startswith("macro.") for b in exported_only["blocks"].values())
    ton_entries = [b for b in exported_only["blocks"].values() if b["type_id"] == "timer.ton"]
    assert len(ton_entries) == 1
    assert ton_entries[0]["properties"]["Preset (ms)"] == 300


# ---- UI: property panel binding flow (§C2.1/§C2.2/§C2.3/§C2.5) ---------

def _make_window_with_ton_macro(qsettings):
    from logic_studio.ui.main_window import MainWindow

    window = MainWindow(settings=qsettings)
    window.scene.clear()
    window.scene.add_block_from_library("input.di", 0, 0)
    window.scene.add_block_from_library("timer.ton", 200, 0)
    window.scene.add_block_from_library("output.do", 400, 0)
    di, ton, do = window.project.blocks
    di.outputs[0].connect(ton.inputs[0])
    ton.outputs[0].connect(do.inputs[0])
    from logic_studio.ui.canvas.block_item import BlockItem
    for item in [i for i in window.scene.items() if isinstance(i, BlockItem)]:
        if item.logic_block is ton:
            item.setSelected(True)
    window.scene.create_macro_from_selection("BlokadaZwloczna")

    instance = next(b for b in window.project.blocks if isinstance(b, MacroInstanceBlock))
    return window, instance, ton

def test_binding_created_from_the_property_panel_appears_in_the_definition(qsettings):
    _app()
    window, instance, ton = _make_window_with_ton_macro(qsettings)
    window.enter_macro_instance(instance)
    ton_inside = next(b for b in window.project.blocks if b.type_id == "timer.ton")

    window.property_panel.load_block_properties(ton_inside, window.project, window.current_macro_def_id)

    from logic_studio.core.macros import get_definition
    def_id = window.current_macro_def_id
    from logic_studio.ui.macro_parameter_dialog import BindParameterDialog
    definition = get_definition(window.project, def_id)
    dialog = BindParameterDialog(definition, "Preset (ms)", ton_inside.properties["Preset (ms)"], parent=window)
    dialog._new_entry = {"display_name": "Zwloka", "type": "INT", "default": 500, "unit": "ms", "description": ""}

    # Drive the same commit path _open_bind_parameter_dialog() would after dialog.exec():
    from logic_studio.core import macros as macros_module
    param_name = dialog.result_parameter_name(window.project, def_id)
    window.project.push_state()
    window.set_dirty()
    macros_module.add_parameter_binding(window.project, def_id, param_name, ton_inside.uuid, "Preset (ms)")
    window._resync_macro_instances(def_id)

    definition_after = get_definition(window.project, def_id)
    assert definition_after["parameters"][0]["display_name"] == "Zwloka"
    assert definition_after["parameter_bindings"][0]["property_name"] == "Preset (ms)"
    _close(window)

def test_bound_property_row_shows_unbind_button_not_the_editor(qsettings):
    _app()
    window, instance, ton = _make_window_with_ton_macro(qsettings)
    window.enter_macro_instance(instance)
    ton_inside = next(b for b in window.project.blocks if b.type_id == "timer.ton")
    def_id = window.current_macro_def_id

    from logic_studio.core import macros as macros_module
    name = macros_module.add_parameter(window.project, def_id, "Zwloka", "INT", 500, unit="ms")
    macros_module.add_parameter_binding(window.project, def_id, name, ton_inside.uuid, "Preset (ms)")

    window.property_panel.load_block_properties(ton_inside, window.project, def_id)
    row = window.property_panel.field_widget("Preset")
    children = [row.layout().itemAt(i).widget() for i in range(row.layout().count())]
    assert any("Odłącz" in getattr(w, "text", lambda: "")() for w in children)
    _close(window)

def test_unbinding_a_property_removes_the_binding(qsettings):
    _app()
    window, instance, ton = _make_window_with_ton_macro(qsettings)
    window.enter_macro_instance(instance)
    ton_inside = next(b for b in window.project.blocks if b.type_id == "timer.ton")
    def_id = window.current_macro_def_id

    from logic_studio.core import macros as macros_module
    name = macros_module.add_parameter(window.project, def_id, "Zwloka", "INT", 500, unit="ms")
    macros_module.add_parameter_binding(window.project, def_id, name, ton_inside.uuid, "Preset (ms)")

    window.property_panel.load_block_properties(ton_inside, window.project, def_id)
    window.property_panel._unbind_parameter(def_id, ton_inside, "Preset (ms)")

    definition = macros_module.get_definition(window.project, def_id)
    assert definition["parameter_bindings"] == []
    _close(window)

def test_instance_property_panel_shows_parameter_with_unit_tooltip(qsettings):
    """§C2.5: the PLACED INSTANCE's own property panel (top level, not
    inside the macro's own edit view) shows the parameter's value,
    tooltip-annotated with its unit/description."""
    _app()
    window, instance, ton = _make_window_with_ton_macro(qsettings)
    window.enter_macro_instance(instance)
    ton_inside = next(b for b in window.project.blocks if b.type_id == "timer.ton")
    def_id = window.current_macro_def_id
    from logic_studio.core import macros as macros_module
    name = macros_module.add_parameter(window.project, def_id, "Zwloka", "INT", 500, unit="ms", description="Czas opóźnienia")
    macros_module.add_parameter_binding(window.project, def_id, name, ton_inside.uuid, "Preset (ms)")
    window._resync_macro_instances(def_id)
    window._navigate_to_breadcrumb_index(0)  # back to top level

    top_instance = next(b for b in window.project.blocks if isinstance(b, MacroInstanceBlock))
    window.property_panel.load_block_properties(top_instance, window.project, None)
    editor = window.property_panel.field_widget("Zwloka")
    assert editor is not None
    assert "ms" in editor.toolTip()
    assert "opóźnienia" in editor.toolTip()
    _close(window)


# ---- UI: MacroPinsDialog "Parametry" tab (§C2.4) ------------------------

def test_macro_pins_dialog_lists_parameters_with_binding_counts(qsettings):
    _app()
    window, instance, ton = _make_window_with_ton_macro(qsettings)
    window.enter_macro_instance(instance)
    ton_inside = next(b for b in window.project.blocks if b.type_id == "timer.ton")
    def_id = window.current_macro_def_id
    from logic_studio.core import macros as macros_module
    name = macros_module.add_parameter(window.project, def_id, "Zwloka", "INT", 500, unit="ms")
    macros_module.add_parameter_binding(window.project, def_id, name, ton_inside.uuid, "Preset (ms)")

    from logic_studio.ui.macro_pins_dialog import MacroPinsDialog
    definition = macros_module.get_definition(window.project, def_id)
    dialog = MacroPinsDialog(definition, window._remove_macro_pin, parent=window, on_parameter_change=window._on_macro_parameter_change)

    assert dialog.param_table.rowCount() == 1
    assert dialog.param_table.item(0, 0).text() == "Zwloka"
    assert dialog.param_table.item(0, 1).text() == "INT"
    assert dialog.param_table.item(0, 4).text() == "1"  # Powiązań
    dialog.close()
    _close(window)

def test_macro_pins_dialog_add_parameter_dispatches_to_the_callback(qsettings):
    _app()
    window, instance, ton = _make_window_with_ton_macro(qsettings)
    window.enter_macro_instance(instance)
    def_id = window.current_macro_def_id

    from logic_studio.ui.macro_pins_dialog import MacroPinsDialog
    from logic_studio.core import macros as macros_module
    definition = macros_module.get_definition(window.project, def_id)
    dialog = MacroPinsDialog(definition, window._remove_macro_pin, parent=window, on_parameter_change=window._on_macro_parameter_change)

    fresh = window._on_macro_parameter_change("add", display_name="X", type="INT", default=1, unit="", description="")
    assert fresh is not None
    dialog.refresh(fresh)
    assert dialog.param_table.rowCount() == 1
    dialog.close()
    _close(window)

def test_macro_pins_dialog_remove_parameter_dispatches_to_the_callback(qsettings):
    _app()
    window, instance, ton = _make_window_with_ton_macro(qsettings)
    window.enter_macro_instance(instance)
    def_id = window.current_macro_def_id
    from logic_studio.core import macros as macros_module
    name = macros_module.add_parameter(window.project, def_id, "X", "INT", 1)

    fresh = window._on_macro_parameter_change("remove", param_name=name)
    assert fresh is not None
    assert fresh["parameters"] == []
    _close(window)

def test_macro_pins_dialog_reorder_dispatches_to_the_callback(qsettings):
    _app()
    window, instance, ton = _make_window_with_ton_macro(qsettings)
    window.enter_macro_instance(instance)
    def_id = window.current_macro_def_id
    from logic_studio.core import macros as macros_module
    a = macros_module.add_parameter(window.project, def_id, "A", "INT", 1)
    b = macros_module.add_parameter(window.project, def_id, "B", "INT", 2)

    fresh = window._on_macro_parameter_change("reorder", new_order=[b, a])
    assert fresh is not None
    assert [p["name"] for p in fresh["parameters"]] == [b, a]
    _close(window)

def test_type_reset_notice_reaches_the_status_bar(qsettings):
    """The placed instance (`instance`) is stashed in _macro_nav_stack's
    own ancestor entry while its macro is being edited — still reachable
    by resync_all_instances()'s own live_block_lists, which is exactly
    what makes an immediate (not deferred-to-compile) notice possible at
    all (core/macros.py's own resync_all_instances() docstring)."""
    _app()
    window, instance, ton = _make_window_with_ton_macro(qsettings)
    window.enter_macro_instance(instance)
    ton_inside = next(b for b in window.project.blocks if b.type_id == "timer.ton")
    def_id = window.current_macro_def_id
    from logic_studio.core import macros as macros_module
    name = macros_module.add_parameter(window.project, def_id, "Zwloka", "INT", 500)
    macros_module.add_parameter_binding(window.project, def_id, name, ton_inside.uuid, "Preset (ms)")
    window._resync_macro_instances(def_id)  # gives `instance` its own "Zwloka" property
    instance.update_property("Zwloka", "700")

    window._on_macro_parameter_change("update", param_name=name, fields={"type": "STRING", "default": "auto"})

    assert "Zwloka" in window.statusBar().currentMessage()
    _close(window)
