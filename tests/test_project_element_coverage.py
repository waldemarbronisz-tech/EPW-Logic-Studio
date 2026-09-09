"""fix/wire-labels-and-project-integrity §B2 — the project-ELEMENT-level
guardian this project never had. Every field-level guardian this
project already has (Pin/BaseLogicBlock's SERIALIZED_FIELDS, Wire's
own, state_diff's KNOWN_TOP_LEVEL_KEYS) only ever asks "does every
FIELD of one class survive this path" — none of them ever asked "does
every ELEMENT of the PROJECT ITSELF survive this path", which is
exactly the gap that let project.wires go unknown to core/macros.py
for as long as it did (§B1's own fix, the eighth instance of this
project's most recurring bug class).

PROJECT_ELEMENTS (core/project.py) names the three: blocks, wires,
settings. This file checks each of the seven paths §B2.2 names has a
documented, TESTED answer for what happens to each element — including
paths where the correct answer is "deliberately left alone" (settings,
during macro enter/exit and macro import/export), which is just as
important to pin down as "must survive" is.
"""
import pytest

from logic_studio.blocks import register_builtin_blocks
from logic_studio.blocks.registry import BlockRegistry
from logic_studio.core.project import Project, PROJECT_ELEMENTS
from logic_studio.core.wire import Wire
from logic_studio.core import macros as macros_module
from logic_studio.core import macro_library
from logic_studio.core.state_diff import KNOWN_TOP_LEVEL_KEYS, SCALAR_KEYS
from logic_studio.compiler.core import Compiler

register_builtin_blocks()


# ---- §B2.1: the declaration itself -----------------------------------------

def test_project_elements_is_derived_from_state_diffs_own_registries_not_hand_duplicated():
    assert set(PROJECT_ELEMENTS) == KNOWN_TOP_LEVEL_KEYS - set(SCALAR_KEYS)
    assert set(PROJECT_ELEMENTS) == {"blocks", "wires", "settings"}


# ---- Path 1: serialize()/deserialize() (save/load) -------------------------

def test_path_serialize_deserialize_covers_all_three_elements(tmp_path):
    p = Project()
    b = BlockRegistry.create_block("logic.and")
    p.add_block(b)
    wire = Wire()
    wire.source_pin = b.outputs[0].uuid
    wire.free_end_dest = {"x": 1.0, "y": 1.0}
    wire.label = "L"
    p.add_wire(wire)
    p.settings["name"] = "CustomName"

    path = str(tmp_path / "p.epwlogic")
    p.save_to_file(path)
    reloaded = Project.load_from_file(path)

    assert len(reloaded.blocks) == 1  # blocks
    assert len(reloaded.wires) == 1 and reloaded.wires[0].label == "L"  # wires
    assert reloaded.settings["name"] == "CustomName"  # settings


# ---- Path 2: state_diff (undo/redo) ----------------------------------------

def test_path_state_diff_covers_all_three_elements():
    """The exact subject of test_state_diff.py's own
    test_state_diff_round_trips_a_change_to_each_top_level_key,
    parametrized over KNOWN_TOP_LEVEL_KEYS -- referenced here, not
    duplicated (one test suite for this path, not two copies free to
    drift apart from each other)."""
    assert set(PROJECT_ELEMENTS) <= KNOWN_TOP_LEVEL_KEYS


# ---- Path 3: clipboard (copy/paste) ----------------------------------------

def test_path_clipboard_covers_blocks_and_wires(qsettings):
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from logic_studio.ui.main_window import MainWindow
    window = MainWindow(settings=qsettings)
    window.scene.clear()
    window.scene.add_block_from_library("logic.and", 0, 0)
    a = window.project.blocks[0]
    wire = Wire()
    wire.source_pin = a.outputs[0].uuid
    wire.free_end_dest = {"x": 1.0, "y": 1.0}
    wire.label = "Copied"
    window.project.add_wire(wire)

    for item in window.scene.items():
        if hasattr(item, "logic_block"):
            item.setSelected(True)
    assert window.scene.copy_selected_items()
    window.scene.paste_clipboard()  # no explicit return value on success

    assert len(window.project.blocks) == 2  # blocks: original + pasted
    assert len(window.project.wires) == 2  # wires: original + pasted copy
    window.is_dirty = False
    window.close()

