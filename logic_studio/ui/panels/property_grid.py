from PySide6.QtWidgets import QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView, QComboBox
from PySide6.QtCore import Qt
from logic_studio.core.device_model import DeviceModel

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


    def _on_combo_changed(self, key, text):
        if not self.current_block:
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

    def load_block_properties(self, block):
        """Loads properties from a BaseLogicBlock instance."""
        self.table.blockSignals(True) # Prevent triggering itemChanged during load
        self.current_block = block
        self.table.setRowCount(0)

        # Common properties defined in SRS
        props = {
            "Name": block.display_name,
            "Description": block.description,
            "UUID": block.uuid,
            "Category": block.category,
            "Priority": str(block.execution_priority),
            "Enabled": str(block.enabled),
            "Visible": str(block.visibility),
            "Execution State": block.execution_state
        }

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
            elif key == "Force State":
                combo = QComboBox()
                combo.addItems(["NO FORCE", "FORCE FALSE", "FORCE TRUE"])
                combo.setCurrentText(str(value))
                combo.currentTextChanged.connect(lambda text, k=key: self._on_combo_changed(k, text))
                self.table.setCellWidget(row, 1, combo)
            else:
                self.table.setItem(row, 1, val_item)

        self.table.blockSignals(False)
