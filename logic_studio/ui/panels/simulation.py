from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QGridLayout, QCheckBox, QLabel, QGroupBox, QScrollArea,
    QSlider, QDoubleSpinBox, QHBoxLayout, QPushButton, QLineEdit
)
from PySide6.QtCore import Qt, Signal

# feat/editor-modes-and-geometry §4: approximate on-screen width (px) of one
# DI/DO checkbox/tag cell, incl. its label and grid spacing — used to decide
# how many columns actually FIT at the panel's current width, instead of the
# fixed 4 the ELA/ADA grids used to hard-code. At the panel's typical docked
# width that hardcoded 4 was really only wide enough for ~2, so DI03/DI04/
# DI07/DI08/... (and the equivalent ADA channels) were laid out into columns
# squeezed off past what QScrollArea (setWidgetResizable=True, so no
# horizontal scrollbar is offered at all) could ever show — silently
# unreachable, no visible indication anything was missing.
ELA_ADA_COLUMN_WIDTH = 60


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
        self._ela_columns = None
        self._ada_columns = None

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

        # §4: 32 DI + 32 DO channels are faster to search than to scroll for
        # — filters both ELA_Inputs and ADA_Outputs by address substring.
        self.io_filter = QLineEdit()
        self.io_filter.setPlaceholderText("Filtruj DI/DO (np. DI03, DO01)…")
        self.io_filter.textChanged.connect(self._apply_io_filter)
        layout.addWidget(self.io_filter)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        content = QWidget()
        self.grid = QGridLayout(content)

        from logic_studio.core.device_model import DeviceModel

        # ELA Inputs (Checkboxes) — fixed physical channels, project-independent.
        in_group = QGroupBox("ELA Inputs (DI)")
        self.in_layout = QGridLayout(in_group)
        self.ela_boxes = []
        for addr in DeviceModel.get_ela_addresses():
            cb = QCheckBox(addr)
            self.ela_boxes.append(cb)
        self.grid.addWidget(in_group, 0, 0)

        # ADA Outputs (LEDs mocked as text/color labels)
        out_group = QGroupBox("ADA Outputs (DO)")
        self.out_layout = QGridLayout(out_group)
        self.ada_leds = []
        for addr in DeviceModel.get_ada_addresses():
            lbl = QLabel(addr)
            lbl.setStyleSheet("background-color: darkgray; color: white; padding: 2px; border: 1px solid black;")
            lbl.setAlignment(Qt.AlignCenter)
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

        # Initial layout — a real column count is computed as soon as this
        # widget is actually shown/resized (resizeEvent below); this seeds a
        # sane starting arrangement so the grids aren't empty before then.
        self._recompute_ela_ada_columns()

        self.set_project(project)

    # ---- Dynamic ELA/ADA column layout (§4) --------------------------------

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._recompute_ela_ada_columns()

    def _recompute_ela_ada_columns(self):
        """Recomputes how many columns actually fit the panel's CURRENT
        width and relays out both the ELA and ADA grids if that count
        changed — called on every resize, not just once at construction, so
        docking/undocking or dragging the panel wider/narrower keeps every
        channel reachable instead of freezing whatever fit at startup."""
        available = max(self.width(), ELA_ADA_COLUMN_WIDTH)
        columns = max(1, available // ELA_ADA_COLUMN_WIDTH)

        if columns != self._ela_columns:
            self._ela_columns = columns
            self._relayout_grid(self.in_layout, self.ela_boxes, columns)

        if columns != self._ada_columns:
            self._ada_columns = columns
            self._relayout_grid(self.out_layout, self.ada_leds, columns)

    @staticmethod
    def _relayout_grid(grid_layout, widgets, columns):
        """Re-places every widget in `widgets` into `grid_layout` at the
        given column count, without deleting any of them — takeAt() detaches
        an item from the layout but the widget itself survives untouched, so
        every channel stays present (just repositioned) across a resize."""
        while grid_layout.count():
            grid_layout.takeAt(0)
        for i, w in enumerate(widgets):
            grid_layout.addWidget(w, i // columns, i % columns)

    def _apply_io_filter(self, text):
        text = text.strip().lower()
        for cb in self.ela_boxes:
            cb.setVisible(not text or text in cb.text().lower())
        for lbl in self.ada_leds:
            lbl.setVisible(not text or text in lbl.text().lower())

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
