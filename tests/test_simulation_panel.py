"""feat/wire-modes-and-labels §0A — simulation panel rebuild.

§0A.0: DI/AI are stimulus (engineer-set, clickable); DO/AO are response
(logic-set, read-only). §0A.1 fixes the real bug behind this rebuild: the
previous panel computed its DI/DO column count from the panel's own
REQUESTED width, not the width actually available in the scrolled viewport,
so a fraction of channels rendered outside the visible area. §0A.2 adds an
"only used" filter, default ON. §0A.4 groups the "all channels" view into
fixed banks of 8 whose internal channel order never changes, only which
column of groups they land in.
"""
import pytest
from PySide6.QtWidgets import QApplication

from logic_studio.core.project import Project
from logic_studio.blocks import register_builtin_blocks
from logic_studio.blocks.registry import BlockRegistry
from logic_studio.ui.panels.simulation import SimulationPanel, GROUP_SIZE, _short_address


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


register_builtin_blocks()


def _di_block(address):
    b = BlockRegistry.create_block("input.di")
    b.properties["Address"] = address
    return b

def _do_block(address):
    b = BlockRegistry.create_block("output.do")
    b.properties["Address"] = address
    return b


# ---- §0A.3: short address, no module prefix -------------------------------

def test_short_address_strips_module_prefix():
    assert _short_address("ELA01.DI01") == "DI01"
    assert _short_address("ADA01.DO32") == "DO32"

def test_short_address_passthrough_when_no_dot():
    # _short_address is only ever applied to ELA/ADA addresses (always
    # "<device>.<channel>") — analog point addresses never go through it.
    assert _short_address("DI01") == "DI01"


# ---- §0A.7 (1): all 32+32 channel widgets always exist, at any width -----

@pytest.mark.parametrize("viewport_width", [150, 300, 900])
def test_all_channels_present_at_every_viewport_width(qsettings, viewport_width):
    _app()
    panel = SimulationPanel(settings=qsettings)
    panel.only_used_btn.setChecked(False)  # "wszystkie" — the grouped view §0A.4 governs
    panel.resize(viewport_width, 600)
    panel._recompute_group_columns()

    di_rows = sum(g.layout().count() - 1 for g in panel._di_group_widgets)  # -1 per group header
    do_rows = sum(g.layout().count() - 1 for g in panel._do_group_widgets)
    assert di_rows == 32
    assert do_rows == 32
    assert len(panel._di_compact_rows) == 32
    assert len(panel._do_compact_rows) == 32

@pytest.mark.parametrize("viewport_width", [150, 300, 900])
def test_group_columns_never_exceed_viewport_width(qsettings, viewport_width):
    """§0A.1's actual fix: columns * tile_width must fit inside the real
    viewport width — unless even a single column doesn't fit, in which case
    exactly one (squeezed but visible) column is used regardless (§0A.1:
    "kafelki ścieśnione, ale WIDOCZNE")."""
    _app()
    panel = SimulationPanel(settings=qsettings)
    panel.only_used_btn.setChecked(False)
    panel.resize(viewport_width, 600)
    panel._recompute_group_columns()

    tile_w = panel._group_tile_width()
    columns = panel._group_columns
    assert columns >= 1
    viewport_w = panel._scroll.viewport().width() or panel.width()
    assert columns * tile_w <= viewport_w or columns == 1


# ---- §0A.7 (2): "only used" filter ----------------------------------------

def test_only_used_filter_counts_blocks_referencing_the_address(qsettings):
    _app()
    p = Project()
    p.add_block(_di_block("ELA01.DI01"))
    p.add_block(_di_block("ELA01.DI02"))
    p.add_block(_di_block("ELA01.DI03"))

    panel = SimulationPanel(settings=qsettings)
    panel.set_project(p)  # "only used" is ON by default (§0A.2)

    assert panel.di_used_layout.count() == 3

    p.add_block(_di_block("ELA01.DI04"))
    panel.refresh()

    assert panel.di_used_layout.count() == 4

def test_only_used_is_on_by_default(qsettings):
    _app()
    panel = SimulationPanel(settings=qsettings)
    assert panel.only_used_btn.isChecked() is True

