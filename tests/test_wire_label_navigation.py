"""fix/wire-labels-and-project-integrity §A4.5 — navigating between the
two (or more) ends of a labeled network node.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from logic_studio.blocks import register_builtin_blocks
from logic_studio.core.wire import Wire
from logic_studio.ui.canvas.wire_item import WireItem
from logic_studio.ui.canvas.navigation import find_pin_owner_item, jump_to_pin

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


def _free_wire_items(window):
    return [i for i in window.scene.items() if isinstance(i, WireItem) and i.fixed_free_end is not None]


def _two_labeled_stubs(window):
    window.scene.add_block_from_library("input.di", 0, 0)
    window.scene.add_block_from_library("output.do", 400, 0)
    di, do = window.project.blocks
    w1 = Wire()
    w1.source_pin = di.outputs[0].uuid
    w1.free_end_dest = {"x": 100.0, "y": 0.0}
    w1.label = "Cmd"
    window.project.add_wire(w1)
    w2 = Wire()
    w2.dest_pin = do.inputs[0].uuid
    w2.free_end_source = {"x": 300.0, "y": 0.0}
    w2.label = "Cmd"
    window.project.add_wire(w2)
    window.scene.clear()
    window._reconstruct_scene()
    return di, do


# ---- navigation.py helpers ---------------------------------------------

def test_find_pin_owner_item_locates_the_block(qsettings):
    _app()
    window = _make_window(qsettings)
    di, do = _two_labeled_stubs(window)

    item = find_pin_owner_item(window.scene, di.outputs[0].uuid)
    assert item.logic_block is di
    _close(window)

def test_jump_to_pin_selects_and_centers_on_the_owning_block(qsettings):
    _app()
    window = _make_window(qsettings)
    di, do = _two_labeled_stubs(window)
    view = window.scene.views()[0]

    result = jump_to_pin(window.scene, view, do.inputs[0].uuid)

    assert result.logic_block is do
    assert result.isSelected()
    _close(window)


# ---- WireItem.navigate_to_other_end() -----------------------------------

def test_double_click_a_labeled_free_end_jumps_to_the_single_other_end(qsettings):
    _app()
    window = _make_window(qsettings)
    di, do = _two_labeled_stubs(window)

    source_stub = next(w for w in _free_wire_items(window) if w.source_port.pin is di.outputs[0])
    source_stub.navigate_to_other_end()

    do_item = next(i for i in _block_items(window) if i.logic_block is do)
    assert do_item.isSelected()
    _close(window)

def test_multiple_receivers_are_all_found_as_other_ends(qsettings):
    """navigate_to_other_end() itself opens a REAL modal QMenu when
    there's more than one target (§A4.5's own "menu with list"
    requirement) — not driveable headless without blocking on a real
    event loop, so this exercises the underlying target-resolution
    logic (_other_end_pins()) directly instead, which is what decides
    WHETHER a menu is needed and what it would list."""
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("input.di", 0, 0)
    window.scene.add_block_from_library("output.do", 400, 0)
    window.scene.add_block_from_library("logic.buffer", 400, 200)
    di, do, buf = window.project.blocks
    w_src = Wire()
    w_src.source_pin = di.outputs[0].uuid
    w_src.free_end_dest = {"x": 100.0, "y": 0.0}
    w_src.label = "Fanout"
    window.project.add_wire(w_src)
    w_rx1 = Wire()
    w_rx1.dest_pin = do.inputs[0].uuid
    w_rx1.free_end_source = {"x": 300.0, "y": 0.0}
    w_rx1.label = "Fanout"
    window.project.add_wire(w_rx1)
    w_rx2 = Wire()
    w_rx2.dest_pin = buf.inputs[0].uuid
    w_rx2.free_end_source = {"x": 300.0, "y": 200.0}
    w_rx2.label = "Fanout"
    window.project.add_wire(w_rx2)
    window.scene.clear()
    window._reconstruct_scene()

    source_stub = next(w for w in _free_wire_items(window) if w.source_port.pin is di.outputs[0])
    targets = source_stub._other_end_pins()

    assert {p.uuid for p in targets} == {do.inputs[0].uuid, buf.inputs[0].uuid}
    _close(window)

def test_double_click_an_unlabeled_free_end_does_nothing(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("input.di", 0, 0)
    di = window.project.blocks[0]
    w = Wire()
    w.source_pin = di.outputs[0].uuid
    w.free_end_dest = {"x": 100.0, "y": 0.0}
    window.project.add_wire(w)
    window.scene.clear()
    window._reconstruct_scene()

    stub = _free_wire_items(window)[0]
    stub.navigate_to_other_end()  # must not raise, must not select anything

    assert not any(i.isSelected() for i in _block_items(window))
    _close(window)


# ---- Enter key on the scene ----------------------------------------------

def test_enter_key_on_a_selected_free_end_navigates(qsettings):
    _app()
    window = _make_window(qsettings)
    di, do = _two_labeled_stubs(window)

    source_stub = next(w for w in _free_wire_items(window) if w.source_port.pin is di.outputs[0])
    source_stub.setSelected(True)

    event = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Return, Qt.NoModifier)
    window.scene.keyPressEvent(event)

    do_item = next(i for i in _block_items(window) if i.logic_block is do)
    assert do_item.isSelected()
    _close(window)

def test_enter_key_with_no_wire_selected_falls_through_unchanged(qsettings):
    """Existing Enter behavior (there is none registered otherwise, but
    the fallthrough itself must not raise) stays undisturbed when
    nothing relevant is selected."""
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)

    event = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Return, Qt.NoModifier)
    window.scene.keyPressEvent(event)  # must not raise

    _close(window)
