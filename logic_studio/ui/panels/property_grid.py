"""feat/io-labels-and-ids §5 — property panel rebuild.

Reference point: e²TANGO's own property panel shows two rows —
Identyfikator and Bit wejściowy. Ours used to show eight, starting with a
36-character UUID. This groups everything into four collapsible sections
(Identyfikacja/Adresacja/Parametry/Zaawansowane, §5.1), replaces free-text
table cells with typed, range-checked editors (§5.2), moves a numeric
property's unit onto the editor as a suffix instead of baking it into the
displayed name (§5.3 — the underlying `properties` dict KEY is untouched),
stops flooding the undo stack on every keystroke (§5.4), and cleans up the
per-block editor widgets it creates instead of leaking them across a
selection change (§5.5).
"""
import re

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QGroupBox, QLabel, QLineEdit,
    QSpinBox, QDoubleSpinBox, QComboBox, QPushButton
)
from PySide6.QtCore import Qt, QSettings
from logic_studio.core.device_model import DeviceModel

# feat/internal-bits §6.1: SignalPickerDialog opens for these (type_id,
# property key) pairs — value_type/sections tell the dialog what to show.
_SIGNAL_PICKER_TARGETS = {
    ("virtual.input", "Bit"): ("BOOL", ("internal",)),
    ("virtual.output", "Bit"): ("BOOL", ("internal",)),
    ("internal.reg_in", "Bit"): ("REAL", ("internal",)),
    ("internal.reg_out", "Bit"): ("REAL", ("internal",)),
    ("system.signal", "Sygnał"): (None, ("system",)),
}

# feat/io-labels-and-ids §5.1: the four collapsible sections, in display
# order, with their default expanded/collapsed state.
SECTION_IDENTIFICATION = "Identyfikacja"
SECTION_ADDRESSING = "Adresacja"
SECTION_PARAMETERS = "Parametry"
SECTION_ADVANCED = "Zaawansowane"
_SECTION_DEFAULT_EXPANDED = {
    SECTION_IDENTIFICATION: True,
    SECTION_ADDRESSING: True,
    SECTION_PARAMETERS: True,
    SECTION_ADVANCED: False,  # §5.1: UUID/Category/Priority — rarely needed
}

_ADDRESSING_KEYS = ("Address", "Bit", "Sygnał")
# "Address" is a key on EVERY block's properties dict (BaseLogicBlock.
# __init__ sets it unconditionally, empty, regardless of block type) — but
# it only actually APPLIES (§5.1: "tylko gdy dotyczy") to the four block
# types that use it for real addressing. Showing an empty "Address" row on
# every gate/timer/etc. would be exactly the kind of always-there-even-
# when-meaningless UI element §5.6 elsewhere in this PR removes on sight.
_ADDRESS_TYPE_IDS = ("input.di", "output.do", "input.ai", "output.ao")
_IDENTIFICATION_KEYS = ("Tag", "Comment")  # "Identyfikator" (short_id) is always first, read-only

# §5.2/§5.3: domain-appropriate ranges and display-only unit suffixes for
# numeric properties, keyed by property NAME — there is no per-block
# property schema in this codebase to hang range metadata on directly, and
# a property name (e.g. "Preset", "Samples") is used consistently across
# whichever block types happen to have it. Presentation-only per §5.3: the
# `properties` dict KEY itself is never touched.
_UNIT_SUFFIX_RE = re.compile(r'^(.*) \(([^)]+)\)$')


def _split_unit(key: str):
    """"Preset (ms)" -> ("Preset", "ms"); "Samples" -> ("Samples", None)."""
    m = _UNIT_SUFFIX_RE.match(key)
    return (m.group(1), m.group(2)) if m else (key, None)


def _int_floor(key: str):
    base, unit = _split_unit(key)
    if unit in ("ms", "s"):
        return 0  # §5.2: "czasy nieujemne"
    if base == "Samples":
        return 1  # §5.2: "liczba próbek >= 1"
    if base in ("Preset", "Stuck Scans"):
        return 0  # a count; never negative
    return None


