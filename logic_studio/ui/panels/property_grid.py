from PySide6.QtWidgets import QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView, QComboBox, QPushButton
from PySide6.QtCore import Qt
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

class PropertyGridPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Property", "Value"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(False)
        self.table.setStyleSheet("""
            QTableWidget {
                gridline-color: #C0C0C0;
                background-color: #FFFFFF;
                selection-background-color: #000080;
                selection-color: #FFFFFF;
            }
            QTableWidget::item {
                border-bottom: 1px solid #C0C0C0;
            }
        """)

        layout.addWidget(self.table)

        # Initialize with empty selection message or defaults
        self._set_empty_state()
        self.current_block = None

        self.table.itemChanged.connect(self._on_item_changed)

    def _on_item_changed(self, item):
        if not self.current_block:
            return

        row = item.row()
        key_item = self.table.item(row, 0)

        if key_item and item.column() == 1:
            key = key_item.text()
            val = item.text()

            # Hook into MainWindow to mark dirty / push state
            window = self.window()
            if hasattr(window, 'project'):
                window.project.push_state()
                window.set_dirty()

            self.current_block.update_property(key, val)

            # Request visual repaint
            if hasattr(window, 'scene'):
                window.scene.update()


    def _open_signal_picker(self, key, button):
        """feat/internal-bits §6.1/§6.7: opens SignalPickerDialog for the
        given property; on accept, sets the property, pushes undo state,
        marks dirty, repaints the canvas — exactly the same side effects
        _on_item_changed()/_on_combo_changed() already have for every other
        property, just triggered from a button instead of an edited cell."""
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

    def _on_combo_changed(self, key, text):
        if not self.current_block:
            return

        if key == "Force State":
            # Runtime-only override (AUDIT_REPORT.md §5.1): lives in simulation_state,
            # never in properties, so it can never be saved to a project file or ride
            # along into an exported runtime. Not an undoable edit either.
            self.current_block.simulation_state["force_state"] = text
            window = self.window()
            if hasattr(window, 'scene'):
                window.scene.update()
            return

        window = self.window()
        if hasattr(window, 'project'):
            window.project.push_state()
            window.set_dirty()

        self.current_block.update_property(key, text)

        if hasattr(window, 'scene'):
            window.scene.update()

    def _set_empty_state(self):
        self.table.setRowCount(1)
        item = QTableWidgetItem("No object selected")
        item.setFlags(Qt.ItemIsEnabled)
        self.table.setItem(0, 0, item)
        self.table.setItem(0, 1, QTableWidgetItem(""))

    def load_block_properties(self, block, project=None):
        """Loads properties from a BaseLogicBlock instance. `project` is only
        needed for input.ai/output.ao's Address combobox, whose choices come
        from the project's dynamic analog_points list rather than a fixed
        DeviceModel channel list (AUDIT_REPORT.md §2.4)."""
        self.table.blockSignals(True) # Prevent triggering itemChanged during load
        self.current_block = block
        self.current_project = project
        self.table.setRowCount(0)

        # Tag/Comment first — the first two fields an engineer fills in
        # after placing a block (feat/block-rendering-library §3.3).
        props = {
            "Tag": block.properties.get("Tag", ""),
            "Comment": block.properties.get("Comment", ""),
        }

        # Common properties defined in SRS
        props.update({
            "Name": block.display_name,
            "Description": block.description,
            "UUID": block.uuid,
            "Category": block.category,
            "Priority": str(block.execution_priority),
            "Enabled": str(block.enabled),
            "Visible": str(block.visibility),
            "Execution State": block.execution_state
        })

        # Force is runtime-only (AUDIT_REPORT.md §5.1): it lives in simulation_state,
        # not in properties, so surface it here explicitly for forceable block types.
        if block.type_id in ["input.di", "virtual.input"]:
            props["Force State"] = block.simulation_state.get("force_state", "NO FORCE")

        # Add dynamic properties
        props.update(block.properties)

        self.table.setRowCount(len(props))
        for row, (key, value) in enumerate(props.items()):

            key_item = QTableWidgetItem(key)
            key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            # Make property names stand out slightly
            from PySide6.QtGui import QColor
            key_item.setBackground(QColor(240, 240, 240))

            val_item = QTableWidgetItem(str(value))

            # If property is read-only in this Phase
            if key in ["UUID", "Category", "Execution State", "Enabled", "Visible"]:
                val_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            else:
                # Fully editable for "Address", "Name", "Description", "Comment", "Preset" etc
                val_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)

            self.table.setItem(row, 0, key_item)

            # Custom Comboboxes for Address and Force State
            if key == "Address" and block.type_id in ["input.di", "output.do"]:
                combo = QComboBox()
                if block.type_id == "input.di":
                    combo.addItems(DeviceModel.get_ela_addresses())
                else:
                    combo.addItems(DeviceModel.get_ada_addresses())
                combo.setCurrentText(str(value))
                combo.currentTextChanged.connect(lambda text, k=key: self._on_combo_changed(k, text))
                self.table.setCellWidget(row, 1, combo)
            elif key == "Address" and block.type_id in ["input.ai", "output.ao"] and project is not None:
                combo = QComboBox()
                if block.type_id == "input.ai":
                    combo.addItems(DeviceModel.get_analog_input_addresses(project))
                else:
                    combo.addItems(DeviceModel.get_analog_output_addresses(project))
                combo.setCurrentText(str(value))
                combo.currentTextChanged.connect(lambda text, k=key: self._on_combo_changed(k, text))
                self.table.setCellWidget(row, 1, combo)
            elif key == "Force State":
                combo = QComboBox()
                combo.addItems(["NO FORCE", "FORCE FALSE", "FORCE TRUE"])
                combo.setCurrentText(str(value))
                combo.currentTextChanged.connect(lambda text, k=key: self._on_combo_changed(k, text))
                self.table.setCellWidget(row, 1, combo)
            elif (block.type_id, key) in _SIGNAL_PICKER_TARGETS:
                # feat/internal-bits §6.1: SignalPickerDialog, not a plain
                # text field — a "Bit"/"Sygnał" typo used to silently
                # create a new signal (or, for system.signal, collide with
                # a physical DI address); picking from a validated list
                # makes that impossible.
                btn = QPushButton(str(value) or "(nie wybrano)")
                btn.clicked.connect(lambda checked=False, k=key, b=btn: self._open_signal_picker(k, b))
                self.table.setCellWidget(row, 1, btn)
            else:
                self.table.setItem(row, 1, val_item)

        self.table.blockSignals(False)
