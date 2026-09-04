"""feat/duplicate-address-hyperlink — ui/canvas/navigation.py: shared
"select + center + pulse-highlight a block" helpers, factored out of
SignalsPanel (feat/signal-crossref §3.1) so BlockItem's own context menu
can jump directly between blocks sharing a signal reference without
duplicating this logic.
"""
import time

import pytest
from PySide6.QtWidgets import QApplication, QGraphicsRectItem
from PySide6.QtTest import QTest

from logic_studio.blocks import register_builtin_blocks
from logic_studio.ui.canvas.navigation import find_block_item, pulse_highlight, jump_to_block

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


def test_find_block_item_locates_by_uuid(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    block = window.project.blocks[0]

    item = find_block_item(window.scene, block.uuid)
    assert item is not None
    assert item.logic_block.uuid == block.uuid
    _close(window)

def test_find_block_item_returns_none_for_unknown_uuid(qsettings):
    _app()
    window = _make_window(qsettings)
    assert find_block_item(window.scene, "not-a-real-uuid") is None
    _close(window)


def test_pulse_highlight_overlay_is_added_then_removed(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("output.do", 0, 0)
    window.project.blocks[0].properties["Address"] = "ADA01.DO01"

    from logic_studio.ui.canvas.block_item import BlockItem
    item = next(i for i in window.scene.items() if isinstance(i, BlockItem))

    before = len([i for i in window.scene.items() if isinstance(i, QGraphicsRectItem)])
    pulse_highlight(window.scene, item, cycles=2, interval_ms=20)
    during = len([i for i in window.scene.items() if isinstance(i, QGraphicsRectItem)])
    assert during == before + 1

    # CI flake fix (feat/clipboard-and-align, diagnosed from a real CI
    # failure — the SAME commit passed on `pull_request` and failed on
    # `push` 39 minutes later): a single fixed QTest.qWait(150) then one
    # check is exactly the shape of test that goes flaky under runner
    # contention — the ~40ms animation (cycles=2 * interval_ms=20) is
    # normally done well within 150ms, but a stalled/throttled CI runner
    # can occasionally miss even a 3.75x margin. Poll instead, with a much
    # larger ceiling than the animation could plausibly need, breaking out
    # the moment the overlay is actually gone rather than waiting a fixed
    # span and checking exactly once.
    deadline = time.monotonic() + 2.0
    after = during
    while time.monotonic() < deadline:
        QTest.qWait(20)
        after = len([i for i in window.scene.items() if isinstance(i, QGraphicsRectItem)])
        if after == before:
            break
    assert after == before
    _close(window)


def test_jump_to_block_selects_and_returns_the_item(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    window.scene.add_block_from_library("logic.not", 300, 0)
    target = window.project.blocks[1]

    result = jump_to_block(window.scene, window.view, target.uuid)

    from logic_studio.ui.canvas.block_item import BlockItem
    selected = [i for i in window.scene.selectedItems() if isinstance(i, BlockItem)]
    assert result is not None
    assert result.logic_block.uuid == target.uuid
    assert len(selected) == 1 and selected[0] is result
    _close(window)

def test_jump_to_block_replaces_the_previous_selection(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    window.scene.add_block_from_library("logic.not", 300, 0)
    first, second = window.project.blocks

    from logic_studio.ui.canvas.block_item import BlockItem
    first_item = next(i for i in window.scene.items() if isinstance(i, BlockItem) and i.logic_block is first)
    first_item.setSelected(True)

    jump_to_block(window.scene, window.view, second.uuid)

    selected = [i for i in window.scene.selectedItems() if isinstance(i, BlockItem)]
    assert len(selected) == 1
    assert selected[0].logic_block.uuid == second.uuid
    _close(window)

def test_jump_to_block_returns_none_for_unknown_uuid(qsettings):
    _app()
    window = _make_window(qsettings)
    assert jump_to_block(window.scene, window.view, "not-a-real-uuid") is None
    _close(window)

def test_jump_to_block_returns_none_with_no_scene_or_view(qsettings):
    assert jump_to_block(None, None, "any-uuid") is None
