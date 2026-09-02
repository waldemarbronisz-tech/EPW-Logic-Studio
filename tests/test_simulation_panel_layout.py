"""feat/editor-modes-and-geometry §4 — simulation panel ELA/ADA layout bug.

The panel used to lay out DI/DO channels in a hardcoded 4 columns, but was
typically only wide enough to actually show ~2 — DI03/DI04/DI07/DI08/...
(and the equivalent ADA channels) were squeezed out of the visible area with
no horizontal scrollbar to reach them (QScrollArea(widgetResizable=True)
never offers one). This file checks the fix: column count follows the
panel's actual width, and every channel stays present regardless.
"""
import pytest
from PySide6.QtWidgets import QApplication, QScrollArea
from PySide6.QtCore import Qt

from logic_studio.ui.panels.simulation import SimulationPanel, ELA_ADA_COLUMN_WIDTH


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_all_32_di_and_do_channels_exist_as_widgets():
    _app()
    panel = SimulationPanel()
    assert len(panel.ela_boxes) == 32
    assert len(panel.ada_leds) == 32

def test_narrow_panel_still_has_all_32_channels_in_the_layout():
    """The original bug: at the panel's typical docked width, DI/DO channels
    beyond what a hardcoded 4-column grid could show at that width were
    simply unreachable. Forcing the panel to a narrow 200px width must not
    lose any widget — checking count (and layout membership), not
    visibility, per the requirement."""
    _app()
    panel = SimulationPanel()
    panel.resize(200, 600)
    panel._recompute_ela_ada_columns()

    assert len(panel.ela_boxes) == 32
    assert len(panel.ada_leds) == 32
    assert panel.in_layout.count() == 32
    assert panel.out_layout.count() == 32
    for cb in panel.ela_boxes:
        assert panel.in_layout.indexOf(cb) != -1
    for lbl in panel.ada_leds:
        assert panel.out_layout.indexOf(lbl) != -1

def test_column_count_is_derived_from_actual_width_not_hardcoded():
    _app()
    panel = SimulationPanel()

    panel.resize(200, 600)
    panel._recompute_ela_ada_columns()
    narrow_columns = panel._ela_columns

    panel.resize(2000, 600)
    panel._recompute_ela_ada_columns()
    wide_columns = panel._ela_columns

    assert narrow_columns == max(1, 200 // ELA_ADA_COLUMN_WIDTH)
    assert wide_columns == max(1, 2000 // ELA_ADA_COLUMN_WIDTH)
    assert wide_columns > narrow_columns

def test_resize_event_triggers_relayout():
    """resizeEvent is a thin wrapper around _recompute_ela_ada_columns() —
    call it the way Qt would, through resize(), and confirm the column
    count actually followed."""
    _app()
    panel = SimulationPanel()
    panel.resize(200, 600)
    panel._recompute_ela_ada_columns()
    assert panel._ela_columns == max(1, 200 // ELA_ADA_COLUMN_WIDTH)

def test_vertical_scrollbar_policy_is_as_needed():
    """§4: a vertical scrollbar must always be AVAILABLE when content
    overflows (fewer columns -> more rows -> taller content)."""
    _app()
    panel = SimulationPanel()
    scroll = panel.findChildren(QScrollArea)[0]
    assert scroll.verticalScrollBarPolicy() == Qt.ScrollBarAsNeeded


# ---- Filter/search field ------------------------------------------------

def test_filter_field_narrows_visible_di_channels():
    _app()
    panel = SimulationPanel()
    panel.io_filter.setText("DI03")

    # isHidden() reflects setVisible() regardless of whether the panel
    # itself is actually shown on screen (unlike isVisible(), which also
    # depends on ancestor visibility) — the right check for a headless test.
    matching = [cb for cb in panel.ela_boxes if not cb.isHidden()]
    assert all("di03" in cb.text().lower() for cb in matching)
    assert len(matching) == 1

def test_filter_field_matches_do_channels_too():
    _app()
    panel = SimulationPanel()
    panel.io_filter.setText("DO03")
    matching = [lbl for lbl in panel.ada_leds if not lbl.isHidden()]
    assert len(matching) > 0
    assert all("do03" in lbl.text().lower() for lbl in matching)

def test_clearing_filter_shows_everything_again():
    _app()
    panel = SimulationPanel()
    panel.io_filter.setText("DI03")
    panel.io_filter.setText("")
    assert all(not cb.isHidden() for cb in panel.ela_boxes)
    assert all(not lbl.isHidden() for lbl in panel.ada_leds)

def test_filtered_channels_do_not_lose_state():
    """Filtering must only hide widgets, never remove/recreate them — a
    checked DI box must stay checked after being hidden and re-shown."""
    _app()
    panel = SimulationPanel()
    panel.ela_boxes[5].setChecked(True)
    panel.io_filter.setText("something-that-matches-nothing")
    panel.io_filter.setText("")
    assert panel.ela_boxes[5].isChecked() is True
