"""feat/io-labels-and-ids §5 — property panel rebuild: grouped collapsible
sections, typed/range-checked editors, unit suffixes, undo-stack
discipline, widget cleanup.
"""
import pytest
from PySide6.QtWidgets import QApplication, QSpinBox, QDoubleSpinBox, QComboBox, QLineEdit, QFormLayout

from logic_studio.blocks import register_builtin_blocks
from logic_studio.blocks.registry import BlockRegistry
from logic_studio.core.project import Project
from logic_studio.ui.panels.property_grid import (
    PropertyGridPanel, SECTION_IDENTIFICATION, SECTION_ADDRESSING,
    SECTION_PARAMETERS, SECTION_ADVANCED, _split_unit, _pair_partner,
)


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


register_builtin_blocks()


def _rows(panel, section):
    form = panel._sections[section]["form"]
    out = []
    for row in range(form.rowCount()):
        label = form.itemAt(row, QFormLayout.LabelRole).widget().text()
        field = form.itemAt(row, QFormLayout.FieldRole).widget()
        out.append((label, field))
    return out


# ---- §5.1 grouping --------------------------------------------------------

def test_identification_section_always_has_id_tag_comment(qsettings):
    _app()
    p = Project()
    gate = BlockRegistry.create_block("logic.and")
    p.add_block(gate)
    panel = PropertyGridPanel(settings=qsettings)
    panel.load_block_properties(gate, p)

    labels = [label for label, _ in _rows(panel, SECTION_IDENTIFICATION)]
    assert labels == ["Identyfikator", "Tag", "Comment"]

def test_identyfikator_row_shows_short_id_and_is_read_only(qsettings):
    _app()
    p = Project()
    gate = BlockRegistry.create_block("logic.and")
    p.add_block(gate)
    panel = PropertyGridPanel(settings=qsettings)
    panel.load_block_properties(gate, p)

    field = panel.field_widget("Identyfikator")
    assert field.text() == gate.short_id
    assert field.isReadOnly() is True

def test_addressing_section_hidden_for_a_non_addressed_block(qsettings):
    _app()
    p = Project()
    gate = BlockRegistry.create_block("logic.and")
    p.add_block(gate)
    panel = PropertyGridPanel(settings=qsettings)
    panel.load_block_properties(gate, p)

    assert panel._sections[SECTION_ADDRESSING]["box"].isHidden() is True

def test_addressing_section_shown_for_a_di_block(qsettings):
    _app()
    p = Project()
    di = BlockRegistry.create_block("input.di")
    p.add_block(di)
    panel = PropertyGridPanel(settings=qsettings)
    panel.load_block_properties(di, p)

    assert panel._sections[SECTION_ADDRESSING]["box"].isHidden() is False
    labels = [label for label, _ in _rows(panel, SECTION_ADDRESSING)]
    assert "Address" in labels

def test_parameters_section_hidden_when_block_has_no_extra_properties(qsettings):
    _app()
    p = Project()
    gate = BlockRegistry.create_block("logic.and")
    p.add_block(gate)
    panel = PropertyGridPanel(settings=qsettings)
    panel.load_block_properties(gate, p)

    assert panel._sections[SECTION_PARAMETERS]["box"].isHidden() is True

def test_parameters_section_shown_for_a_timer(qsettings):
    _app()
    p = Project()
    ton = BlockRegistry.create_block("timer.ton")
    p.add_block(ton)
    panel = PropertyGridPanel(settings=qsettings)
    panel.load_block_properties(ton, p)

    assert panel._sections[SECTION_PARAMETERS]["box"].isHidden() is False
    labels = [label for label, _ in _rows(panel, SECTION_PARAMETERS)]
    assert labels == ["Preset"]  # unit stripped from the label — §5.3

def test_advanced_section_has_uuid_category_priority_only(qsettings):
    """§5.6: Execution State/Visible are gone; Enabled has no property-
    panel row post-audit either (§5.1's own list never mentions it)."""
    _app()
    p = Project()
    gate = BlockRegistry.create_block("logic.and")
    p.add_block(gate)
    panel = PropertyGridPanel(settings=qsettings)
    panel.load_block_properties(gate, p)

    labels = [label for label, _ in _rows(panel, SECTION_ADVANCED)]
    assert labels == ["UUID", "Category", "Priority"]

def test_identification_and_advanced_default_expanded_and_collapsed(qsettings):
    _app()
    panel = PropertyGridPanel(settings=qsettings)
    assert panel._sections[SECTION_IDENTIFICATION]["box"].isChecked() is True
    assert panel._sections[SECTION_ADDRESSING]["box"].isChecked() is True
    assert panel._sections[SECTION_PARAMETERS]["box"].isChecked() is True
    assert panel._sections[SECTION_ADVANCED]["box"].isChecked() is False

