"""feat/macro-editable-pins — MacroPinsDialog: lets the engineer REMOVE an
exposed input/output pin from the macro currently being edited (breadcrumb
view). Adding a pin happens elsewhere — BlockItem's own context menu, on
whichever internal block's pin is being exposed (see
BlockItem.populate_expose_pin_menu()) — this dialog only ever removes,
since a removal has no natural "which block on the canvas" anchor the way
an addition does.

fix/safety-and-macro-params §C2.4: a second tab, "Parametry" — lists the
macro's own declared parameters (Nazwa/Typ/Domyślna/Jednostka/Powiązań),
with add/remove/reorder. A parameter's own BINDING to an internal block's
property is created from the property panel instead (§C2.1,
ui/macro_parameter_dialog.py's BindParameterDialog) — same "an addition
has a natural anchor elsewhere, a removal/listing doesn't" split as the
pins tab already makes.

Qt-thin, like every other panel/dialog here: never touches core/macros.py
itself. Every actual mutation is delegated to callbacks MainWindow
supplies, which do the real core/macros.py + resync work and hand back
the refreshed definition — this dialog just renders whatever it's given,
mirroring core/crossref.py vs. ui/panels/signals.py's own split.
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QDialogButtonBox, QTabWidget, QWidget, QTableWidget,
    QTableWidgetItem, QMessageBox, QLineEdit, QComboBox, QFormLayout,
)
from PySide6.QtCore import Qt

from logic_studio.blocks.pin import Pin
from logic_studio.core.macros import PARAM_TYPES

INDEX_ROLE = Qt.UserRole
PARAM_NAME_ROLE = Qt.UserRole
_COLUMNS = ("Nazwa", "Typ", "Domyślna", "Jednostka", "Powiązań")


class _NewParameterDialog(QDialog):
    """§C2.4's own "Nowy parametr" — unlike ui/macro_parameter_dialog.py's
    _NewMacroParameterDialog (created FROM a specific property, type
    inferred from its value), this one starts from nothing: the engineer
    picks the type by hand."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Nowy parametr")
        self.entry = None

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.display_name_edit = QLineEdit()
        self.type_combo = QComboBox()
        self.type_combo.addItems(PARAM_TYPES)
        self.default_edit = QLineEdit("0")
        self.unit_edit = QLineEdit()
        self.description_edit = QLineEdit()
        form.addRow("Nazwa", self.display_name_edit)
        form.addRow("Typ", self.type_combo)
        form.addRow("Domyślna", self.default_edit)
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
        param_type = self.type_combo.currentText()
        raw = self.default_edit.text().strip()
        try:
            if param_type == "INT":
                default = int(raw)
            elif param_type == "REAL":
                default = float(raw)
            elif param_type == "BOOL":
                default = raw.lower() in ("true", "1", "t", "yes", "y")
            else:
                default = raw
        except ValueError:
            QMessageBox.critical(self, "Nieprawidłowa wartość", f"'{raw}' nie jest poprawną wartością typu {param_type}.")
            return
        self.entry = {
            "display_name": name, "type": param_type, "default": default,
            "unit": self.unit_edit.text().strip(), "description": self.description_edit.text().strip(),
        }
        self.accept()


