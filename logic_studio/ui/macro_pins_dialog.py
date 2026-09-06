"""feat/macro-editable-pins — MacroPinsDialog: lets the engineer REMOVE an
exposed input/output pin from the macro currently being edited (breadcrumb
view). Adding a pin happens elsewhere — BlockItem's own context menu, on
whichever internal block's pin is being exposed (see
BlockItem.populate_expose_pin_menu()) — this dialog only ever removes,
since a removal has no natural "which block on the canvas" anchor the way
an addition does.

Qt-thin, like every other panel/dialog here: never touches core/macros.py
itself. Every actual mutation is delegated to the `on_remove` callback
MainWindow supplies, which does the real remove_boundary_pin()/
resync_all_instances() work and hands back the refreshed definition —
this dialog just renders whatever it's given and reports which row was
removed, mirroring core/crossref.py vs. ui/panels/signals.py's own split.
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QDialogButtonBox,
)
from PySide6.QtCore import Qt

from logic_studio.blocks.pin import Pin

INDEX_ROLE = Qt.UserRole


class MacroPinsDialog(QDialog):
    def __init__(self, definition: dict, on_remove, parent=None):
        """`definition`: the macro's CURRENT definition dict — read-only,
        this dialog never mutates it directly. `on_remove(direction,
        index)` is called when the engineer removes a row; it must
        perform the actual removal+resync (MainWindow._remove_macro_pin())
        and return the FRESH definition dict on success, or None if
        nothing changed (index went stale, definition was deleted, ...) —
        this dialog only calls refresh() on a non-None result."""
        super().__init__(parent)
        self._on_remove = on_remove
        self.setWindowTitle("Piny makrobloku")
        self.resize(420, 360)

        layout = QVBoxLayout(self)

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

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.accept)
        layout.addWidget(buttons)

        self.refresh(definition)

    def refresh(self, definition: dict):
        """Repopulates both lists from `definition`'s current
        input_pins/output_pins — called once at construction and again
        after every successful removal, so the dialog stays in sync
        without needing to be closed and reopened."""
        self.input_list.clear()
        for i, entry in enumerate(definition.get("input_pins", [])):
            self._add_row(self.input_list, i, entry)
        self.output_list.clear()
        for i, entry in enumerate(definition.get("output_pins", [])):
            self._add_row(self.output_list, i, entry)

    @staticmethod
    def _add_row(list_widget, index, entry):
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
