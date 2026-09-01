from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QGridLayout, QCheckBox, QLabel, QGroupBox, QScrollArea,
    QSlider, QDoubleSpinBox, QHBoxLayout, QPushButton
)
from PySide6.QtCore import Qt, Signal

class SimulationPanel(QWidget):
    """DI/DO force panel (fixed, hardware-backed) plus the project's dynamic
    analog points (AUDIT_REPORT.md §6) and manual step controls."""

    # Emitted when the user asks to single-/multi-step the engine manually.
    # MainWindow owns the engine, so it performs the actual step(s) and the
    # canvas/status-bar refresh — see AUDIT_REPORT.md §6.3.
    step_requested = Signal(int)

    def __init__(self, project=None, parent=None):
        super().__init__(parent)
        self.project = project
        self.ai_spinboxes = {}   # address -> QDoubleSpinBox
        self.ai_sliders = {}     # address -> QSlider
        self.ao_labels = {}      # address -> QLabel

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        step_row = QHBoxLayout()
        self.step_btn = QPushButton("Krok")
        self.step10_btn = QPushButton("Krok ×10")
        step_tip = (
            "Wykonuje ręczny skan silnika. Dostępne tylko w stanie PAUSED albo "
            "STOPPED z załadowanym programem. Przy SystemTimeProvider krokowanie "
            "ma sens tylko w pauzie — w trybie ciągłym zegar biegnie dalej "
            "niezależnie od ręcznego kroku."
        )
        self.step_btn.setToolTip(step_tip)
        self.step10_btn.setToolTip(step_tip)
        self.step_btn.clicked.connect(lambda: self.step_requested.emit(1))
        self.step10_btn.clicked.connect(lambda: self.step_requested.emit(10))
        self.set_step_buttons_enabled(False)
        step_row.addWidget(self.step_btn)
        step_row.addWidget(self.step10_btn)
        step_row.addStretch()
        layout.addLayout(step_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        self.grid = QGridLayout(content)

        from logic_studio.core.device_model import DeviceModel

        # ELA Inputs (Checkboxes) — fixed physical channels, project-independent.
        in_group = QGroupBox("ELA Inputs (DI)")
        in_layout = QGridLayout(in_group)
        self.ela_boxes = []
        for i, addr in enumerate(DeviceModel.get_ela_addresses()):
            cb = QCheckBox(addr)
            in_layout.addWidget(cb, i // 4, i % 4)
            self.ela_boxes.append(cb)
        self.grid.addWidget(in_group, 0, 0)

        # ADA Outputs (LEDs mocked as text/color labels)
        out_group = QGroupBox("ADA Outputs (DO)")
        out_layout = QGridLayout(out_group)
        self.ada_leds = []
        for i, addr in enumerate(DeviceModel.get_ada_addresses()):
            lbl = QLabel(addr)
            lbl.setStyleSheet("background-color: darkgray; color: white; padding: 2px; border: 1px solid black;")
            lbl.setAlignment(Qt.AlignCenter)
            out_layout.addWidget(lbl, i // 4, i % 4)
            self.ada_leds.append(lbl)
        self.grid.addWidget(out_group, 1, 0)

        # Analog Inputs / Outputs — fully project-defined, rebuilt in set_project().
        self.ai_group = QGroupBox("Wejścia analogowe")
        self.ai_layout = QGridLayout(self.ai_group)
        self.grid.addWidget(self.ai_group, 2, 0)

        self.ao_group = QGroupBox("Wyjścia analogowe")
        self.ao_layout = QGridLayout(self.ao_group)
        self.grid.addWidget(self.ao_group, 3, 0)

        scroll.setWidget(content)
        layout.addWidget(scroll)

        self.set_project(project)

    def set_project(self, project):
        """Rebuild the analog sections for a (possibly new) project's
        analog_points. Call whenever the project or its analog point list
        changes (new/open/undo/redo, Project Settings dialog)."""
        self.project = project

        self._clear_layout(self.ai_layout)
        self._clear_layout(self.ao_layout)
        self.ai_spinboxes.clear()
        self.ai_sliders.clear()
        self.ao_labels.clear()

        if project is None:
            return

        from logic_studio.core.device_model import DeviceModel
        points = DeviceModel.get_analog_points(project)

        row = 0
        for point in points:
            if point.get("direction") != "input":
                continue
            addr = point.get("address", "")
            unit = point.get("unit", "")
            name = point.get("name", addr) or addr
            min_v = float(point.get("min", 0.0))
            max_v = float(point.get("max", 100.0))
            span = (max_v - min_v) or 1.0

            label_text = f"{name} [{unit}]" if unit else name
            self.ai_layout.addWidget(QLabel(label_text), row, 0)

            slider = QSlider(Qt.Horizontal)
            slider.setRange(0, 1000)  # scaled 0..1000 across [min, max]

            spin = QDoubleSpinBox()
            spin.setRange(min_v, max_v)
            spin.setDecimals(2)
            spin.setValue(min_v)

            def slider_to_value(v, min_v=min_v, span=span):
                return min_v + (v / 1000.0) * span

            def value_to_slider(v, min_v=min_v, span=span):
                return int(round((v - min_v) / span * 1000))

            def on_slider_changed(v, spin=spin, f=slider_to_value):
                # blockSignals so this doesn't bounce back through spin's own
                # valueChanged and re-quantize the value onto the slider's
                # coarser 1000-step resolution.
                spin.blockSignals(True)
                spin.setValue(f(v))
                spin.blockSignals(False)

            def on_spin_changed(v, slider=slider, f=value_to_slider):
                slider.blockSignals(True)
                slider.setValue(f(v))
                slider.blockSignals(False)

            slider.valueChanged.connect(on_slider_changed)
            spin.valueChanged.connect(on_spin_changed)

            self.ai_layout.addWidget(slider, row, 1)
            self.ai_layout.addWidget(spin, row, 2)

            self.ai_spinboxes[addr] = spin
            self.ai_sliders[addr] = slider
            row += 1

        row = 0
        for point in points:
            if point.get("direction") != "output":
                continue
            addr = point.get("address", "")
            unit = point.get("unit", "")
            name = point.get("name", addr) or addr

            label_text = f"{name} [{unit}]" if unit else name
            self.ao_layout.addWidget(QLabel(label_text), row, 0)

            value_lbl = QLabel("-")
            value_lbl.setStyleSheet("background-color: white; padding: 2px; border: 1px solid black;")
            self.ao_layout.addWidget(value_lbl, row, 1)
            self.ao_labels[addr] = value_lbl
            row += 1

    @staticmethod
    def _clear_layout(layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def set_ada_state(self, index: int, state: bool):
        """Update ADA output LED state. Index is 0-31."""
        if 0 <= index < len(self.ada_leds):
            color = "green" if state else "darkgray"
            self.ada_leds[index].setStyleSheet(f"background-color: {color}; color: white; padding: 2px; border: 1px solid black;")

    def get_ela_state(self, index: int) -> bool:
        """Get ELA input checkbox state. Index is 0-31."""
        if 0 <= index < len(self.ela_boxes):
            return self.ela_boxes[index].isChecked()
        return False

    def get_analog_input_value(self, address: str) -> float:
        spin = self.ai_spinboxes.get(address)
        return spin.value() if spin else 0.0

    def set_analog_output_value(self, address: str, value):
        lbl = self.ao_labels.get(address)
        if lbl is None:
            return
        try:
            lbl.setText(f"{float(value):.2f}")
        except (TypeError, ValueError):
            lbl.setText(str(value))

    def set_step_buttons_enabled(self, enabled: bool):
        self.step_btn.setEnabled(enabled)
        self.step10_btn.setEnabled(enabled)