class MacroPinsDialog(QDialog):
    def __init__(self, definition: dict, on_remove, parent=None, on_parameter_change=None):
        """`definition`: the macro's CURRENT definition dict — read-only,
        this dialog never mutates it directly. `on_remove(direction,
        index)` is called when the engineer removes a pin row; it must
        perform the actual removal+resync (MainWindow._remove_macro_pin())
        and return the FRESH definition dict on success, or None if
        nothing changed. `on_parameter_change(action, **kwargs)` is the
        single dispatcher for every parameter-tab mutation — `action` is
        one of "add"/"remove"/"reorder" (kwargs matching core/macros.py's
        own add_parameter()/remove_parameter()/reorder_parameters()
        signatures), returning the fresh definition on success or None on
        failure (a duplicate reorder set, a stale index, ...). Optional —
        a dialog opened for a definition-less context (shouldn't happen
        in practice) simply hides the Parametry tab's own actions."""
        super().__init__(parent)
        self._on_remove = on_remove
        self._on_parameter_change = on_parameter_change
        self.setWindowTitle("Piny i parametry makrobloku")
        self.resize(520, 420)

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self.tabs.addTab(self._build_pins_tab(), "Piny")
        self.tabs.addTab(self._build_parameters_tab(), "Parametry")

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.accept)
        layout.addWidget(buttons)

        self.refresh(definition)

    # ---- "Piny" tab (unchanged from feat/macro-editable-pins) --------------

    def _build_pins_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        columns = QHBoxLayout()
        layout.addLayout(columns)

        input_col = QVBoxLayout()
        input_col.addWidget(QLabel("Wejścia"))
        self.input_list = QListWidget()
        input_col.addWidget(self.input_list)
        self.remove_input_btn = QPushButton("Usuń zaznaczone")
        self.remove_input_btn.clicked.connect(lambda: self._remove_selected(self.input_list, Pin.DIR_INPUT))
        input_col.addWidget(self.remove_input_btn)
        columns.addLayout(input_col)

        output_col = QVBoxLayout()
        output_col.addWidget(QLabel("Wyjścia"))
        self.output_list = QListWidget()
        output_col.addWidget(self.output_list)
        self.remove_output_btn = QPushButton("Usuń zaznaczone")
        self.remove_output_btn.clicked.connect(lambda: self._remove_selected(self.output_list, Pin.DIR_OUTPUT))
        output_col.addWidget(self.remove_output_btn)
        columns.addLayout(output_col)

        hint = QLabel(
            "Aby dodać nowy pin, kliknij prawym przyciskiem na blok "
            "wewnątrz makrobloku i wybierz „Wystaw pin makrobloku”."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        return tab

    # ---- "Parametry" tab (§C2.4) --------------------------------------------

    def _build_parameters_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.param_table = QTableWidget(0, len(_COLUMNS))
        self.param_table.setHorizontalHeaderLabels(_COLUMNS)
        self.param_table.setSelectionBehavior(self.param_table.SelectionBehavior.SelectRows)
        self.param_table.setEditTriggers(self.param_table.EditTrigger.NoEditTriggers)
        layout.addWidget(self.param_table)

        row = QHBoxLayout()
        self.add_param_btn = QPushButton("Nowy parametr...")
        self.add_param_btn.clicked.connect(self._add_parameter)
        row.addWidget(self.add_param_btn)
        self.remove_param_btn = QPushButton("Usuń zaznaczony")
        self.remove_param_btn.clicked.connect(self._remove_selected_parameter)
        row.addWidget(self.remove_param_btn)
        self.move_up_btn = QPushButton("W górę")
        self.move_up_btn.clicked.connect(lambda: self._move_parameter(-1))
        row.addWidget(self.move_up_btn)
        self.move_down_btn = QPushButton("W dół")
        self.move_down_btn.clicked.connect(lambda: self._move_parameter(1))
        row.addWidget(self.move_down_btn)
        row.addStretch()
        layout.addLayout(row)

        hint = QLabel(
            "Aby powiązać parametr z właściwością bloku, otwórz panel "
            "właściwości tego bloku wewnątrz makrobloku i użyj przycisku "
            "„Powiąż z parametrem...” przy wybranej właściwości."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        return tab

    def refresh(self, definition: dict):
        """Repopulates every tab from `definition`'s current state —
        called once at construction and again after every successful
        mutation, so the dialog stays in sync without needing to be
        closed and reopened."""
        self._definition = definition
        self.input_list.clear()
        for i, entry in enumerate(definition.get("input_pins", [])):
            self._add_pin_row(self.input_list, i, entry)
        self.output_list.clear()
        for i, entry in enumerate(definition.get("output_pins", [])):
            self._add_pin_row(self.output_list, i, entry)
        self._refresh_parameters_table(definition)

    def _refresh_parameters_table(self, definition: dict):
        params = definition.get("parameters", [])
        bindings = definition.get("parameter_bindings", [])
        binding_counts = {}
        for b in bindings:
            binding_counts[b.get("parameter")] = binding_counts.get(b.get("parameter"), 0) + 1

        self.param_table.setRowCount(len(params))
        for row, param in enumerate(params):
            values = (
                param.get("display_name", ""), param.get("type", ""),
                str(param.get("default", "")), param.get("unit", ""),
                str(binding_counts.get(param.get("name"), 0)),
            )
            for col, text in enumerate(values):
                item = QTableWidgetItem(text)
                if col == 0:
                    item.setData(PARAM_NAME_ROLE, param.get("name"))
                self.param_table.setItem(row, col, item)

    @staticmethod
    def _add_pin_row(list_widget, index, entry):
        label = entry.get("label", entry.get("pin_name", ""))
        item = QListWidgetItem(label)
        item.setData(INDEX_ROLE, index)
        list_widget.addItem(item)

    def _remove_selected(self, list_widget, direction):
        item = list_widget.currentItem()
        if item is None:
            return
        index = item.data(INDEX_ROLE)
        new_definition = self._on_remove(direction, index)
        if new_definition is not None:
            self.refresh(new_definition)

    # ---- Parameter actions ---------------------------------------------------

    def _selected_param_name(self):
        items = self.param_table.selectedItems()
        if not items:
            return None
        return self.param_table.item(items[0].row(), 0).data(PARAM_NAME_ROLE)

    def _add_parameter(self):
        if self._on_parameter_change is None:
            return
        sub = _NewParameterDialog(parent=self)
        if sub.exec() != QDialog.DialogCode.Accepted or sub.entry is None:
            return
        new_definition = self._on_parameter_change("add", **sub.entry)
        if new_definition is not None:
            self.refresh(new_definition)

    def _remove_selected_parameter(self):
        if self._on_parameter_change is None:
            return
        param_name = self._selected_param_name()
        if param_name is None:
            return
        param = next((p for p in self._definition.get("parameters", []) if p.get("name") == param_name), None)
        bindings = [b for b in self._definition.get("parameter_bindings", []) if b.get("parameter") == param_name]
        if bindings:
            ref_list = "\n".join(f"- {b.get('property_name')}" for b in bindings)
            reply = QMessageBox.question(
                self, "Usunąć parametr?",
                f"Parametr '{param.get('display_name') if param else param_name}' jest powiązany z "
                f"{len(bindings)} właściwościami:\n{ref_list}\n\nUsunięcie skasuje też te powiązania. Kontynuować?",
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        new_definition = self._on_parameter_change("remove", param_name=param_name)
        if new_definition is not None:
            self.refresh(new_definition)

    def _move_parameter(self, delta: int):
        if self._on_parameter_change is None:
            return
        param_name = self._selected_param_name()
        if param_name is None:
            return
        names = [p.get("name") for p in self._definition.get("parameters", [])]
        i = names.index(param_name)
        j = i + delta
        if j < 0 or j >= len(names):
            return
        names[i], names[j] = names[j], names[i]
        new_definition = self._on_parameter_change("reorder", new_order=names)
        if new_definition is not None:
            self.refresh(new_definition)
            self.param_table.selectRow(j)