def _float_floor(key: str):
    base, unit = _split_unit(key)
    if unit in ("ms", "s"):
        return 0.0
    if base in ("Hysteresis", "Deadband", "Range", "Max Rate"):
        return 0.0
    return None


# §5.2: "min < max tam gdzie występuje para" — (low, high) name pairs.
# "Low Threshold"/"High Threshold" (HYSTERESIS block) is the same domain
# concept under different names, included for the same reason a Low
# threshold at or above High would make the block's own logic meaningless.
_RANGE_PAIRS = [
    ("Min", "Max"), ("In Min", "In Max"), ("Out Min", "Out Max"),
    ("Low Threshold", "High Threshold"),
]


def _pair_partner(key: str):
    """('low'|'high', partner_key) if `key` is half of a known min<max
    pair, else None."""
    for lo, hi in _RANGE_PAIRS:
        if key == lo:
            return ("low", hi)
        if key == hi:
            return ("high", lo)
    return None


# Known closed sets for a string property that isn't Address/Bit/Sygnał —
# same idea as _SIGNAL_PICKER_TARGETS, keyed by (type_id, key). Anything not
# listed here falls back to a plain QLineEdit (§5.2's "QLineEdit dla tekstu").
_COMBO_OPTIONS = {
    ("analog.deadband", "Mode"): ["Bezwzględny", "Procentowy"],
    ("system.button", "Mode"): ["Monostabilny", "Bistabilny"],
}

_NUMERIC_RANGE = 1_000_000  # generic wide bound when no domain floor/ceiling applies


