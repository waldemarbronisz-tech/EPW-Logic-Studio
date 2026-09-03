"""feat/signal-crossref §4 — the block context menu's "Pokaż użycia
sygnału" action. contextMenuEvent() itself calls QMenu.exec() (modal —
would block forever in a headless test), so these tests exercise the two
new methods it's built from directly: _current_signal_reference() (which
also determines the menu item's enabled state — `setEnabled(bool(ref))`)
and _show_signal_usage() (the action's actual effect).
"""
import pytest
from PySide6.QtWidgets import QApplication

from logic_studio.blocks import register_builtin_blocks
from logic_studio.core.project import Project
from logic_studio.core.device_model import DeviceModel
from logic_studio.ui.canvas.block_item import BlockItem

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


# ---- _current_signal_reference() -----------------------------------------

def test_address_based_block_reference_is_the_address():
    _app()
    from logic_studio.blocks.registry import BlockRegistry
    block = BlockRegistry.create_block("input.di")
    block.properties["Address"] = "ELA01.DI01"
    item = BlockItem(block)
    assert item._current_signal_reference() == "ELA01.DI01"

def test_gate_has_no_signal_reference():
    _app()
    from logic_studio.blocks.registry import BlockRegistry
    block = BlockRegistry.create_block("logic.and")
    item = BlockItem(block)
    assert item._current_signal_reference() == ""

def test_di_with_empty_address_has_no_reference():
    _app()
    from logic_studio.blocks.registry import BlockRegistry
    block = BlockRegistry.create_block("input.di")
    block.properties["Address"] = ""
    item = BlockItem(block)
    assert item._current_signal_reference() == ""

def test_system_signal_block_reference_is_the_raw_sygnal_value(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("system.signal", 0, 0)
    block = window.project.blocks[0]
    from logic_studio.core import system_signals
    any_signal = system_signals.get_all_signals()[0]
    block.properties["Sygnał"] = any_signal["id"]

    from logic_studio.ui.canvas.block_item import BlockItem as BI
    item = next(i for i in window.scene.items() if isinstance(i, BI))
    assert item._current_signal_reference() == any_signal["id"]
    _close(window)

def test_virtual_input_reference_resolves_to_prefixed_id(qsettings):
    """Bit resolves through the SAME DeviceModel.get_internal_bit()/
    internal_bit_id() lookup core/crossref.py's own _resolve_bit() uses —
    "X" becomes "M.X", matching whatever row the signals panel shows."""
    _app()
    window = _make_window(qsettings)
    window.project.settings["internal_bits"] = [{"name": "X", "type": "BOOL", "retentive": False}]
    window.scene.add_block_from_library("virtual.input", 0, 0)
    window.project.blocks[0].properties["Bit"] = "X"

    from logic_studio.ui.canvas.block_item import BlockItem as BI
    item = next(i for i in window.scene.items() if isinstance(i, BI))
    assert item._current_signal_reference() == "M.X"
    _close(window)

def test_virtual_input_reference_falls_back_to_raw_name_when_undefined(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("virtual.input", 0, 0)
    window.project.blocks[0].properties["Bit"] = "GHOST"

    from logic_studio.ui.canvas.block_item import BlockItem as BI
    item = next(i for i in window.scene.items() if isinstance(i, BI))
    assert item._current_signal_reference() == "GHOST"
    _close(window)


# ---- _show_signal_usage() -------------------------------------------------

def test_show_signal_usage_switches_to_signals_tab_and_focuses_row(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("input.di", 0, 0)
    window.project.blocks[0].properties["Address"] = "ELA01.DI01"
    window.signals_panel.set_project(window.project)

    from logic_studio.ui.canvas.block_item import BlockItem as BI
    item = next(i for i in window.scene.items() if isinstance(i, BI))
    item._show_signal_usage(item._current_signal_reference())

    assert window.left_tabs.currentWidget() is window.signals_panel
    assert window.signals_panel.search_edit.text() == "ELA01.DI01"
    _close(window)

def test_show_signal_usage_with_empty_signal_id_does_nothing(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    from logic_studio.ui.canvas.block_item import BlockItem as BI
    item = next(i for i in window.scene.items() if isinstance(i, BI))

    before_tab = window.left_tabs.currentWidget()
    item._show_signal_usage("")
    assert window.left_tabs.currentWidget() is before_tab
    _close(window)

def test_focus_signal_resets_stale_filters_so_the_row_stays_visible(qsettings):
    """§4's whole point ("gdzie jeszcze jest używany X") fails silently if
    an old "Tylko problemy"/kind filter hides the very row it's supposed
    to reveal."""
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("input.di", 0, 0)
    window.project.blocks[0].properties["Address"] = "ELA01.DI01"
    window.signals_panel.set_project(window.project)
    window.signals_panel.only_issues_check.setChecked(True)  # this DI has no issue -> would hide it
    window.signals_panel.kind_filter_checks["Systemowe"].setChecked(True)  # wrong kind too

    from logic_studio.ui.canvas.block_item import BlockItem as BI
    item = next(i for i in window.scene.items() if isinstance(i, BI))
    item._show_signal_usage(item._current_signal_reference())

    row = next(
        r for r in range(window.signals_panel.table.rowCount())
        if window.signals_panel.table.item(r, 1).text() == "ELA01.DI01"
    )
    assert window.signals_panel.table.isRowHidden(row) is False
    _close(window)
