from PySide6.QtWidgets import QWidget, QVBoxLayout, QGridLayout, QCheckBox, QLabel, QGroupBox, QScrollArea
from PySide6.QtCore import Qt

class SimulationPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        self.grid = QGridLayout(content)

        from logic_studio.core.device_model import DeviceModel

        # ELA Inputs (Checkboxes)
        in_group = QGroupBox("ELA Inputs (DI)")
        in_layout = QGridLayout(in_group)
        self.ela_boxes = []

        ela_addrs = DeviceModel.get_ela_addresses()
        for i, addr in enumerate(ela_addrs):
            cb = QCheckBox(addr)
            # Layout in 4 columns
            row = i // 4
            col = i % 4
            in_layout.addWidget(cb, row, col)
            self.ela_boxes.append(cb)

        self.grid.addWidget(in_group, 0, 0)

        # ADA Outputs (LEDs mocked as text/color labels for now)
        out_group = QGroupBox("ADA Outputs (DO)")
        out_layout = QGridLayout(out_group)
        self.ada_leds = []

        ada_addrs = DeviceModel.get_ada_addresses()
        for i, addr in enumerate(ada_addrs):
            lbl = QLabel(addr)
            lbl.setStyleSheet("background-color: darkgray; color: white; padding: 2px; border: 1px solid black;")
            lbl.setAlignment(Qt.AlignCenter)

            row = i // 4
            col = i % 4
            out_layout.addWidget(lbl, row, col)
            self.ada_leds.append(lbl)

        self.grid.addWidget(out_group, 1, 0)

        scroll.setWidget(content)
        layout.addWidget(scroll)

    def set_ada_state(self, index: int, state: bool):
        """Update ADA output LED state. Index is 0-31."""
        if 0 <= index < 32:
            color = "green" if state else "darkgray"
            self.ada_leds[index].setStyleSheet(f"background-color: {color}; color: white; padding: 2px; border: 1px solid black;")

    def get_ela_state(self, index: int) -> bool:
        """Get ELA input checkbox state. Index is 0-31."""
        if 0 <= index < 32:
            return self.ela_boxes[index].isChecked()
        return False
