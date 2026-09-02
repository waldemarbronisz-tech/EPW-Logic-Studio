"""feat/clipboard-and-align §2 — align and distribute selected blocks.

Block widths for input.di/output.do depend on the rendered identifier text
(font metrics), which can differ across environments/fonts — so expected
positions below are computed from each BlockItem's OWN .width/.height at
test time, never hardcoded. Only heights are safe to assume fixed (40, for
any single-pin gate or IO block, independent of text) and positions are
always chosen as exact multiples of grid_size=10, since op_apply_block_
positions()'s item.setPos() still runs through BlockItem's existing
ItemPositionChange snap-to-grid — a non-grid-aligned expectation would be
silently rounded and the test would be asserting the wrong thing.
"""
import pytest
from PySide6.QtWidgets import QApplication

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


def _snap(value, grid=10):
    """Mirrors BlockItem.itemChange()'s own ItemPositionChange snap-to-
    grid — align/distribute compute raw target positions and let that
    existing mechanism do the snapping (see scene.py's _apply_block_
    positions() docstring), so an expectation involving a block's
    (possibly odd, text-width-dependent) width/2 must be snapped the same
    way before comparing."""
    return round(value / grid) * grid


def _select_in_order(window, blocks):
    """Selects each block's item, one at a time and in the given order, so
    LogicScene.selection_order (§2.2) records that exact order."""
    window.scene.clearSelection()
    for b in blocks:
        _block_item(window, b).setSelected(True)


def _three_blocks(window):
    """input.di, logic.and, output.do at grid-aligned positions — mixed
    widths (io blocks are text-width-dependent, gates are a fixed 40x40),
    uniform height (40 for any single-pin block), so left/right/center-
    horizontal alignment and horizontal distribution all produce
    distinguishable results."""
    window.scene.add_block_from_library("input.di", 100, 10)
    window.scene.add_block_from_library("logic.and", 0, 100)
    window.scene.add_block_from_library("output.do", 300, 200)
    di, and_b, do = window.project.blocks
    return di, and_b, do


# ---- §2.1/§2.2 the eight operations, pixel-exact -----------------------

def test_align_left(qsettings):
    _app()
    window = _make_window(qsettings)
    ref, mid, last = _three_blocks(window)  # ref = input.di, x=100
    _select_in_order(window, [ref, mid, last])

    window.scene.align_left()

    assert ref.x == 100 and ref.y == 10  # reference itself untouched
    assert mid.x == 100 and mid.y == 100  # only x moves
    assert last.x == 100 and last.y == 200
    _close(window)


def test_align_right(qsettings):
    _app()
    window = _make_window(qsettings)
    ref, mid, last = _three_blocks(window)
    ref_item = _block_item(window, ref)
    mid_item = _block_item(window, mid)
    last_item = _block_item(window, last)
    right_edge = ref_item.pos().x() + ref_item.width

    _select_in_order(window, [ref, mid, last])

    window.scene.align_right()

    assert ref.x == 100
    assert mid.x == _snap(right_edge - mid_item.width) and mid.y == 100
    assert last.x == _snap(right_edge - last_item.width) and last.y == 200
    _close(window)


def test_align_top(qsettings):
    _app()
    window = _make_window(qsettings)
    ref, mid, last = _three_blocks(window)  # ref y=10
    _select_in_order(window, [ref, mid, last])

    window.scene.align_top()

    assert ref.y == 10
    assert mid.x == 0 and mid.y == 10  # only y moves
    assert last.x == 300 and last.y == 10
    _close(window)


def test_align_bottom(qsettings):
    _app()
    window = _make_window(qsettings)
    ref, mid, last = _three_blocks(window)  # ref bottom = 10+40=50, all heights 40
    _select_in_order(window, [ref, mid, last])

    window.scene.align_bottom()

    assert ref.y == 10
    assert mid.x == 0 and mid.y == 50 - 40
    assert last.x == 300 and last.y == 50 - 40
    _close(window)


def test_align_center_vertical(qsettings):
    """"Wyśrodkuj w pionie" — horizontal axes aligned (same Y). All three
    blocks are 40 tall here, so this coincides with align_top's result,
    but it must go through the center-based formula, not the top one."""
    _app()
    window = _make_window(qsettings)
    ref, mid, last = _three_blocks(window)  # ref center_y = 10+20=30
    _select_in_order(window, [ref, mid, last])

    window.scene.align_center_vertical()

    assert ref.y == 10
    assert mid.y == 30 - 20  # mid height 40 -> half=20
    assert last.y == 30 - 20
    _close(window)


def test_align_center_horizontal(qsettings):
    """"Wyśrodkuj w poziomie" — vertical axes aligned (same X). Widths
    differ between an io block and a gate, so this is distinguishable
    from align_left/right."""
    _app()
    window = _make_window(qsettings)
    ref, mid, last = _three_blocks(window)
    ref_item = _block_item(window, ref)
    mid_item = _block_item(window, mid)
    last_item = _block_item(window, last)
    center_x = ref_item.pos().x() + ref_item.width / 2.0
    _select_in_order(window, [ref, mid, last])

    window.scene.align_center_horizontal()

    assert ref.x == 100
    assert mid.x == _snap(center_x - mid_item.width / 2.0)
    assert last.x == _snap(center_x - last_item.width / 2.0)
    _close(window)


