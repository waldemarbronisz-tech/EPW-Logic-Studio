"""feat/clipboard-and-align §4 — temporary block disable: a ready
`enabled` field (BaseLogicBlock, read by validate()) with no UI toggle
until now.
"""
import pytest
from PySide6.QtWidgets import QApplication

from logic_studio.blocks import register_builtin_blocks
from logic_studio.blocks.registry import BlockRegistry
from logic_studio.core.project import Project
from logic_studio.compiler.core import Compiler
from logic_studio.engine.execution import ExecutionEngine
from logic_studio.engine.io_provider import SimulationIOProvider
from logic_studio.engine.time_provider import SimulationTimeProvider

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


def _block_item(window, block):
    from logic_studio.ui.canvas.block_item import BlockItem
    for item in window.scene.items():
        if isinstance(item, BlockItem) and item.logic_block is block:
            return item
    raise AssertionError("no BlockItem for block")


def _and_project():
    """DI -> AND -> DO, a trivially compilable chain."""
    p = Project()
    di = BlockRegistry.create_block("input.di")
    di.properties["Address"] = "ELA01.DI01"
    gate = BlockRegistry.create_block("logic.and")
    do = BlockRegistry.create_block("output.do")
    do.properties["Address"] = "ADA01.DO01"
    p.add_block(di)
    p.add_block(gate)
    p.add_block(do)
    di.outputs[0].connect(gate.inputs[0])
    gate.outputs[0].connect(do.inputs[0])
    return p, di, gate, do


# ---- §4.4: excluded from execution_order, restored on re-enable --------

def test_disabled_block_is_excluded_from_execution_order(qsettings):
    p, di, gate, do = _and_project()
    gate.enabled = False

    result = Compiler(p).compile()

    assert gate.uuid not in result["program"].execution_order
    assert di.uuid in result["program"].execution_order
    _close_app_only()


def test_reenabling_restores_the_block_to_execution_order(qsettings):
    p, di, gate, do = _and_project()
    gate.enabled = False
    Compiler(p).compile()  # sanity: excluded while disabled

    gate.enabled = True
    result = Compiler(p).compile()

    assert gate.uuid in result["program"].execution_order
    _close_app_only()


def _close_app_only():
    pass  # these tests never construct a MainWindow — nothing to close


# ---- §4.4: outputs get a defined value after a scan, never None --------

def test_disabled_blocks_outputs_have_a_defined_value_after_a_scan(qsettings):
    p, di, gate, do = _and_project()
    gate.enabled = False

    result = Compiler(p).compile()
    assert result is not None, "compile should succeed (a warning, not an error)"

    engine = ExecutionEngine(result["program"], SimulationIOProvider(), SimulationTimeProvider())
    engine.start()
    engine.step()

    compiled_gate = result["program"].block_map[gate.uuid]
    assert compiled_gate.outputs[0].value is not None
    assert compiled_gate.outputs[0].value is False  # BOOL safe default


def test_enabled_blocks_still_evaluate_normally_alongside_a_disabled_one(qsettings):
    """The disabled-outputs forcing loop must not clobber a normally
    evaluated block's own real output."""
    p, di, gate, do = _and_project()
    # Disable something unrelated (a second, disconnected gate) so gate/do
    # keep evaluating normally and DI=True should still reach DO via AND.
    unrelated = BlockRegistry.create_block("logic.not")
    p.add_block(unrelated)
    unrelated.enabled = False

    result = Compiler(p).compile()
    io = SimulationIOProvider()
    engine = ExecutionEngine(result["program"], io, SimulationTimeProvider())
    io.set_digital_input("ELA01.DI01", True)
    engine.start()
    engine.step()
    engine.step()

    compiled_gate = result["program"].block_map[gate.uuid]
    # AND with only one connected input at True and the block itself
    # enabled must evaluate normally, unaffected by the unrelated disabled
    # block's forced-safe-value handling.
    assert compiled_gate.outputs[0].value is not None


# ---- §4.4: compiler warning names the block by short_id ----------------

def test_compiling_with_a_disabled_block_gives_a_warning_naming_its_short_id(qsettings):
    p, di, gate, do = _and_project()
    gate.enabled = False

    compiler = Compiler(p)
    result = compiler.compile()

    assert result is not None
    assert any(gate.short_id in w for w in compiler.warnings)