def test_empty_project_shows_placeholder_message(qsettings):
    _app()
    p = Project()
    panel = SimulationPanel(settings=qsettings)
    panel.set_project(p)

    assert panel.di_used_layout.count() == 1
    assert panel.di_used_layout.itemAt(0).widget() is panel.di_empty_label

def test_only_used_setting_persists_across_panel_instances(qsettings):
    _app()
    panel = SimulationPanel(settings=qsettings)
    panel.only_used_btn.setChecked(False)

    panel2 = SimulationPanel(settings=qsettings)
    assert panel2.only_used_btn.isChecked() is False


# ---- §0A.7 (3): group order stability under reflow (§0A.4) ---------------

def test_channel_order_within_groups_is_stable_across_widths(qsettings):
    _app()
    panel = SimulationPanel(settings=qsettings)
    panel.only_used_btn.setChecked(False)

    def group_addresses():
        return [
            [row.full_address for row in [g.layout().itemAt(i).widget() for i in range(1, g.layout().count())]]
            for g in panel._di_group_widgets
        ]

    panel.resize(150, 600)
    panel._recompute_group_columns()
    narrow_order = group_addresses()
    narrow_columns = panel._group_columns

    panel.resize(2000, 600)
    panel._recompute_group_columns()
    wide_order = group_addresses()
    wide_columns = panel._group_columns

    assert narrow_order == wide_order  # channel order inside each group never changes
    assert wide_columns >= narrow_columns  # only the GROUP arrangement (columns) changed

def test_first_group_is_di01_through_di08_in_order():
    _app()
    from logic_studio.core.device_model import DeviceModel
    panel = SimulationPanel()
    first_group = panel._di_group_widgets[0]
    rows = [first_group.layout().itemAt(i).widget() for i in range(1, first_group.layout().count())]
    assert [r.short_address for r in rows] == [f"DI{n:02d}" for n in range(1, 9)]


# ---- §0A.7 (4): row click behavior -----------------------------------------

def test_clicking_anywhere_on_an_input_row_toggles_it(qsettings):
    _app()
    panel = SimulationPanel(settings=qsettings)
    row = panel._di_detail_rows["ELA01.DI01"]
    assert panel.get_ela_state(0) is False

    from PySide6.QtGui import QMouseEvent
    from PySide6.QtCore import QPointF, Qt as QtCore_Qt
    from PySide6.QtCore import QEvent

    event = QMouseEvent(
        QEvent.MouseButtonPress, QPointF(row.width() - 2, row.height() / 2),
        QtCore_Qt.LeftButton, QtCore_Qt.LeftButton, QtCore_Qt.NoModifier,
    )
    row.mousePressEvent(event)

    assert panel.get_ela_state(0) is True

def test_clicking_an_output_row_does_nothing(qsettings):
    _app()
    panel = SimulationPanel(settings=qsettings)
    row = panel._do_detail_rows["ADA01.DO01"]

    from PySide6.QtGui import QMouseEvent
    from PySide6.QtCore import QPointF, Qt as QtCore_Qt, QEvent

    event = QMouseEvent(
        QEvent.MouseButtonPress, QPointF(row.width() - 2, row.height() / 2),
        QtCore_Qt.LeftButton, QtCore_Qt.LeftButton, QtCore_Qt.NoModifier,
    )
    row.mousePressEvent(event)

    # No exception, no state change — set_ada_state is the only legitimate
    # writer of DO state (§0A.0: DO is the logic's answer, not the
    # engineer's).
    assert panel._do_state["ADA01.DO01"] is False


# ---- Public API contract unchanged (MainWindow depends on this) ----------

def test_get_ela_state_and_set_ada_state_are_index_based(qsettings):
    _app()
    panel = SimulationPanel(settings=qsettings)
    panel.set_ada_state(3, True)
    assert panel._do_state["ADA01.DO04"] is True

    row_addr = panel._di_detail_rows and "ELA01.DI05"
    panel._toggle_di("ELA01.DI05")
    assert panel.get_ela_state(4) is True
