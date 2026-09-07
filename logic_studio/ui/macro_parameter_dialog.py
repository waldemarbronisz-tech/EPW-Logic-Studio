"""fix/safety-and-macro-params §C2.1/§C2.2 — BindParameterDialog: pick an
EXISTING parameter of the macro currently being edited, or create a new
one, to bind to one internal block's property. Modeled directly on
ui/signal_picker.py's SignalPickerDialog + its own "Nowy sygnał
wewnętrzny..." sub-dialog (_NewInternalSignalDialog) — same shape, same
reasoning: don't force the engineer out of this dialog to define
something new first.

Qt-thin like every other dialog here: never mutates the definition
itself — property_grid.py's own _open_bind_parameter_dialog() does the
actual add_parameter()/add_parameter_binding() calls (push_state()/
set_dirty()/resync side effects live there, not here), consuming
result_parameter_name()'s return.
"""
import re

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QLineEdit, QPushButton, QDialogButtonBox, QFormLayout, QMessageBox, QLabel,
)
from PySide6.QtCore import Qt

PARAM_NAME_ROLE = Qt.UserRole

# Same shape as property_grid.py's own _split_unit() — duplicated rather
# than imported across the ui/panels boundary (that function is private
# to that module), same reasoning compiler/validator.py's own
# _direct_source_block() duplicates compiler/core.py's copy.
_UNIT_SUFFIX_RE = re.compile(r'^(.*) \(([^)]+)\)$')


def _split_property_unit(key: str):
    m = _UNIT_SUFFIX_RE.match(key)
    return (m.group(1), m.group(2)) if m else (key, "")


def infer_param_type(value) -> str:
    """§C2.2: a new parameter's type is INFERRED from the bound
    property's own current value, never picked by hand — a numeric
    property becomes an INT/REAL parameter, a boolean one a BOOL, so a
    parameter can never mismatch the property it was created FROM."""
    if isinstance(value, bool):
        return "BOOL"
    if isinstance(value, int):
        return "INT"
    if isinstance(value, float):
        return "REAL"
    return "STRING"


class _NewMacroParameterDialog(QDialog):
    def __init__(self, property_name: str, current_value, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Nowy parametr makrobloku")
        self.entry = None

        base_name, unit = _split_property_unit(property_name)
        self._param_type = infer_param_type(current_value)
        self._default_value = current_value

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.display_name_edit = QLineEdit(base_name)
        type_label = QLabel(self._param_type)
        self.unit_edit = QLineEdit(unit)
        self.description_edit = QLineEdit()
        form.addRow("Nazwa", self.display_name_edit)
        form.addRow("Typ (z właściwości)", type_label)
        form.addRow("Jednostka", self.unit_edit)
        form.addRow("Opis", self.description_edit)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_accept(self):
        name = self.display_name_edit.text().strip()
        if not name:
            QMessageBox.critical(self, "Nieprawidłowa nazwa", "Nazwa parametru nie może być pusta.")
            return
        self.entry = {
            "display_name": name,
            "type": self._param_type,
            "default": self._default_value,
            "unit": self.unit_edit.text().strip(),
            "description": self.description_edit.text().strip(),
        }
        self.accept()


class BindParameterDialog(QDialog):
    def __init__(self, definition: dict, property_name: str, current_value, parent=None):
        super().__init__(parent)
        self.definition = definition
        self.property_name = property_name
        self.current_value = current_value
        self._chosen_existing_name = None
        self._new_entry = None
        self.setWindowTitle("Powiąż z parametrem")
        self.resize(360, 320)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Właściwość: {property_name}"))

        self.list = QListWidget()
        for param in definition.get("parameters", []):
            item = QListWidgetItem(f"{param.get('display_name')} ({param.get('type')})")
            item.setData(PARAM_NAME_ROLE, param.get("name"))
            self.list.addItem(item)
        self.list.itemSelectionChanged.connect(self._update_ok_enabled)
        layout.addWidget(self.list)

        new_row = QHBoxLayout()
        self.new_param_btn = QPushButton("Nowy parametr...")
        self.new_param_btn.clicked.connect(self._create_new_parameter)
        new_row.addWidget(self.new_param_btn)
        new_row.addStretch()
        layout.addLayout(new_row)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.ok_button = buttons.button(QDialogButtonBox.Ok)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._update_ok_enabled()

    def _update_ok_enabled(self):
        self.ok_button.setEnabled(bool(self.list.selectedItems()) or self._new_entry is not None)

    def _create_new_parameter(self):
        sub = _NewMacroParameterDialog(self.property_name, self.current_value, parent=self)
        if sub.exec() != QDialog.DialogCode.Accepted or sub.entry is None:
            return
        self._new_entry = sub.entry
        self.list.clearSelection()
        self._update_ok_enabled()
        self.accept()

    def result_parameter_name(self, project, def_id) -> str:
        """The parameter `name` to bind — an existing one picked from the
        list, or a freshly created one (this is the one place that
        actually calls add_parameter(), right when the dialog's own
        result is being consumed). None if nothing was ever chosen."""
        if self._new_entry is not None:
            from logic_studio.core.macros import add_parameter
            return add_parameter(
                project, def_id,
                self._new_entry["display_name"], self._new_entry["type"], self._new_entry["default"],
                unit=self._new_entry["unit"], description=self._new_entry["description"],
            )
        items = self.list.selectedItems()
        if not items:
            return None
        return items[0].data(PARAM_NAME_ROLE)
