"""feat/signal-crossref §2 / feat/signals-panel-tree — the "Sygnały" side
panel (read-only), rebuilt onto a category-grouped QTreeWidget."""
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

from logic_studio.blocks import register_builtin_blocks
from logic_studio.blocks.registry import BlockRegistry
from logic_studio.core.project import Project
from logic_studio.core.device_model import DeviceModel
from logic_studio.ui.panels.signals import SignalsPanel, COL_SIGNAL, COL_STATE, COL_WRITES, COL_READS, COL_LABEL


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


register_builtin_blocks()


def _di(address):
    b = BlockRegistry.create_block("input.di")
    b.properties["Address"] = address
    return b

def _do(address):
    b = BlockRegistry.create_block("output.do")
    b.properties["Address"] = address
    return b

def _row_of(panel, signal_id):
    """The leaf QTreeWidgetItem for `signal_id`, or None."""
    for leaf in panel._iter_leaves():
        if panel._signal_id_of(leaf) == signal_id:
            return leaf
    return None

def _category_of(panel, label):
    return panel._category_items[label]

def _leaf_count(panel):
    return sum(1 for _ in panel._iter_leaves())


# ---- population / empty state -----------------------------------------

def test_empty_project_shows_placeholder_not_a_table(qsettings):
    # isHidden() (not isVisible()) — a never-shown top-level widget's
    # descendants all report isVisible()==False regardless of their own
    # explicit setVisible() call; isHidden() tracks that explicit flag
    # directly, independent of ancestor visibility.
    _app()
    panel = SignalsPanel(settings=qsettings)
    panel.set_project(Project())
    assert panel.tree.isHidden() is True
    assert panel.empty_label.isHidden() is False
    assert "Brak sygnałów" in panel.empty_label.text()

def test_project_with_signals_shows_the_table(qsettings):
    _app()
    p = Project()
    p.add_block(_di("ELA01.DI01"))
    panel = SignalsPanel(settings=qsettings)
    panel.set_project(p)
    assert panel.tree.isHidden() is False
    assert panel.empty_label.isHidden() is True
    assert _leaf_count(panel) == 1

def test_columns_are_in_spec_order(qsettings):
    _app()
    panel = SignalsPanel(settings=qsettings)
    headers = [panel.tree.headerItem().text(i) for i in range(panel.tree.columnCount())]
    assert headers == ["Stan", "Sygnał", "Typ", "Etykieta", "Zapisuje", "Czyta"]

def test_row_shows_label_from_io_labels(qsettings):
    _app()
    p = Project()
    p.add_block(_di("ELA01.DI01"))
    DeviceModel.set_io_label(p, "ELA01.DI01", "Wyłącznik Q1 zamknięty")
    panel = SignalsPanel(settings=qsettings)
    panel.set_project(p)

    leaf = _row_of(panel, "ELA01.DI01")
    assert leaf.text(COL_LABEL) == "Wyłącznik Q1 zamknięty"

def test_physical_input_shows_urzadzenie_as_writer(qsettings):
    _app()
    p = Project()
    di = _di("ELA01.DI01")
    p.add_block(di)
    panel = SignalsPanel(settings=qsettings)
    panel.set_project(p)

    leaf = _row_of(panel, "ELA01.DI01")
    assert leaf.text(COL_WRITES) == "urządzenie"

def test_do_block_shows_its_short_id_as_writer(qsettings):
    _app()
    p = Project()
    do = _do("ADA01.DO01")
    p.add_block(do)
    panel = SignalsPanel(settings=qsettings)
    panel.set_project(p)

    leaf = _row_of(panel, "ADA01.DO01")
    assert leaf.text(COL_WRITES) == do.short_id

def test_multiple_writers_shown_as_comma_list(qsettings):
    p = Project()
    p.settings["internal_bits"] = [{"name": "X", "type": "BOOL", "retentive": False}]
    vo1 = BlockRegistry.create_block("virtual.output"); vo1.properties["Bit"] = "X"
    vo2 = BlockRegistry.create_block("virtual.output"); vo2.properties["Bit"] = "X"
    p.add_block(vo1)
    p.add_block(vo2)
    _app()
    panel = SignalsPanel(settings=qsettings)
    panel.set_project(p)

    leaf = _row_of(panel, "M.X")
    text = leaf.text(COL_WRITES)
    assert vo1.short_id in text and vo2.short_id in text

def test_status_icon_present_for_issue_rows_and_absent_for_clean_rows(qsettings):
    _app()
    p = Project()
    p.add_block(_di("ELA01.DI01"))  # clean
    ghost = BlockRegistry.create_block("virtual.input")
    ghost.properties["Bit"] = "GHOST"
    p.add_block(ghost)  # undefined -> error
    panel = SignalsPanel(settings=qsettings)
    panel.set_project(p)

    clean_leaf = _row_of(panel, "ELA01.DI01")
    error_leaf = _row_of(panel, "GHOST")
    assert clean_leaf.icon(COL_STATE).isNull()
    assert not error_leaf.icon(COL_STATE).isNull()
    assert error_leaf.toolTip(COL_STATE) != ""


