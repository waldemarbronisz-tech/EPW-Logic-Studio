"""fix/wire-labels-and-project-integrity §A4 — WireItem's label/marker
rendering and MainWindow._reconstruct_scene()'s wiring of it.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from logic_studio.blocks import register_builtin_blocks
from logic_studio.core.wire import Wire
from logic_studio.ui.canvas.wire_item import WireItem

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


def _wire_items(window):
    return [i for i in window.scene.items() if isinstance(i, WireItem)]


# ---- _reconstruct_scene() wiring -------------------------------------------

def test_free_end_wire_gets_its_own_wire_item(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    a = window.project.blocks[0]
    wire = Wire()
    wire.source_pin = a.outputs[0].uuid
    wire.free_end_dest = {"x": 100.0, "y": 20.0}
    wire.label = "Odnośnik"
    window.project.add_wire(wire)

    window.scene.clear()
    window._reconstruct_scene()

    free_items = [w for w in _wire_items(window) if w.fixed_free_end is not None]
    assert len(free_items) == 1
    assert free_items[0].wire is wire
    assert free_items[0].fixed_free_end.x() == 100.0
    assert free_items[0].fixed_free_end.y() == 20.0
    _close(window)

def test_dangling_free_end_reference_is_skipped_not_crashed(qsettings):
    """A Wire naming a pin uuid that no longer exists (found by neither
    add nor remove happening through the normal paths) must not crash
    scene reconstruction -- it's simply not drawable."""
    _app()
    window = _make_window(qsettings)
    wire = Wire()
    wire.source_pin = "does-not-exist"
    wire.free_end_dest = {"x": 0.0, "y": 0.0}
    window.project.wires.append(wire)  # bypass add_wire's own bookkeeping deliberately

    window.scene.clear()
    window._reconstruct_scene()  # must not raise

    assert _wire_items(window) == []
    _close(window)

def test_fully_connected_labeled_wire_attaches_to_the_existing_wire_item(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    window.scene.add_block_from_library("logic.not", 200, 0)
    a, n = window.project.blocks
    a.outputs[0].connect(n.inputs[0])
    wire = Wire()
    wire.source_pin = a.outputs[0].uuid
    wire.dest_pin = n.inputs[0].uuid
    wire.label = "Dokumentacja"
    window.project.add_wire(wire)

    window.scene.clear()
    window._reconstruct_scene()

    items = [w for w in _wire_items(window) if w.wire is wire]
    assert len(items) == 1
    assert items[0].fixed_free_end is None
    assert items[0].dest_port is not None
    _close(window)

def test_plain_unlabeled_wire_gets_no_wire_record_reference(qsettings):
    """The overwhelming common case -- core/wire.py's own design
    principle -- gets a WireItem with wire=None, no label drawn."""
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    window.scene.add_block_from_library("logic.not", 200, 0)
    a, n = window.project.blocks
    a.outputs[0].connect(n.inputs[0])

    window.scene.clear()
    window._reconstruct_scene()

    items = _wire_items(window)
    assert len(items) == 1
    assert items[0].wire is None
    _close(window)

def test_label_error_state_is_reflected_in_label_info(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    a = window.project.blocks[0]
    wire = Wire()
    wire.dest_pin = a.inputs[0].uuid  # a RECEIVER stub with no source anywhere
    wire.free_end_source = {"x": 0.0, "y": 0.0}
    wire.label = "Orphan"
    window.project.add_wire(wire)

    window.scene.clear()
    window._reconstruct_scene()

    free_items = [w for w in _wire_items(window) if w.fixed_free_end is not None]
    assert len(free_items) == 1
    assert free_items[0].label_info["has_error"] is True
    _close(window)


# ---- A4.6: geometric non-overlap -------------------------------------------

def test_label_symbol_does_not_overlap_its_own_block(qsettings):
    """The rectangle boundingRect() reports (used by Qt itself for
    repaint/hit-testing) must not swallow the block it's attached to --
    checked on RECTANGLES, not pixels, per §A4.6's own instruction."""
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    a = window.project.blocks[0]
    wire = Wire()
    wire.source_pin = a.outputs[0].uuid
    wire.free_end_dest = {"x": 300.0, "y": 0.0}
    wire.label = "FarAway"
    window.project.add_wire(wire)

    window.scene.clear()
    window._reconstruct_scene()

    block_item = _block_items(window)[0]
    free_item = next(w for w in _wire_items(window) if w.fixed_free_end is not None)
    geometry = free_item.label_geometry()
    assert geometry is not None
    block_rect = block_item.sceneBoundingRect()
    assert not geometry["text_rect"].intersects(block_rect), (geometry["text_rect"], block_rect)
    _close(window)

def test_two_free_end_labels_on_the_same_block_do_not_overlap_each_other(qsettings):
    """Two separate stubs leaving the SAME block, close together, must
    not have their own label text rectangles collide with each other —
    checked on rectangles (§A4.6), by giving them enough vertical/
    horizontal separation via distinct free-end positions."""
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and3", 0, 0)
    a = window.project.blocks[0]
    w1 = Wire()
    w1.source_pin = a.outputs[0].uuid
    w1.free_end_dest = {"x": 200.0, "y": -60.0}
    w1.label = "First"
    window.project.add_wire(w1)
    w2 = Wire()
    w2.dest_pin = a.inputs[0].uuid
    w2.free_end_source = {"x": -200.0, "y": 60.0}
    w2.label = "Second"
    window.project.add_wire(w2)

    window.scene.clear()
    window._reconstruct_scene()

    free_items = [w for w in _wire_items(window) if w.fixed_free_end is not None]
    assert len(free_items) == 2
    rect_a = free_items[0].label_geometry()["text_rect"]
    rect_b = free_items[1].label_geometry()["text_rect"]
    assert not rect_a.intersects(rect_b), (rect_a, rect_b)
    _close(window)