def test_collapse_state_persists_via_settings(qsettings):
    _app()
    panel = PropertyGridPanel(settings=qsettings)
    panel._sections[SECTION_ADVANCED]["box"].setChecked(True)

    panel2 = PropertyGridPanel(settings=qsettings)
    assert panel2._sections[SECTION_ADVANCED]["box"].isChecked() is True

def test_toggling_a_section_hides_shows_its_content(qsettings):
    _app()
    p = Project()
    gate = BlockRegistry.create_block("logic.and")
    p.add_block(gate)
    panel = PropertyGridPanel(settings=qsettings)
    panel.load_block_properties(gate, p)

    content = panel._sections[SECTION_IDENTIFICATION]["content"]
    assert content.isHidden() is False
    panel._sections[SECTION_IDENTIFICATION]["box"].setChecked(False)
    assert content.isHidden() is True

def test_empty_state_shows_placeholder_not_blank_panel(qsettings):
    _app()
    panel = PropertyGridPanel(settings=qsettings)
    panel._set_empty_state()
    labels = [panel.layout().itemAt(i).widget() for i in range(panel.layout().count())]
    texts = [w.text() for w in labels if hasattr(w, 'text')]
    assert any("Brak zaznaczonego bloku" in t for t in texts)


# ---- §5.3 unit suffix presentation ---------------------------------------

def test_split_unit_extracts_suffix():
    assert _split_unit("Preset (ms)") == ("Preset", "ms")
    assert _split_unit("Samples") == ("Samples", None)

def test_numeric_field_shows_unit_as_suffix_not_in_label(qsettings):
    _app()
    p = Project()
    ton = BlockRegistry.create_block("timer.ton")
    p.add_block(ton)
    panel = PropertyGridPanel(settings=qsettings)
    panel.load_block_properties(ton, p)

    field = panel.field_widget("Preset")
    assert isinstance(field, QSpinBox)
    assert field.suffix() == " ms"

def test_properties_dict_key_is_never_touched_by_the_unit_split():
    """§5.3: "Klucze properties zostają BEZ ZMIAN" — the model still uses
    the original "Preset (ms)" key regardless of how it's displayed."""
    ton = BlockRegistry.create_block("timer.ton")
    assert "Preset (ms)" in ton.properties


# ---- §5.2 typed editors + ranges -----------------------------------------

def test_int_property_gets_a_spinbox_with_domain_floor(qsettings):
    _app()
    p = Project()
    ton = BlockRegistry.create_block("timer.ton")
    p.add_block(ton)
    panel = PropertyGridPanel(settings=qsettings)
    panel.load_block_properties(ton, p)

    field = panel.field_widget("Preset")
    assert field.minimum() == 0  # non-negative time

def test_samples_property_has_minimum_one(qsettings):
    _app()
    p = Project()
    b = BlockRegistry.create_block("analog.mov_avg")
    p.add_block(b)
    panel = PropertyGridPanel(settings=qsettings)
    panel.load_block_properties(b, p)

    field = panel.field_widget("Samples")
    assert isinstance(field, QSpinBox)
    assert field.minimum() == 1

def test_float_property_gets_a_double_spinbox(qsettings):
    _app()
    p = Project()
    b = BlockRegistry.create_block("analog.limit")
    p.add_block(b)
    panel = PropertyGridPanel(settings=qsettings)
    panel.load_block_properties(b, p)

    field = panel.field_widget("Min")
    assert isinstance(field, QDoubleSpinBox)

def test_bool_property_gets_a_combobox():
    """No shipped block currently has a bare bool property, but the editor
    factory must still handle one correctly if/when one is added."""
    _app()
    from logic_studio.ui.panels.property_grid import PropertyGridPanel as PGP
    panel = PGP()
    block = BlockRegistry.create_block("logic.and")
    block.properties["SomeFlag"] = True
    p = Project()
    p.add_block(block)
    panel.load_block_properties(block, p)

    field = panel.field_widget("SomeFlag")
    assert isinstance(field, QComboBox)
    assert field.currentText() == "True"

def test_known_enum_property_gets_a_combobox_with_its_options(qsettings):
    _app()
    p = Project()
    b = BlockRegistry.create_block("analog.deadband")
    p.add_block(b)
    panel = PropertyGridPanel(settings=qsettings)
    panel.load_block_properties(b, p)

    field = panel.field_widget("Mode")
    assert isinstance(field, QComboBox)
    assert [field.itemText(i) for i in range(field.count())] == ["Bezwzględny", "Procentowy"]

