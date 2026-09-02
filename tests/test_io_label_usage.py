"""feat/io-labels-and-ids §3 — where io_labels actually get USED: the
canvas block's own second line, the signal picker's Opis column, and
compiler messages (the compiler-message half is covered by
test_short_id.py's _block_ref tests, since both features land together).
"""
import pytest
from PySide6.QtWidgets import QApplication

from logic_studio.blocks import register_builtin_blocks
from logic_studio.core.project import Project
from logic_studio.core.device_model import DeviceModel
from logic_studio.ui.canvas.block_item import BlockItem
from logic_studio.ui.canvas.scene import LogicScene


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


register_builtin_blocks()


def _di_item_in_scene(address, qsettings):
    """A BlockItem placed on a REAL MainWindow's real scene — needed
    because _io_label_for_display() reaches for self.scene().views()[0].
    window().project (same pattern as the pre-existing
    _lookup_analog_unit()), and PySide6's Python wrappers around a
    QGraphicsScene/View aren't guaranteed stable across repeated attribute
    access, so a hand-rolled fake scene/view/window doesn't reliably
    survive the round trip the way a real MainWindow does."""
    from logic_studio.ui.main_window import MainWindow
    from logic_studio.blocks.registry import BlockRegistry

    window = MainWindow(settings=qsettings)
    block = BlockRegistry.create_block("input.di")
    block.properties["Address"] = address
    window.project.add_block(block)
    item = BlockItem(block)
    window.scene.addItem(item)
    return item, block, window


def test_canvas_second_line_shows_io_label_when_no_comment(qsettings):
    _app()
    item, block, window = _di_item_in_scene("ELA01.DI01", qsettings)
    DeviceModel.set_io_label(window.project, "ELA01.DI01", "Wyłącznik Q1 zamknięty")

    assert item._io_label_for_display("ELA01.DI01") == "Wyłącznik Q1 zamknięty"
    window.close()

def test_canvas_second_line_prefers_comment_over_label(qsettings):
    """§3.1/§3.4: Comment describes THIS USAGE, the label describes the
    ADDRESS — Comment wins when both are set."""
    _app()
    item, block, window = _di_item_in_scene("ELA01.DI01", qsettings)
    DeviceModel.set_io_label(window.project, "ELA01.DI01", "Wyłącznik Q1 zamknięty")
    block.properties["Comment"] = "Blokada bramy wjazdowej"

    comment = block.properties.get("Comment", "")
    label = item._io_label_for_display("ELA01.DI01")
    second_line = comment or label or block.display_name
    assert second_line == "Blokada bramy wjazdowej"
    window.close()

def test_canvas_falls_back_to_display_name_when_neither_set(qsettings):
    _app()
    item, block, window = _di_item_in_scene("ELA01.DI02", qsettings)

    assert item._io_label_for_display("ELA01.DI02") == ""
    comment = block.properties.get("Comment", "")
    label = item._io_label_for_display("ELA01.DI02")
    second_line = comment or label or block.display_name
    assert second_line == block.display_name
    window.close()

def test_comment_suppressed_above_address_based_io_block_to_avoid_duplication(qsettings):
    """§3.1: Comment is now shown INSIDE an address-configured IO block
    (the second line) — showing it again above the block (the generic
    Tag/Comment annotation every other block type uses) would just
    duplicate it."""
    _app()
    item, block, window = _di_item_in_scene("ELA01.DI01", qsettings)
    block.properties["Comment"] = "Blokada bramy wjazdowej"

    tag, comment = item._effective_tag_and_comment()
    assert comment == ""
    window.close()

def test_comment_still_shown_above_virtual_io_block():
    """Virtual/internal-signal IO blocks use "Bit", not "Address" — the
    suppression above only applies to the Address-configured case."""
    _app()
    p = Project()
    from logic_studio.blocks.registry import BlockRegistry
    block = BlockRegistry.create_block("virtual.input")
    block.properties["Comment"] = "Some usage note"
    p.add_block(block)
    scene = LogicScene()
    item = BlockItem(block)
    scene.addItem(item)

    tag, comment = item._effective_tag_and_comment()
    assert comment == "Some usage note"


# ---- §3.2 signal picker -------------------------------------------------

def test_signal_picker_opis_column_shows_label_when_set():
    _app()
    from logic_studio.ui.signal_picker import SignalPickerDialog

    p = Project()
    DeviceModel.set_io_label(p, "ELA01.DI01", "Wyłącznik Q1 zamknięty")
    dialog = SignalPickerDialog(p, value_type="BOOL", sections=("physical",))

    found = _find_leaf_by_name(dialog.tree, "ELA01.DI01")
    assert found is not None
    assert found.text(0) == "Wyłącznik Q1 zamknięty"

def test_signal_picker_opis_column_falls_back_when_no_label():
    _app()
    from logic_studio.ui.signal_picker import SignalPickerDialog

    p = Project()
    dialog = SignalPickerDialog(p, value_type="BOOL", sections=("physical",))

    found = _find_leaf_by_name(dialog.tree, "ELA01.DI02")
    assert found is not None
    assert found.text(0) == "Wejście cyfrowe (ELA)"

def test_signal_picker_search_matches_label_text():
    _app()
    from logic_studio.ui.signal_picker import SignalPickerDialog

    p = Project()
    DeviceModel.set_io_label(p, "ELA01.DI01", "Wyłącznik Q1 zamknięty")
    dialog = SignalPickerDialog(p, value_type="BOOL", sections=("physical",))
    dialog._apply_filter("Wyłącznik Q1")

    found = _find_leaf_by_name(dialog.tree, "ELA01.DI01")
    assert found is not None
    assert not found.isHidden()

    other = _find_leaf_by_name(dialog.tree, "ELA01.DI02")
    assert other.isHidden()


def _find_leaf_by_name(tree, signal_name):
    from logic_studio.ui.signal_picker import SIGNAL_ID_ROLE

    def _walk(item):
        if item.data(0, SIGNAL_ID_ROLE) == signal_name:
            return item
        for i in range(item.childCount()):
            found = _walk(item.child(i))
            if found is not None:
                return found
        return None

    for i in range(tree.topLevelItemCount()):
        found = _walk(tree.topLevelItem(i))
        if found is not None:
            return found
    return None