# ---- category grouping (feat/signals-panel-tree) --------------------------

def test_signals_are_grouped_under_the_correct_category(qsettings):
    """Categorization is now the TREE'S OWN STRUCTURE (parent node), not a
    filter — a DI lands under "Fizyczne", an internal bit under
    "Wewnętrzne", regardless of anything else selected."""
    _app()
    p = Project()
    p.add_block(_di("ELA01.DI01"))
    p.settings["internal_bits"] = [{"name": "X", "type": "BOOL", "retentive": False}]
    vi = BlockRegistry.create_block("virtual.input"); vi.properties["Bit"] = "X"
    p.add_block(vi)
    panel = SignalsPanel(settings=qsettings)
    panel.set_project(p)

    di_leaf = _row_of(panel, "ELA01.DI01")
    bit_leaf = _row_of(panel, "M.X")
    assert di_leaf.parent() is _category_of(panel, "Fizyczne")
    assert bit_leaf.parent() is _category_of(panel, "Wewnętrzne")
    # Both categories are simultaneously visible (structural, not exclusive
    # like the old single-select filter buttons ever allowed).
    assert _category_of(panel, "Fizyczne").isHidden() is False
    assert _category_of(panel, "Wewnętrzne").isHidden() is False

def test_category_label_shows_signal_count(qsettings):
    _app()
    p = Project()
    p.add_block(_di("ELA01.DI01"))
    p.add_block(_di("ELA01.DI02"))
    panel = SignalsPanel(settings=qsettings)
    panel.set_project(p)

    assert _category_of(panel, "Fizyczne").text(0) == "Fizyczne (2)"
    assert _category_of(panel, "Systemowe").text(0) == "Systemowe (0)"

def test_all_four_categories_always_present_even_when_empty(qsettings):
    _app()
    panel = SignalsPanel(settings=qsettings)
    panel.set_project(Project())
    assert set(panel._category_items.keys()) == {"Fizyczne", "Analogowe", "Wewnętrzne", "Systemowe"}

def test_categories_default_to_expanded(qsettings):
    _app()
    p = Project()
    p.add_block(_di("ELA01.DI01"))
    panel = SignalsPanel(settings=qsettings)
    panel.set_project(p)
    assert _category_of(panel, "Fizyczne").isExpanded() is True

def test_collapsing_a_category_persists_across_instances(qsettings):
    _app()
    p = Project()
    p.add_block(_di("ELA01.DI01"))
    panel = SignalsPanel(settings=qsettings)
    panel.set_project(p)
    _category_of(panel, "Fizyczne").setExpanded(False)  # a real user click, not a filter pass

    panel2 = SignalsPanel(settings=qsettings)
    panel2.set_project(p)
    assert _category_of(panel2, "Fizyczne").isExpanded() is False
    assert _category_of(panel2, "Analogowe").isExpanded() is True  # untouched category unaffected

def test_children_sort_without_reordering_categories(qsettings):
    """Sorting by a column reorders each category's OWN children only —
    the four category nodes themselves must stay in their fixed
    registration order (Fizyczne, Analogowe, Wewnętrzne, Systemowe)
    regardless of which column/direction was clicked."""
    _app()
    p = Project()
    p.add_block(_di("ELA01.DI02"))
    p.add_block(_di("ELA01.DI01"))
    panel = SignalsPanel(settings=qsettings)
    panel.set_project(p)

    from PySide6.QtCore import Qt
    panel._on_sort_indicator_changed(COL_SIGNAL, Qt.AscendingOrder)

    # category order unchanged
    assert [panel.tree.topLevelItem(i).text(0).split(" (")[0] for i in range(4)] == \
           ["Fizyczne", "Analogowe", "Wewnętrzne", "Systemowe"]
    # children within Fizyczne DID sort ascending by signal id
    fizyczne = _category_of(panel, "Fizyczne")
    assert [fizyczne.child(i).text(COL_SIGNAL) for i in range(fizyczne.childCount())] == \
           ["ELA01.DI01", "ELA01.DI02"]


# ---- filtering (§2.3) ---------------------------------------------------

def test_search_matches_signal_id(qsettings):
    _app()
    p = Project()
    p.add_block(_di("ELA01.DI01"))
    p.add_block(_di("ELA01.DI02"))
    panel = SignalsPanel(settings=qsettings)
    panel.set_project(p)
    panel.search_edit.setText("DI01")

    assert _row_of(panel, "ELA01.DI01").isHidden() is False
    assert _row_of(panel, "ELA01.DI02").isHidden() is True

def test_search_matches_label(qsettings):
    _app()
    p = Project()
    p.add_block(_di("ELA01.DI01"))
    DeviceModel.set_io_label(p, "ELA01.DI01", "Blokada bramy")
    panel = SignalsPanel(settings=qsettings)
    panel.set_project(p)
    panel.search_edit.setText("Blokada")
    assert _row_of(panel, "ELA01.DI01").isHidden() is False