def test_plain_string_property_gets_a_line_edit(qsettings):
    _app()
    p = Project()
    b = BlockRegistry.create_block("const.string")
    p.add_block(b)
    panel = PropertyGridPanel(settings=qsettings)
    panel.load_block_properties(b, p)

    field = panel.field_widget("Text")
    assert isinstance(field, QLineEdit)


# ---- §5.2 min<max pair validation -----------------------------------------

def test_pair_partner_recognizes_known_pairs():
    assert _pair_partner("Min") == ("low", "Max")
    assert _pair_partner("Max") == ("high", "Min")
    assert _pair_partner("In Min") == ("low", "In Max")
    assert _pair_partner("Nonexistent") is None

def test_setting_min_above_max_is_rejected_with_status_message(qsettings):
    _app()
    from logic_studio.ui.main_window import MainWindow

    window = MainWindow(settings=qsettings)
    p = window.project
    b = BlockRegistry.create_block("analog.limit")
    p.add_block(b)
    window.property_panel.load_block_properties(b, p)

    field = window.property_panel.field_widget("Min")
    field.setValue(150.0)  # Max defaults to 100.0 -> Min must stay < Max
    field.editingFinished.emit()

    assert b.properties["Min"] == 0.0  # unchanged — rejected
    assert field.value() == 0.0  # editor reverted too
    assert window.statusBar().currentMessage() != ""
    window.is_dirty = False  # avoid the real Unsaved-Changes modal on close()
    window.close()

def test_setting_a_valid_min_max_pair_is_accepted(qsettings):
    _app()
    from logic_studio.ui.main_window import MainWindow

    window = MainWindow(settings=qsettings)
    p = window.project
    b = BlockRegistry.create_block("analog.limit")
    p.add_block(b)
    window.property_panel.load_block_properties(b, p)

    field = window.property_panel.field_widget("Min")
    field.setValue(50.0)
    field.editingFinished.emit()

    assert b.properties["Min"] == 50.0
    window.is_dirty = False  # avoid the real Unsaved-Changes modal on close()
    window.close()


# ---- §5.4 undo stack discipline -------------------------------------------

def test_editing_finished_with_unchanged_value_does_not_push_undo_state(qsettings):
    _app()
    from logic_studio.ui.main_window import MainWindow

    window = MainWindow(settings=qsettings)
    p = window.project
    ton = BlockRegistry.create_block("timer.ton")
    p.add_block(ton)
    window.property_panel.load_block_properties(ton, p)

    before = len(p.undo_stack)
    field = window.property_panel.field_widget("Preset")
    field.editingFinished.emit()  # no value change at all
    assert len(p.undo_stack) == before
    window.is_dirty = False  # avoid the real Unsaved-Changes modal on close()
    window.close()

def test_editing_finished_with_a_real_change_pushes_exactly_one_undo_state(qsettings):
    _app()
    from logic_studio.ui.main_window import MainWindow

    window = MainWindow(settings=qsettings)
    p = window.project
    ton = BlockRegistry.create_block("timer.ton")
    p.add_block(ton)
    window.property_panel.load_block_properties(ton, p)

    before = len(p.undo_stack)
    field = window.property_panel.field_widget("Preset")
    field.setValue(field.value() + 500)
    field.editingFinished.emit()

    assert len(p.undo_stack) == before + 1
    assert ton.properties["Preset (ms)"] == field.value()
    window.is_dirty = False  # avoid the real Unsaved-Changes modal on close()
    window.close()

def test_spinbox_does_not_fire_on_every_keystroke():
    """§5.4: keyboardTracking must be off, or valueChanged (and therefore
    any commit wired to it) fires on every digit typed."""
    _app()
    p = Project()
    ton = BlockRegistry.create_block("timer.ton")
    p.add_block(ton)
    panel = PropertyGridPanel()
    panel.load_block_properties(ton, p)

    field = panel.field_widget("Preset")
    assert field.keyboardTracking() is False


# ---- §5.5 widget cleanup ---------------------------------------------------

def test_switching_blocks_does_not_leak_previous_editor_widgets(qsettings):
    _app()
    p = Project()
    ton = BlockRegistry.create_block("timer.ton")
    gate = BlockRegistry.create_block("logic.and")
    p.add_block(ton)
    p.add_block(gate)

    panel = PropertyGridPanel(settings=qsettings)
    panel.load_block_properties(ton, p)
    preset_field = panel.field_widget("Preset")

    panel.load_block_properties(gate, p)

    assert panel.field_widget("Preset") is None  # TON's row is gone
    # QFormLayout.removeRow() doesn't just detach the old widget, it
    # deletes the underlying C++ object outright — accessing it now raises,
    # which is the strongest possible proof nothing was leaked.
    with pytest.raises(RuntimeError):
        preset_field.parent()
