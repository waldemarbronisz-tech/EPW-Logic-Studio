"""fix/wire-labels-and-project-integrity §B1 — a macro definition now
carries its own Wire list, scoped exactly like its own block list:
entering/leaving a macro's edit view swaps BOTH, a macro's own labels
never merge with the top level or another instance, and export/import
carries wires along with blocks.

This is the EIGHTH instance of "element added to the model, one path
never learned about" this project has now found -- and this file's own
existence is the direct fix for it, mirroring the SERIALIZED_FIELDS
field-audit convention one level up: at the level of PROJECT ELEMENTS
(blocks/wires/settings), not just fields within one of them.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from logic_studio.blocks import register_builtin_blocks
from logic_studio.blocks.registry import BlockRegistry
from logic_studio.core.project import Project
from logic_studio.core.wire import Wire
from logic_studio.core import macros as macros_module
from logic_studio.core import macro_library
from logic_studio.compiler.core import Compiler

register_builtin_blocks()


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _make_window(qsettings):
    from logic_studio.ui.main_window import MainWindow
    window = MainWindow(settings=qsettings)
    window.scene.clear()
    return window


def _close(window):
    window.is_dirty = False
    window.close()


def _block_items(window):
    from logic_studio.ui.canvas.block_item import BlockItem
    return [i for i in window.scene.items() if isinstance(i, BlockItem)]


# ---- B1.1: build_definition() captures internal wires, drops crossing ----

def test_build_definition_captures_a_wire_fully_inside_the_selection():
    a = BlockRegistry.create_block("logic.and")
    b = BlockRegistry.create_block("logic.not")
    wire = Wire()
    wire.source_pin = a.outputs[0].uuid
    wire.free_end_dest = {"x": 1.0, "y": 1.0}
    wire.label = "Internal"

    definition, _ = macros_module.build_definition("M", [a, b], wires=[wire])

    assert len(definition["wires"]) == 1
    assert definition["wires"][0]["label"] == "Internal"

def test_build_definition_drops_a_wire_touching_a_pin_outside_the_selection():
    a = BlockRegistry.create_block("logic.and")
    outside = BlockRegistry.create_block("logic.not")
    a.outputs[0].connect(outside.inputs[0])
    wire = Wire()
    wire.source_pin = a.outputs[0].uuid
    wire.dest_pin = outside.inputs[0].uuid
    wire.label = "Crossing"

    definition, _ = macros_module.build_definition("M", [a], wires=[wire])  # `outside` NOT selected

    assert definition["wires"] == []

def test_build_definition_with_no_wires_argument_defaults_to_empty():
    a = BlockRegistry.create_block("logic.and")
    definition, _ = macros_module.build_definition("M", [a])
    assert definition["wires"] == []


# ---- instantiate_definition_wires() / update_definition_wires() ----------

def test_instantiate_definition_wires_builds_live_wire_objects():
    definition = {"wires": [{
        "uuid": "w1", "source_pin": "p1", "dest_pin": None,
        "free_end_source": None, "free_end_dest": {"x": 1.0, "y": 2.0}, "label": "X",
    }]}
    wires = macros_module.instantiate_definition_wires(definition)
    assert len(wires) == 1
    assert isinstance(wires[0], Wire)
    assert wires[0].label == "X"
    assert wires[0].source_pin == "p1"

def test_instantiate_definition_wires_defaults_to_empty_for_a_pre_b1_definition():
    """A definition with no "wires" key at all (schema v12 or older,
    before the v12->v13 migration ever touched it in memory) must not
    raise -- same graceful-degrade the migration itself guarantees on
    disk, also true for a definition built in-process."""
    definition = {"blocks": []}
    assert macros_module.instantiate_definition_wires(definition) == []

def test_update_definition_wires_round_trips_through_get_definition():
    p = Project()
    def_id = macros_module.new_def_id()
    macros_module.set_definition(p, def_id, {"name": "M", "blocks": [], "wires": [],
                                              "input_pins": [], "output_pins": []})
    wire = Wire()
    wire.source_pin = "p1"
    wire.free_end_dest = {"x": 0.0, "y": 0.0}
    wire.label = "Persisted"

    ok = macros_module.update_definition_wires(p, def_id, [wire])
    assert ok is True

    reloaded = macros_module.get_definition(p, def_id)
    assert len(reloaded["wires"]) == 1
    assert reloaded["wires"][0]["label"] == "Persisted"

def test_update_definition_wires_is_a_no_op_for_a_deleted_definition():
    p = Project()
    assert macros_module.update_definition_wires(p, "does-not-exist", []) is False


# ---- Regression: _copy_definition() must not silently drop "wires" -------

def test_copy_definition_preserves_wires_across_a_get_set_round_trip():
    """The EIGHTH occurrence of this project's own recurring bug class,
    found while manually verifying this exact PR: _copy_definition() is
    ITS OWN hand-enumerated whitelist of keys, and "wires" was briefly
    missing from it -- every write silently vanished on the very next
    get_definition()/set_definition() round trip. This is the permanent
    regression test for that."""
    p = Project()
    def_id = macros_module.new_def_id()
    macros_module.set_definition(p, def_id, {
        "name": "M", "blocks": [], "wires": [{"uuid": "w1", "label": "Survives"}],
        "input_pins": [], "output_pins": [],
    })
    reloaded = macros_module.get_definition(p, def_id)
    assert reloaded["wires"] == [{"uuid": "w1", "label": "Survives"}]

    # get_definitions() (plural, the whole-registry copy) uses the same
    # _copy_definition() internally -- covered separately since a fix
    # scoped to only ONE of the two callers would be exactly the kind of
    # "half-fixed" gap this project's own history warns about.
    all_defs = macros_module.get_definitions(p)
    assert all_defs[def_id]["wires"] == [{"uuid": "w1", "label": "Survives"}]


# ---- B1.2: entering/leaving a macro swaps project.wires too --------------

def test_entering_a_macro_swaps_to_its_own_wires_and_leaving_restores_the_top_level(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.or", 0, 0)
    window.scene.add_block_from_library("logic.buffer", 200, 0)
    outside_a, outside_b = window.project.blocks
    outside_a.outputs[0].connect(outside_b.inputs[0])
    top_level_wire = Wire()
    top_level_wire.source_pin = outside_a.outputs[0].uuid
    top_level_wire.dest_pin = outside_b.inputs[0].uuid
    top_level_wire.label = "TopLevel"
    window.project.add_wire(top_level_wire)

    window.scene.add_block_from_library("logic.and", 400, 0)
    window.scene.add_block_from_library("logic.not", 600, 0)
    items = {i.logic_block.type_id: i for i in _block_items(window)}
    items["logic.and"].setSelected(True)
    items["logic.not"].setSelected(True)
    window.scene.create_macro_from_selection("M")

    from logic_studio.blocks.macro_instance import MacroInstanceBlock
    instance = next(b for b in window.project.blocks if isinstance(b, MacroInstanceBlock))

    window.enter_macro_instance(instance)
    assert window.project.wires == []  # nothing captured, extraction had no internal wire

    inner_and = next(b for b in window.project.blocks if b.type_id == "logic.and")
    inner_wire = Wire()
    inner_wire.source_pin = inner_and.outputs[0].uuid
    inner_wire.free_end_dest = {"x": 5.0, "y": 5.0}
    inner_wire.label = "Inner"
    window.project.add_wire(inner_wire)

    window._navigate_to_breadcrumb_index(0)
    assert [w.label for w in window.project.wires] == ["TopLevel"]  # restored, undisturbed

    window.enter_macro_instance(instance)
    assert [w.label for w in window.project.wires] == ["Inner"]  # persisted across the round trip
    window._navigate_to_breadcrumb_index(0)
    _close(window)

def test_check_wire_pin_consistency_has_no_false_positive_while_editing_a_macro(qsettings):
    """§B2.4: the exact scenario the systematic-sweep audit found."""
    from logic_studio.core.wire import check_wire_pin_consistency

    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.or", 0, 0)
    window.scene.add_block_from_library("logic.buffer", 200, 0)
    outside_a, outside_b = window.project.blocks
    outside_a.outputs[0].connect(outside_b.inputs[0])
    wire = Wire()
    wire.source_pin = outside_a.outputs[0].uuid
    wire.dest_pin = outside_b.inputs[0].uuid
    wire.label = "TopLevel"
    window.project.add_wire(wire)

    window.scene.add_block_from_library("logic.and", 400, 0)
    window.scene.add_block_from_library("logic.not", 600, 0)
    items = {i.logic_block.type_id: i for i in _block_items(window)}
    items["logic.and"].setSelected(True)
    items["logic.not"].setSelected(True)
    window.scene.create_macro_from_selection("M")

    from logic_studio.blocks.macro_instance import MacroInstanceBlock
    instance = next(b for b in window.project.blocks if isinstance(b, MacroInstanceBlock))
    window.enter_macro_instance(instance)

    assert check_wire_pin_consistency(window.project) == []
    window._navigate_to_breadcrumb_index(0)
    assert check_wire_pin_consistency(window.project) == []
    _close(window)


# ---- B1.3: label scope ends at the macro boundary -------------------------

def test_macro_internal_label_does_not_merge_with_a_same_named_top_level_label():
    """A "Cmd" INSIDE a macro definition and a "Cmd" at the top level
    are two DIFFERENT nodes. The real, meaningful signal here: BOTH
    top_di (top level) and macro_di (inside the macro) are OUTPUT-
    direction sources claiming the label "Cmd" -- if the two scopes
    were flattened together (the bug this test guards against), that's
    a "two sources for one label" conflict compiler/label_merge.py
    would correctly reject as an ERROR. If scoping actually works,
    neither one ever sees the other, and compilation succeeds cleanly."""
    p = Project()
    top_di = BlockRegistry.create_block("input.di")
    top_di.properties["Address"] = "ELA01.DI01"
    p.add_block(top_di)
    top_wire_out = Wire()
    top_wire_out.source_pin = top_di.outputs[0].uuid
    top_wire_out.free_end_dest = {"x": 0.0, "y": 0.0}
    top_wire_out.label = "Cmd"
    p.add_wire(top_wire_out)

    macro_di = BlockRegistry.create_block("input.di")
    macro_di.properties["Address"] = "ELA01.DI02"
    macro_not = BlockRegistry.create_block("logic.not")
    macro_wire_out = Wire()
    macro_wire_out.source_pin = macro_di.outputs[0].uuid
    macro_wire_out.free_end_dest = {"x": 0.0, "y": 0.0}
    macro_wire_out.label = "Cmd"  # SAME name, inside the macro
    definition, _ = macros_module.build_definition("M", [macro_di, macro_not], wires=[macro_wire_out])
    def_id = macros_module.new_def_id()
    macros_module.set_definition(p, def_id, definition)

    from logic_studio.blocks.macro_instance import MacroInstanceBlock
    instance = MacroInstanceBlock(def_id=def_id)
    instance.configure(macros_module.get_definition(p, def_id))
    p.add_block(instance)

    c = Compiler(p)
    res = c.compile()
    assert res is not None, c.errors
    assert not any("więcej niż jedno źródło" in e for e in c.errors)

def test_two_instances_of_the_same_macro_do_not_share_their_internal_label():
    """Two PLACED instances of the identical macro definition, each
    with its own internal "Cmd" -> receiver wiring -- instance A's
    internal source must never satisfy instance B's internal receiver,
    or vice versa, even though both come from the literal same
    definition dict."""
    p = Project()
    macro_di = BlockRegistry.create_block("input.di")
    macro_di.properties["Address"] = "ELA01.DI01"
    macro_do_stub = BlockRegistry.create_block("logic.buffer")
    src_wire = Wire()
    src_wire.source_pin = macro_di.outputs[0].uuid
    src_wire.free_end_dest = {"x": 0.0, "y": 0.0}
    src_wire.label = "Shared"
    rx_wire = Wire()
    rx_wire.dest_pin = macro_do_stub.inputs[0].uuid
    rx_wire.free_end_source = {"x": 0.0, "y": 0.0}
    rx_wire.label = "Shared"
    definition, _ = macros_module.build_definition("M", [macro_di, macro_do_stub], wires=[src_wire, rx_wire])
    def_id = macros_module.new_def_id()
    macros_module.set_definition(p, def_id, definition)

    from logic_studio.blocks.macro_instance import MacroInstanceBlock
    instance_a = MacroInstanceBlock(def_id=def_id)
    instance_a.configure(macros_module.get_definition(p, def_id))
    instance_b = MacroInstanceBlock(def_id=def_id)
    instance_b.configure(macros_module.get_definition(p, def_id))
    p.add_block(instance_a)
    p.add_block(instance_b)

    c = Compiler(p)
    res = c.compile()
    assert res is not None, c.errors
    assert c.errors == []
    assert c.warnings == []  # each instance's own "Shared" fully resolves inside itself


# ---- B1.4: export/import carries wires ------------------------------------

def test_export_import_bundle_carries_macro_internal_wires():
    p = Project()
    a = BlockRegistry.create_block("logic.and")
    b = BlockRegistry.create_block("logic.not")
    wire = Wire()
    wire.source_pin = a.outputs[0].uuid
    wire.free_end_dest = {"x": 1.0, "y": 1.0}
    wire.label = "Carried"
    definition, _ = macros_module.build_definition("M", [a, b], wires=[wire])
    def_id = macros_module.new_def_id()
    macros_module.set_definition(p, def_id, definition)

    bundle = macro_library.export_definition(p, def_id)
    assert bundle["definitions"][def_id]["wires"][0]["label"] == "Carried"

    target = Project()
    new_id = macro_library.import_bundle(target, bundle)
    imported = macros_module.get_definition(target, new_id)
    assert imported["wires"][0]["label"] == "Carried"


# ---- Schema migration v12 -> v13 ------------------------------------------

def test_v12_project_migrates_macro_definitions_with_an_empty_wires_list():
    data = {
        "format": "EPW_LOGIC", "schema_version": 12, "blocks": [], "wires": [],
        "settings": {"macro_definitions": {"m1": {"name": "M", "blocks": [], "input_pins": [], "output_pins": []}}},
    }
    p = Project.deserialize(data)
    definition = macros_module.get_definition(p, "m1")
    assert definition["wires"] == []