class PropertyGridPanel(QWidget):
    def __init__(self, parent=None, settings=None):
        super().__init__(parent)
        # Injectable so tests/verification scripts don't touch the real
        # user registry — same pattern as LibraryPanel/SimulationPanel.
        self.settings = settings if settings is not None else QSettings("BroniszLabs", "EPW Logic Studio")

        self.current_block = None
        self.current_project = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self._sections = {}  # name -> {"box", "form", "content"}
        for name in (SECTION_IDENTIFICATION, SECTION_ADDRESSING, SECTION_PARAMETERS, SECTION_ADVANCED):
            box = QGroupBox(name)
            box.setCheckable(True)
            expanded = self._read_section_expanded(name)
            box.setChecked(expanded)

            content = QWidget()
            form = QFormLayout(content)
            content.setVisible(expanded)

            box_layout = QVBoxLayout(box)
            box_layout.setContentsMargins(6, 4, 6, 4)
            box_layout.addWidget(content)

            box.toggled.connect(lambda checked, n=name, c=content: self._on_section_toggled(n, checked, c))
            layout.addWidget(box)
            self._sections[name] = {"box": box, "form": form, "content": content}

        layout.addStretch(1)
        self._set_empty_state()

    # ---- Section collapse state (§5.1) -------------------------------------

    def _section_setting_key(self, name):
        return f"property_panel/section_expanded/{name}"

    def _read_section_expanded(self, name):
        val = self.settings.value(self._section_setting_key(name), _SECTION_DEFAULT_EXPANDED[name])
        if isinstance(val, str):
            return val.lower() in ("true", "1")
        return bool(val)

    def _on_section_toggled(self, name, checked, content):
        content.setVisible(checked)
        self.settings.setValue(self._section_setting_key(name), checked)

    # ---- Widget cleanup (§5.5) ----------------------------------------------

    @staticmethod
    def _clear_form(form: QFormLayout):
        """Removes and deletes every row this form currently holds —
        comboboxes/spinboxes created per-block via setCellWidget-equivalent
        addRow() calls were never explicitly released before a rebuild,
        leaking one full set of editor widgets per block selection."""
        while form.rowCount():
            form.removeRow(0)  # removeRow() deletes both the label and field widgets

    def _clear_all_sections(self):
        for info in self._sections.values():
            self._clear_form(info["form"])

    def _set_empty_state(self):
        self._clear_all_sections()
        for info in self._sections.values():
            info["box"].setVisible(False)
        empty_box = QGroupBox()
        empty_box.setFlat(True)
        # A single, unmissable placeholder — not an empty panel that could
        # be mistaken for "still loading" or a bug.
        layout = self.layout()
        placeholder = QLabel("Brak zaznaczonego bloku")
        placeholder.setObjectName("property_panel_empty_label")
        # Remove any previous placeholder before adding a new one.
        for i in reversed(range(layout.count())):
            item = layout.itemAt(i)
            w = item.widget()
            if w is not None and w.objectName() == "property_panel_empty_label":
                layout.removeWidget(w)
                w.deleteLater()
        layout.insertWidget(0, placeholder)

    # ---- Population ----------------------------------------------------------

    def load_block_properties(self, block, project=None):
        self.current_block = block
        self.current_project = project

        self._clear_all_sections()
        self._remove_empty_placeholder()

        self._populate_identification(block)
        self._populate_addressing(block, project)
        self._populate_parameters(block)
        self._populate_advanced(block)

        for info in self._sections.values():
            has_rows = info["form"].rowCount() > 0
            info["box"].setVisible(has_rows)  # §5.1: an empty section is hidden, not shown empty

    def _remove_empty_placeholder(self):
        layout = self.layout()
        for i in reversed(range(layout.count())):
            item = layout.itemAt(i)
            w = item.widget()
            if w is not None and w.objectName() == "property_panel_empty_label":
                layout.removeWidget(w)
                w.deleteLater()

    def _populate_identification(self, block):
        form = self._sections[SECTION_IDENTIFICATION]["form"]

        id_edit = QLineEdit(block.short_id)
        id_edit.setReadOnly(True)
        form.addRow("Identyfikator", id_edit)

        for key in _IDENTIFICATION_KEYS:
            value = block.properties.get(key, "")
            editor = self._make_text_editor(key, value)
            form.addRow(key, editor)

    def _populate_addressing(self, block, project):
        form = self._sections[SECTION_ADDRESSING]["form"]

        for key in _ADDRESSING_KEYS:
            if key not in block.properties:
                continue
            if key == "Address" and block.type_id not in _ADDRESS_TYPE_IDS:
                continue
            value = block.properties.get(key, "")
            editor = self._make_addressing_editor(block, key, value, project)
            if editor is not None:
                form.addRow(key, editor)

        if block.type_id in ("input.di", "virtual.input"):
            force_value = block.simulation_state.get("force_state", "NO FORCE")
            combo = QComboBox()
            combo.addItems(["NO FORCE", "FORCE FALSE", "FORCE TRUE"])
            combo.setCurrentText(force_value)
            combo.currentTextChanged.connect(self._on_force_state_changed)
            form.addRow("Force State", combo)

    def _populate_parameters(self, block):
        form = self._sections[SECTION_PARAMETERS]["form"]
        skip = set(_IDENTIFICATION_KEYS) | set(_ADDRESSING_KEYS) | {"Address"}
        for key, value in block.properties.items():
            if key in skip:
                continue
            editor = self._make_property_editor(block, key, value)
            base_name, _unit = _split_unit(key)
            form.addRow(base_name, editor)  # §5.3: unit lives on the editor, not the label

    def _populate_advanced(self, block):
        form = self._sections[SECTION_ADVANCED]["form"]

        uuid_edit = QLineEdit(block.uuid)
        uuid_edit.setReadOnly(True)
        form.addRow("UUID", uuid_edit)

        category_edit = QLineEdit(block.category)
        category_edit.setReadOnly(True)
        form.addRow("Category", category_edit)

        priority_spin = QSpinBox()
        priority_spin.setRange(-_NUMERIC_RANGE, _NUMERIC_RANGE)
        priority_spin.setValue(block.execution_priority)
        priority_spin.setKeyboardTracking(False)
        priority_spin.editingFinished.connect(lambda s=priority_spin: self._commit_priority(s.value()))
        form.addRow("Priority", priority_spin)

    # ---- Editor factories ----------------------------------------------------

    def _make_text_editor(self, key, value):
        editor = QLineEdit(str(value))
        editor.editingFinished.connect(lambda k=key, e=editor: self._commit_property(k, e.text(), editor=e))
        return editor

    def _make_addressing_editor(self, block, key, value, project):
        if key == "Address" and block.type_id in ("input.di", "output.do"):
            combo = QComboBox()
            combo.addItems(DeviceModel.get_ela_addresses(project) if block.type_id == "input.di" else DeviceModel.get_ada_addresses(project))
            combo.setCurrentText(str(value))
            combo.currentTextChanged.connect(lambda text, k=key: self._commit_property(k, text))
            return combo
        if key == "Address" and block.type_id in ("input.ai", "output.ao") and project is not None:
            combo = QComboBox()
            combo.addItems(DeviceModel.get_analog_input_addresses(project) if block.type_id == "input.ai" else DeviceModel.get_analog_output_addresses(project))
            combo.setCurrentText(str(value))
            combo.currentTextChanged.connect(lambda text, k=key: self._commit_property(k, text))
            return combo
        if (block.type_id, key) in _SIGNAL_PICKER_TARGETS:
            btn = QPushButton(str(value) or "(nie wybrano)")
            btn.clicked.connect(lambda checked=False, k=key, b=btn: self._open_signal_picker(k, b))
            return btn
        # Address on a block type not covered above (shouldn't normally
        # happen — Address only ever appears on DI/DO/AI/AO) or a project-
        # less AI/AO block still under construction: plain text fallback,
        # never silently drop the row.
        return self._make_text_editor(key, value)

    def _make_property_editor(self, block, key, value):
        if isinstance(value, bool):
            combo = QComboBox()
            combo.addItems(["True", "False"])
            combo.setCurrentText(str(value))
            combo.currentTextChanged.connect(lambda text, k=key: self._commit_property(k, text))
            return combo

        options = _COMBO_OPTIONS.get((block.type_id, key))
        if options is not None:
            combo = QComboBox()
            combo.addItems(options)
            combo.setCurrentText(str(value))
            combo.currentTextChanged.connect(lambda text, k=key: self._commit_property(k, text))
            return combo

        if isinstance(value, int) and not isinstance(value, bool):
            return self._make_numeric_editor(key, value, is_float=False)

        if isinstance(value, float):
            return self._make_numeric_editor(key, value, is_float=True)

        return self._make_text_editor(key, value)

    def _make_numeric_editor(self, key, value, is_float: bool):
        base, unit = _split_unit(key)
        if is_float:
            editor = QDoubleSpinBox()
            editor.setDecimals(4)
            editor.setRange(-float(_NUMERIC_RANGE), float(_NUMERIC_RANGE))
            floor = _float_floor(key)
            if floor is not None:
                editor.setMinimum(floor)
        else:
            editor = QSpinBox()
            editor.setRange(-_NUMERIC_RANGE, _NUMERIC_RANGE)
            floor = _int_floor(key)
            if floor is not None:
                editor.setMinimum(floor)
        if unit:
            editor.setSuffix(f" {unit}")  # §5.3
        editor.setValue(value)
        editor.setKeyboardTracking(False)  # §5.4: don't fire on every keystroke
        editor.editingFinished.connect(lambda k=key, e=editor: self._commit_property(k, e.value(), editor=e))
        return editor

    # ---- Commit / validation (§5.2/§5.4) --------------------------------------

    def _commit_property(self, key, new_value, editor=None):
        if not self.current_block:
            return
        old_value = self.current_block.properties.get(key)

        pair = _pair_partner(key)
        if pair is not None and isinstance(new_value, (int, float)) and not isinstance(new_value, bool):
            role, partner_key = pair
            partner_value = self.current_block.properties.get(partner_key)
            if isinstance(partner_value, (int, float)):
                ok = (new_value < partner_value) if role == "low" else (new_value > partner_value)
                if not ok:
                    verb = "mniejsza niż" if role == "low" else "większa niż"
                    self._reject_value(
                        old_value, editor,
                        f"Wartość '{key}' musi być {verb} '{partner_key}' — odrzucono.",
                    )
                    return

        # §5.4: only touch the undo stack when the value actually changed —
        # editingFinished/currentTextChanged already fire on a no-op commit
        # (e.g. tabbing through a field without editing it).
        if str(old_value) == str(new_value):
            return

        window = self.window()
        if hasattr(window, 'project'):
            window.project.push_state()
            window.set_dirty()

        self.current_block.update_property(key, str(new_value))

        if key == "Address" and hasattr(window, 'simulation_panel'):
            window.simulation_panel.refresh()

        if hasattr(window, 'scene'):
            window.scene.update()

    def _reject_value(self, old_value, editor, message):
        """§5.2: revert the editor to its last good value and show `message`
        on the status bar for 4 seconds — never silently keep an invalid
        edit without telling the engineer why."""
        if editor is not None:
            editor.blockSignals(True)
            if isinstance(editor, (QSpinBox, QDoubleSpinBox)):
                editor.setValue(old_value)
            elif isinstance(editor, QLineEdit):
                editor.setText(str(old_value))
            editor.blockSignals(False)
        window = self.window()
        if hasattr(window, 'statusBar'):
            window.statusBar().showMessage(message, 4000)

    def _commit_priority(self, new_value):
        if not self.current_block:
            return
        if self.current_block.execution_priority == new_value:
            return
        window = self.window()
        if hasattr(window, 'project'):
            window.project.push_state()
            window.set_dirty()
        self.current_block.execution_priority = new_value
        if hasattr(window, 'scene'):
            window.scene.update()

    def _on_force_state_changed(self, text):
        # Runtime-only override (AUDIT_REPORT.md §5.1): lives in
        # simulation_state, never in properties, so it can never be saved
        # to a project file or ride along into an exported runtime. Not an
        # undoable edit either.
        if not self.current_block:
            return
        self.current_block.simulation_state["force_state"] = text
        window = self.window()
        if hasattr(window, 'scene'):
            window.scene.update()

    def _open_signal_picker(self, key, button):
        """feat/internal-bits §6.1/§6.7: opens SignalPickerDialog for the
        given property; on accept, sets the property, pushes undo state,
        marks dirty, repaints the canvas — the same side effects
        _commit_property() gives every other property, just triggered from
        a button instead of an edited field."""
        if not self.current_block:
            return
        target = _SIGNAL_PICKER_TARGETS.get((self.current_block.type_id, key))
        if target is None:
            return
        value_type, sections = target

        window = self.window()
        project = getattr(window, 'project', None) or self.current_project
        if project is None:
            return

        from logic_studio.ui.signal_picker import SignalPickerDialog
        from PySide6.QtWidgets import QDialog

        dialog = SignalPickerDialog(project, value_type=value_type, parent=self, sections=sections)
        if dialog.exec() != QDialog.Accepted:
            return
        chosen = dialog.selected_signal_id()
        if not chosen:
            return

        if hasattr(window, 'project'):
            window.project.push_state()
            window.set_dirty()

        self.current_block.update_property(key, chosen)
        button.setText(chosen)

        if hasattr(window, 'scene'):
            window.scene.update()

    # ---- Test/introspection helper -------------------------------------------

    def field_widget(self, label: str):
        """The editor widget for the row whose label matches `label`, in
        whichever section it lives — None if not currently shown. Meant
        for tests; the panel itself never needs to look a row up by label."""
        for info in self._sections.values():
            form = info["form"]
            for row in range(form.rowCount()):
                label_item = form.itemAt(row, QFormLayout.LabelRole)
                if label_item and isinstance(label_item.widget(), QLabel) and label_item.widget().text() == label:
                    field_item = form.itemAt(row, QFormLayout.FieldRole)
                    return field_item.widget() if field_item else None
        return None