def test_search_matches_reader_short_id(qsettings):
    _app()
    p = Project()
    di = _di("ELA01.DI01")
    p.add_block(di)
    panel = SignalsPanel(settings=qsettings)
    panel.set_project(p)
    panel.search_edit.setText(di.short_id)
    assert _row_of(panel, "ELA01.DI01").isHidden() is False

def test_search_hides_the_non_matching_category_and_expands_the_matching_one(qsettings):
    """The tree-specific behavior a filter row never had: a search that
    only matches something in ONE category hides the other, empty-of-
    matches categories entirely and force-expands the matching one, even
    if the user had it collapsed."""
    _app()
    p = Project()
    p.add_block(_di("ELA01.DI01"))
    p.settings["internal_bits"] = [{"name": "X", "type": "BOOL", "retentive": False}]
    vi = BlockRegistry.create_block("virtual.input"); vi.properties["Bit"] = "X"
    p.add_block(vi)
    panel = SignalsPanel(settings=qsettings)
    panel.set_project(p)
    _category_of(panel, "Wewnętrzne").setExpanded(False)

    panel.search_edit.setText("M.X")

    assert _category_of(panel, "Wewnętrzne").isHidden() is False
    assert _category_of(panel, "Wewnętrzne").isExpanded() is True  # force-expanded to reveal the match
    assert _category_of(panel, "Fizyczne").isHidden() is True  # nothing in it matches "M.X"

    panel.search_edit.setText("")  # clearing restores the user's real collapse preference
    assert _category_of(panel, "Wewnętrzne").isExpanded() is False
    assert _category_of(panel, "Fizyczne").isHidden() is False

def test_only_issues_toggle_hides_clean_rows(qsettings):
    _app()
    p = Project()
    p.add_block(_di("ELA01.DI01"))  # clean
    ghost = BlockRegistry.create_block("virtual.input")
    ghost.properties["Bit"] = "GHOST"
    p.add_block(ghost)
    panel = SignalsPanel(settings=qsettings)
    panel.set_project(p)
    panel.only_issues_check.setChecked(True)

    assert _row_of(panel, "ELA01.DI01").isHidden() is True
    assert _row_of(panel, "GHOST").isHidden() is False

def test_only_issues_state_persists_via_settings(qsettings):
    _app()
    panel = SignalsPanel(settings=qsettings)
    panel.only_issues_check.setChecked(True)

    panel2 = SignalsPanel(settings=qsettings)
    assert panel2.only_issues_check.isChecked() is True

def test_collapsing_a_category_does_not_hide_its_children_from_filters_or_export(qsettings):
    """Collapse is a DISPLAY convenience only — a collapsed category's
    children are still real, un-hidden tree items (QTreeWidgetItem.
    isHidden() reflects filtering, not the ancestor's expand state), so
    export/counts must still see them."""
    _app()
    p = Project()
    p.add_block(_di("ELA01.DI01"))
    panel = SignalsPanel(settings=qsettings)
    panel.set_project(p)
    _category_of(panel, "Fizyczne").setExpanded(False)

    leaf = _row_of(panel, "ELA01.DI01")
    assert leaf.isHidden() is False
    assert _leaf_count(panel) == 1


# ---- refresh debounce (§2.4) ---------------------------------------------

def test_set_project_rebuilds_immediately(qsettings):
    _app()
    p = Project()
    p.add_block(_di("ELA01.DI01"))
    panel = SignalsPanel(settings=qsettings)
    panel.set_project(p)
    assert _leaf_count(panel) == 1

def test_request_refresh_schedules_a_debounced_rebuild(qsettings):
    _app()
    panel = SignalsPanel(settings=qsettings)
    panel.project = Project()
    panel.project.add_block(_di("ELA01.DI01"))

    assert _leaf_count(panel) == 0  # not rebuilt yet
    panel.request_refresh()
    assert panel._refresh_timer.isActive() is True
    assert _leaf_count(panel) == 0  # still not rebuilt synchronously

def test_request_refresh_actually_rebuilds_after_the_debounce_window(qsettings):
    _app()
    panel = SignalsPanel(settings=qsettings)
    panel.project = Project()
    panel.project.add_block(_di("ELA01.DI01"))

    panel.request_refresh()
    QTest.qWait(350)  # > REFRESH_DEBOUNCE_MS
    assert _leaf_count(panel) == 1

def test_repeated_requests_coalesce_into_one_rebuild(qsettings):
    """A burst of edits must not cause a burst of rebuilds — only the
    LAST request_refresh() within the debounce window should fire."""
    _app()
    panel = SignalsPanel(settings=qsettings)
    panel.project = Project()

    rebuild_count = {"n": 0}
    original = panel._rebuild
    def counting_rebuild():
        rebuild_count["n"] += 1
        original()
    panel._rebuild = counting_rebuild

    for _ in range(5):
        panel.request_refresh()
        QTest.qWait(20)  # well under the 200ms window each time

    QTest.qWait(350)
    assert rebuild_count["n"] == 1