def test_path_clipboard_never_touches_settings(qsettings):
    """Copy/paste operates on a SELECTION of blocks/wires -- it has no
    concept of "settings" at all (project.settings is never part of
    clipboard_data). Documented here as the deliberate, correct answer
    for this element on this path, not an oversight."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from logic_studio.ui.main_window import MainWindow
    window = MainWindow(settings=qsettings)
    window.scene.clear()
    window.project.settings["name"] = "Untouched"
    window.scene.add_block_from_library("logic.and", 0, 0)
    for item in window.scene.items():
        if hasattr(item, "logic_block"):
            item.setSelected(True)
    window.scene.copy_selected_items()
    assert "settings" not in window.scene.clipboard_data
    window.scene.paste_clipboard()
    assert window.project.settings["name"] == "Untouched"
    window.is_dirty = False
    window.close()


# ---- Path 4: macro expansion (compile-time) --------------------------------

def test_path_macro_expansion_covers_blocks_and_wires_settings_shared_not_swapped():
    """§B1.3's own coverage (tests/test_macro_wire_scoping.py) already
    proves blocks+wires are correctly expanded/scoped; the settings
    answer for THIS path is "shared, read-only, never swapped" — a
    macro instance's parameter substitution writes to internal block
    PROPERTIES, never to project.settings, which stays the single,
    unswapped registry expand_project() reads DeviceModel/system_signals
    lookups against throughout (core/macros.py's own module-level note).
    Confirmed here directly: settings identity is unchanged by
    expand_project()."""
    p = Project()
    p.settings["name"] = "Untouched"
    b = BlockRegistry.create_block("logic.and")
    p.add_block(b)

    settings_before = p.settings
    expanded_blocks, wire_scopes, errors = macros_module.expand_project(p)

    assert errors == []
    assert len(expanded_blocks) == 1
    assert p.settings is settings_before  # never swapped, never copied
    assert p.settings["name"] == "Untouched"


# ---- Path 5: macro enter/exit (breadcrumb navigation) ----------------------

def test_path_macro_enter_exit_swaps_blocks_and_wires_settings_stays_shared(qsettings):
    """§B1.2's own fix. blocks/wires: swapped in lockstep (tests/
    test_macro_wire_scoping.py). settings: the ONE element this path
    deliberately does NOT swap -- confirmed here directly, since an
    accidental future swap would silently break short_id counters/
    macro_definitions itself (shared registries that must stay visible
    regardless of nav depth, core/macros.py's own module-level note)."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from logic_studio.ui.main_window import MainWindow
    window = MainWindow(settings=qsettings)
    window.scene.clear()
    window.project.settings["name"] = "TopLevelProject"

    window.scene.add_block_from_library("logic.and", 0, 0)
    window.scene.add_block_from_library("logic.not", 200, 0)
    from logic_studio.ui.canvas.block_item import BlockItem
    for item in [i for i in window.scene.items() if isinstance(i, BlockItem)]:
        item.setSelected(True)
    window.scene.create_macro_from_selection("M")

    from logic_studio.blocks.macro_instance import MacroInstanceBlock
    instance = next(b for b in window.project.blocks if isinstance(b, MacroInstanceBlock))
    settings_object = window.project.settings

    window.enter_macro_instance(instance)
    assert window.project.settings is settings_object  # SAME object, never swapped
    assert window.project.settings["name"] == "TopLevelProject"

    window._navigate_to_breadcrumb_index(0)
    assert window.project.settings is settings_object
    window.is_dirty = False
    window.close()


# ---- Path 6: macro import/export (.epwmacro) -------------------------------

def test_path_macro_import_export_covers_blocks_and_wires():
    """§B1.4's own coverage (tests/test_macro_wire_scoping.py). A
    .epwmacro bundle has no "settings" concept at all -- it exports one
    self-contained macro DEFINITION (blocks + wires + boundary pins +
    parameters), never anything from project.settings (analog_points/
    internal_bits/io_labels are project-wide registries a standalone
    macro file can't carry along; a macro referencing one by name is
    the importing project's own responsibility to have defined).
    Confirmed here: the bundle shape has no "settings" key at all."""
    p = Project()
    b = BlockRegistry.create_block("logic.and")
    definition, _ = macros_module.build_definition("M", [b])
    def_id = macros_module.new_def_id()
    macros_module.set_definition(p, def_id, definition)

    bundle = macro_library.export_definition(p, def_id)
    assert "settings" not in bundle
    assert "settings" not in bundle["definitions"][def_id]


# ---- Path 7: schema migration chain ----------------------------------------

def test_path_schema_migration_covers_all_three_elements():
    """blocks/wires: test_wire_model.py's own
    test_v1_project_migrates_all_the_way_through_with_no_wires already
    proves the full v1->v13 chain produces both. settings: virtually
    EVERY migration in the chain (io_labels/analog_points/internal_bits/
    ela_devices/...) modifies something INSIDE settings directly --
    confirmed here with a real v1 fixture reaching the CURRENT version
    with all three elements present and well-formed."""
    data = {"format": "EPW_LOGIC", "schema_version": 1, "blocks": []}
    p = Project.deserialize(data)
    assert isinstance(p.blocks, list)
    assert isinstance(p.wires, list)
    assert isinstance(p.settings, dict) and "analog_points" in p.settings