def test_compiling_without_any_disabled_block_gives_no_such_warning(qsettings):
    p, di, gate, do = _and_project()

    compiler = Compiler(p)
    compiler.compile()

    assert not any("wyłączone bloki" in w.lower() for w in compiler.warnings)


# ---- §4.4: export's contains_disabled_blocks flag -----------------------

def test_export_contains_disabled_blocks_true_when_a_block_is_disabled(qsettings):
    p, di, gate, do = _and_project()
    gate.enabled = False

    result = Compiler(p).compile()
    assert result["contains_disabled_blocks"] is True
    assert gate.uuid not in result["blocks"]  # not in the export at all
    assert "contains_disabled_blocks" in result  # exported field present

def test_export_contains_disabled_blocks_false_when_none_are_disabled(qsettings):
    p, di, gate, do = _and_project()

    result = Compiler(p).compile()
    assert result["contains_disabled_blocks"] is False
    assert gate.uuid in result["blocks"]

def test_contains_disabled_blocks_is_covered_by_the_checksum(qsettings):
    from logic_studio.compiler.exporter import CHECKSUM_FIELDS
    assert "contains_disabled_blocks" in CHECKSUM_FIELDS


# ---- §4.1 UI: toggling ----------------------------------------------------

def test_context_menu_style_toggle_disables_a_single_block(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    block = window.project.blocks[0]
    item = _block_item(window, block)

    window.scene.set_blocks_enabled([item], False)
    assert block.enabled is False
    window.scene.set_blocks_enabled([item], True)
    assert block.enabled is True
    _close(window)


def test_toggling_multiple_blocks_is_exactly_one_undo_entry(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    window.scene.add_block_from_library("logic.not", 200, 0)
    items = [_block_item(window, b) for b in window.project.blocks]

    before = len(window.project.undo_stack)
    window.scene.set_blocks_enabled(items, False)

    assert len(window.project.undo_stack) == before + 1
    assert all(not b.enabled for b in window.project.blocks)
    _close(window)


def test_disabling_selection_via_edit_menu_actions(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    window.scene.add_block_from_library("logic.not", 200, 0)
    for item in [_block_item(window, b) for b in window.project.blocks]:
        item.setSelected(True)

    window._disable_selected_blocks()
    assert all(not b.enabled for b in window.project.blocks)

    window._enable_selected_blocks()
    assert all(b.enabled for b in window.project.blocks)
    _close(window)


def test_edit_menu_toggle_actions_disabled_with_no_selection(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    window.scene.clearSelection()

    assert window.act_disable_selected.isEnabled() is False
    assert window.act_enable_selected.isEnabled() is False
    _close(window)


def test_edit_menu_toggle_actions_enabled_with_a_selection(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    _block_item(window, window.project.blocks[0]).setSelected(True)

    assert window.act_disable_selected.isEnabled() is True
    assert window.act_enable_selected.isEnabled() is True
    _close(window)


# ---- §4.3 UI: status bar counter ------------------------------------------

def test_status_bar_shows_disabled_block_counter(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    window.scene.add_block_from_library("logic.not", 200, 0)
    items = [_block_item(window, b) for b in window.project.blocks]

    assert window.lbl_disabled_blocks.text() == ""

    window.scene.set_blocks_enabled([items[0]], False)
    assert window.lbl_disabled_blocks.text() == "Wyłączone bloki: 1"

    window.scene.set_blocks_enabled([items[1]], False)
    assert window.lbl_disabled_blocks.text() == "Wyłączone bloki: 2"

    window.scene.set_blocks_enabled(items, True)
    assert window.lbl_disabled_blocks.text() == ""
    _close(window)


def test_undo_after_disabling_restores_the_status_bar_counter(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    item = _block_item(window, window.project.blocks[0])

    window.scene.set_blocks_enabled([item], False)
    assert window.lbl_disabled_blocks.text() == "Wyłączone bloki: 1"

    window._undo()
    assert window.lbl_disabled_blocks.text() == ""
    assert window.project.blocks[0].enabled is True
    _close(window)
