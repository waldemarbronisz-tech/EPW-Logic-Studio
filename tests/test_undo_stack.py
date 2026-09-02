"""feat/clipboard-and-align §3 — undo stack no longer floods on mouse
release, and the state it pushes actually reverts what happened (not a
post-mutation snapshot that makes undo() a no-op).
"""
import pytest
from PySide6.QtWidgets import QApplication, QGraphicsSceneMouseEvent
from PySide6.QtCore import Qt, QPointF

from logic_studio.blocks import register_builtin_blocks

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


def _press(scene, pos):
    ev = QGraphicsSceneMouseEvent(QGraphicsSceneMouseEvent.GraphicsSceneMousePress)
    ev.setScenePos(pos)
    ev.setButton(Qt.LeftButton)
    ev.setButtons(Qt.LeftButton)
    scene.mousePressEvent(ev)


def _release(scene, pos):
    ev = QGraphicsSceneMouseEvent(QGraphicsSceneMouseEvent.GraphicsSceneMouseRelease)
    ev.setScenePos(pos)
    ev.setButton(Qt.LeftButton)
    ev.setButtons(Qt.NoButton)
    scene.mouseReleaseEvent(ev)


# ---- §3.4 required test: click-without-moving must not grow the stack ---

def test_press_and_release_without_moving_does_not_grow_undo_stack(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    item = _block_item(window, window.project.blocks[0])
    item.setSelected(True)

    before = len(window.project.undo_stack)
    _press(window.scene, QPointF(10, 10))
    _release(window.scene, QPointF(10, 10))  # no movement in between

    assert len(window.project.undo_stack) == before
    _close(window)


def test_moving_a_block_by_one_grid_cell_grows_undo_stack_by_one(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    block = window.project.blocks[0]
    item = _block_item(window, block)
    item.setSelected(True)

    before = len(window.project.undo_stack)
    _press(window.scene, QPointF(10, 10))
    item.setPos(item.pos().x() + window.scene.grid_size, item.pos().y())  # simulate the drag itself
    _release(window.scene, QPointF(20, 10))

    assert len(window.project.undo_stack) == before + 1
    _close(window)


def test_repeated_no_move_clicks_never_grow_the_stack(qsettings):
    """A burst of plain clicks on an already-selected block — the exact
    scenario the original unconditional push_state() flooded on."""
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    item = _block_item(window, window.project.blocks[0])
    item.setSelected(True)

    before = len(window.project.undo_stack)
    for _ in range(10):
        _press(window.scene, QPointF(10, 10))
        _release(window.scene, QPointF(10, 10))

    assert len(window.project.undo_stack) == before
    _close(window)


# ---- undo after a real move actually restores the pre-move position -----

def test_undo_after_a_drag_restores_the_original_position(qsettings):
    """§3.2 audit finding: push_state() used to be called AFTER the drag
    had already been applied live (BlockItem.itemChange()), so it pushed
    the POST-move state and undo() was a no-op. mousePressEvent now
    snapshots the project BEFORE the drag and that snapshot — not a fresh
    serialize() at release time — is what gets pushed."""
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    block = window.project.blocks[0]
    item = _block_item(window, block)
    item.setSelected(True)

    _press(window.scene, QPointF(10, 10))
    item.setPos(100, 100)
    _release(window.scene, QPointF(100, 100))

    assert block.x == 100 and block.y == 100
    window._undo()
    restored = window.project.blocks[0]
    assert restored.x == 0 and restored.y == 0
    _close(window)


# ---- §3.3: the cap on undo_stack size -----------------------------------

def test_undo_stack_never_exceeds_fifty_entries(qsettings):
    _app()
    window = _make_window(qsettings)
    for i in range(60):
        window.project.push_state()
    assert len(window.project.undo_stack) == 50
    _close(window)