def test_distribute_horizontal(qsettings):
    """Equal GAPS between edges (not equal spacing between reference
    points), extremes fixed. Three 40-wide logic.and blocks at x=0, 100,
    400: first/last stay put, the middle one is re-centered so the gap on
    each side is equal: span = 400-(0+40)-40 = 320, gap = 320/2 = 160,
    middle lands at 0+40+160 = 200."""
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 10)
    window.scene.add_block_from_library("logic.and", 100, 10)
    window.scene.add_block_from_library("logic.and", 400, 10)
    first, mid, last = window.project.blocks
    _select_in_order(window, [first, mid, last])  # selection order irrelevant here

    window.scene.distribute_horizontal()

    assert first.x == 0
    assert mid.x == 200
    assert last.x == 400
    assert first.y == 10 and mid.y == 10 and last.y == 10  # y untouched
    _close(window)


def test_distribute_vertical(qsettings):
    """Same math, y axis. Three 40-tall blocks at y=0, 150, 400: span =
    400-(0+40)-40=320, gap=160, middle lands at 0+40+160=200."""
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 10, 0)
    window.scene.add_block_from_library("logic.and", 10, 150)
    window.scene.add_block_from_library("logic.and", 10, 400)
    first, mid, last = window.project.blocks
    _select_in_order(window, [first, mid, last])

    window.scene.distribute_vertical()

    assert first.y == 0
    assert mid.y == 200
    assert last.y == 400
    assert first.x == 10 and mid.x == 10 and last.x == 10  # x untouched
    _close(window)


# ---- one undo entry per operation, regardless of block count -----------

ALIGN_METHODS = [
    "align_left", "align_right", "align_top", "align_bottom",
    "align_center_vertical", "align_center_horizontal",
]
DISTRIBUTE_METHODS = ["distribute_horizontal", "distribute_vertical"]


@pytest.mark.parametrize("method_name", ALIGN_METHODS)
def test_align_operation_is_exactly_one_undo_entry(qsettings, method_name):
    _app()
    window = _make_window(qsettings)
    ref, mid, last = _three_blocks(window)
    _select_in_order(window, [ref, mid, last])

    before = len(window.project.undo_stack)
    getattr(window.scene, method_name)()
    assert len(window.project.undo_stack) == before + 1
    _close(window)


@pytest.mark.parametrize("method_name", DISTRIBUTE_METHODS)
def test_distribute_operation_is_exactly_one_undo_entry(qsettings, method_name):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    window.scene.add_block_from_library("logic.and", 100, 100)
    window.scene.add_block_from_library("logic.and", 400, 400)
    blocks = window.project.blocks
    _select_in_order(window, blocks)

    before = len(window.project.undo_stack)
    getattr(window.scene, method_name)()
    assert len(window.project.undo_stack) == before + 1
    _close(window)


# ---- minimum-selection guards -------------------------------------------

def test_align_does_nothing_with_a_single_block_selected(qsettings):
    _app()
    window = _make_window(qsettings)
    ref, mid, last = _three_blocks(window)
    _select_in_order(window, [mid])

    before = len(window.project.undo_stack)
    window.scene.align_left()
    assert len(window.project.undo_stack) == before  # no-op, no undo entry
    assert mid.x == 0  # unchanged
    _close(window)


def test_distribute_does_nothing_with_only_two_blocks_selected(qsettings):
    _app()
    window = _make_window(qsettings)
    ref, mid, last = _three_blocks(window)
    _select_in_order(window, [ref, mid])

    before = len(window.project.undo_stack)
    window.scene.distribute_horizontal()
    assert len(window.project.undo_stack) == before
    _close(window)


# ---- menu enablement (§2.3) ---------------------------------------------

def test_align_menu_actions_disabled_below_minimum_selection(qsettings):
    from PySide6.QtWidgets import QMenu
    from logic_studio.ui.canvas.scene import populate_align_menu

    _app()
    window = _make_window(qsettings)
    ref, mid, last = _three_blocks(window)
    _select_in_order(window, [ref])  # only one selected

    menu = QMenu()
    populate_align_menu(menu, window.scene)
    labels = {a.text(): a.isEnabled() for a in menu.actions() if a.text()}
    assert labels["Wyrównaj do lewej"] is False
    assert labels["Rozłóż równomiernie w poziomie"] is False
    _close(window)


def test_align_menu_actions_enabled_at_minimum_selection(qsettings):
    from PySide6.QtWidgets import QMenu
    from logic_studio.ui.canvas.scene import populate_align_menu

    _app()
    window = _make_window(qsettings)
    ref, mid, last = _three_blocks(window)
    _select_in_order(window, [ref, mid, last])  # 3 selected -> everything enabled

    menu = QMenu()
    populate_align_menu(menu, window.scene)
    labels = {a.text(): a.isEnabled() for a in menu.actions() if a.text()}
    assert labels["Wyrównaj do lewej"] is True
    assert labels["Rozłóż równomiernie w poziomie"] is True
    _close(window)
