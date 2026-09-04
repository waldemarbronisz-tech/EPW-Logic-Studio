"""Simulation panel — the test bench for a project with no real hardware
behind it (feat/wire-modes-and-labels §0A.0). There's no rack, no physical
terminals, no voltage on any clamp: the engine only knows what an ENGINEER
tells it is present on each input, via THIS panel. MainWindow copies its DI/
AI state into io_provider every scan; the logic blocks (DigitalInputBlock,
AnalogInputBlock, ...) read from there.

    DI/AI — set by the ENGINEER   (stimulus — plays the role of the plant)
    DO/AO — set by the LOGIC      (response — read-only)

That distinction drives every design choice below: DI/AI rows are clickable
(the whole row, not a tiny checkbox), DO/AO rows are visually inert. Nothing
here ever reaches the real controller — EPW-OS reads real inputs over
Modbus; this panel exists purely so an engineer can drive a scenario by
hand while building and testing logic offline.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QGroupBox, QScrollArea,
    QSlider, QDoubleSpinBox, QPushButton
)
from PySide6.QtGui import QPainter, QPen, QBrush, QFontMetrics
from PySide6.QtCore import Qt, Signal, QSettings

# Reused deliberately (§0A.3): the same green/black the canvas already uses
# for a live boolean wire/port, so a DI/DO's state dot here means the same
# thing at a glance as a highlighted wire on the schematic.
from logic_studio.ui.canvas import style as canvas_style

GROUP_SIZE = 8  # §0A.4: DI/DO channels are grouped in banks of 8, mirroring
                # how physical IO modules/terminal strips are organized and
                # read top-to-bottom on the real hardware.

_SETTINGS_KEY_ONLY_USED = "simulation/only_used"


class _StateDot(QWidget):
    """A small filled circle showing a boolean channel's current state —
    deliberately not a QCheckBox (§0A.3): a checkbox communicates a
    SETTING, this communicates a live STATE, and a colored dot reads at a
    glance while scanning dozens of rows the way a checked/unchecked square
    does not."""

    DIAMETER = 10

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(self.DIAMETER, self.DIAMETER)
        self._color = canvas_style.COLOR_LOGIC_LOW

    def set_color(self, color):
        if color != self._color:
            self._color = color
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(QPen(canvas_style.COLOR_OUTLINE, 1))
        painter.setBrush(QBrush(self._color))
        painter.drawEllipse(1, 1, self.DIAMETER - 2, self.DIAMETER - 2)


class ChannelRow(QWidget):
    """One DI/DO channel (§0A.3). Two display modes:

    - detailed (compact=False): dot, short address ("DI01", not
      "ELA01.DI01" — the module prefix repeats 32 times and is already in
      the section header), description (io_labels, blank otherwise —
      §0A.5), value right-aligned. Used by the "tylko użyte" flat list.
    - compact (compact=True): dot + short address only, dimmed when the
      channel isn't referenced by any block in the project. Used by the
      "wszystkie" grouped-by-8 view (§0A.4), which has no room for a
      description or value column.

    The whole row is the click target for an input channel (§0A.3) — not
    just a small checkbox — since a real test session means dozens of
    clicks. Output rows never respond to a click (§0A.0: DO is read-only).
    """

    def __init__(self, full_address, short_address, is_output, compact, parent=None):
        super().__init__(parent)
        self.full_address = full_address
        self.short_address = short_address
        self.is_output = is_output
        self.compact = compact
        self.on_click = None  # set by the panel; called with full_address

        self.setToolTip(full_address)
        if not is_output:
            self.setCursor(Qt.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(6)

        self.dot = _StateDot(self)
        layout.addWidget(self.dot)

        self.addr_label = QLabel(short_address)
        self.addr_label.setMinimumWidth(QFontMetrics(self.addr_label.font()).horizontalAdvance("DO32") + 4)
        layout.addWidget(self.addr_label)

        if not compact:
            self.desc_label = QLabel("")
            self.desc_label.setStyleSheet(_rgb_style("color", canvas_style.COLOR_COMMENT_TEXT))
            layout.addWidget(self.desc_label, 1)

            self.value_label = QLabel("0")
            self.value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.value_label.setMinimumWidth(14)
            layout.addWidget(self.value_label)
        else:
            self.desc_label = None
            self.value_label = None
            layout.addStretch(1)

        self.setAutoFillBackground(True)
        self._alternate = False
        self._apply_background()

    def set_description(self, text: str):
        if self.desc_label is not None:
            self.desc_label.setText(text or "")

    def set_alternate_background(self, alternate: bool):
        self._alternate = alternate
        self._apply_background()

    def _apply_background(self):
        if self.is_output:
            bg = "#ECECEC" if self._alternate else "#F5F5F5"
        else:
            bg = "#F0F0F0" if self._alternate else "#FFFFFF"
        self.setStyleSheet(f"ChannelRow {{ background-color: {bg}; }}")

    def refresh(self, value: bool, used: bool):
        color = canvas_style.COLOR_LOGIC_HIGH if value else canvas_style.COLOR_LOGIC_LOW
        self.dot.set_color(color)
        if self.value_label is not None:
            self.value_label.setText("1" if value else "0")
        if self.compact:
            # §0A.4: unused channels dimmed but still clickable/present.
            text_color = canvas_style.COLOR_TAG_TEXT if used else canvas_style.COLOR_COMMENT_TEXT
            self.addr_label.setStyleSheet(_rgb_style("color", text_color))

    def mousePressEvent(self, event):
        if not self.is_output and event.button() == Qt.LeftButton and self.on_click:
            self.on_click(self.full_address)
            event.accept()
            return
        super().mousePressEvent(event)


def _rgb_style(prop, qcolor):
    return f"{prop}: rgb({qcolor.red()},{qcolor.green()},{qcolor.blue()});"


class _ChannelGroup(QWidget):
    """A fixed bank of GROUP_SIZE compact ChannelRows under a header label
    ("DI01-08") — §0A.4. Internal order NEVER changes; only which COLUMN of
    groups this widget lands in is recomputed on resize, so DI17 is always
    the first row under "DI17-24" regardless of panel width."""

    def __init__(self, header_text, rows, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)

        header = QLabel(header_text)
        header.setStyleSheet("font-weight: bold;")
        layout.addWidget(header)
        for row in rows:
            layout.addWidget(row)


class SimulationPanel(QWidget):
    """DI/DO force panel (fixed, hardware-backed) plus the project's dynamic
    analog points (AUDIT_REPORT.md §6) and manual step controls."""

    # Emitted when the user asks to single-/multi-step the engine manually.
    # MainWindow owns the engine, so it performs the actual step(s) and the
    # canvas/status-bar refresh — see AUDIT_REPORT.md §6.3.
    step_requested = Signal(int)

    def __init__(self, project=None, parent=None, settings=None):
        super().__init__(parent)
        # Injectable so tests/verification scripts don't touch the real
        # user registry (QSettings("BroniszLabs", "EPW Logic Studio") is
        # NativeFormat on Windows == the actual HKCU registry) — same
        # pattern as LibraryPanel.
        self.settings = settings if settings is not None else QSettings("BroniszLabs", "EPW Logic Studio")

        self.project = project
        self.ai_spinboxes = {}   # address -> QDoubleSpinBox
        self.ai_sliders = {}     # address -> QSlider
        self.ao_labels = {}      # address -> QLabel

        # feat/multi-device-followups (closes ARCHITECTURE.md §9.1): the
        # DI/DO address lists — and every row/group widget derived from
        # them — are project-dependent (a project can define more than one
        # ELA/ADA device) and must be able to change after construction.
        # Left empty here; _rebuild_di_do_channels(), called from the
        # set_project(project) at the end of __init__, does the actual
        # first build against whatever project (or None) was passed in.
        self._di_addrs = []
        self._do_addrs = []
        self._di_state = {}
        self._do_state = {}

        # §0A.2: default ON — a real project uses a handful of the 32
        # available channels; showing all 32 by default is exactly the
        # noise this filter exists to remove.
        self._only_used = self._read_only_used_setting()
        self._group_columns = None  # forces the first _relayout to run

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        layout.addLayout(self._build_step_row())
        layout.addLayout(self._build_filter_row())

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)

        self._di_detail_rows = {}   # addr -> ChannelRow (compact=False)
        self._di_compact_rows = {}  # addr -> ChannelRow (compact=True)
        self._do_detail_rows = {}
        self._do_compact_rows = {}
        self._di_group_widgets = []
        self._do_group_widgets = []

        # "tylko użyte" (detailed, flat) sections
        self.di_used_group = QGroupBox("Wejścia dwustanowe (DI)")
        self.di_used_layout = QVBoxLayout(self.di_used_group)
        self.di_empty_label = QLabel("Brak używanych wejść — dodaj blok DI i przypisz adres.")
        self.do_used_group = QGroupBox("Wyjścia dwustanowe (DO)")
        self.do_used_layout = QVBoxLayout(self.do_used_group)
        self.do_empty_label = QLabel("Brak używanych wyjść — dodaj blok DO i przypisz adres.")

        # "wszystkie" (compact, grouped-by-8) sections
        self.di_all_group = QGroupBox("Wejścia dwustanowe (DI) — wszystkie")
        self.di_all_grid = QGridLayout(self.di_all_group)
        self.do_all_group = QGroupBox("Wyjścia dwustanowe (DO) — wszystkie")
        self.do_all_grid = QGridLayout(self.do_all_group)

        for w in (self.di_used_group, self.do_used_group, self.di_all_group, self.do_all_group):
            self._content_layout.addWidget(w)

        # Analog Inputs / Outputs — fully project-defined, rebuilt in set_project().
        self.ai_group = QGroupBox("Wejścia analogowe")
        self.ai_layout = QGridLayout(self.ai_group)
        self._content_layout.addWidget(self.ai_group)

        self.ao_group = QGroupBox("Wyjścia analogowe")
        self.ao_layout = QGridLayout(self.ao_group)
        self._content_layout.addWidget(self.ao_group)

        self._content_layout.addStretch(1)

        self._scroll.setWidget(self._content)
        layout.addWidget(self._scroll)

        self.set_project(project)

    # ---- Skeleton construction ---------------------------------------------

    def _build_step_row(self):
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
        return step_row

    def _build_filter_row(self):
        row = QHBoxLayout()
        self.only_used_btn = QPushButton()
        self.only_used_btn.setCheckable(True)
        self.only_used_btn.setChecked(self._only_used)
        self.only_used_btn.toggled.connect(self._on_only_used_toggled)
        row.addWidget(self.only_used_btn)
        row.addStretch()
        return row

    def _build_di_do_rows(self):
        for addr in self._di_addrs:
            short = _short_address(addr)
            detail = ChannelRow(addr, short, is_output=False, compact=False)
            detail.on_click = self._toggle_di
            self._di_detail_rows[addr] = detail

            compact = ChannelRow(addr, short, is_output=False, compact=True)
            compact.on_click = self._toggle_di
            self._di_compact_rows[addr] = compact

        for addr in self._do_addrs:
            short = _short_address(addr)
            detail = ChannelRow(addr, short, is_output=True, compact=False)
            self._do_detail_rows[addr] = detail

            compact = ChannelRow(addr, short, is_output=True, compact=True)
            self._do_compact_rows[addr] = compact

    def _build_channel_groups(self, addrs, compact_rows):
        groups = []
        for start in range(0, len(addrs), GROUP_SIZE):
            chunk = addrs[start:start + GROUP_SIZE]
            header = f"{_short_address(chunk[0])}-{_short_address(chunk[-1])[-2:]}"
            rows = [compact_rows[a] for a in chunk]
            groups.append(_ChannelGroup(header, rows))
        return groups

    # ---- DI/DO device-list rebuild (feat/multi-device-followups) -----------
    # Closes ARCHITECTURE.md §9.1: the DI/DO grid used to be built exactly
    # once, in __init__, from DeviceModel's single-device default — adding a
    # second ELA/ADA device via Project Settings worked correctly in the
    # engine/compiler/export but never became visible or clickable here.

    def _rebuild_di_do_channels(self):
        """Recomputes the DI/DO address lists from `self.project`'s ELA/ADA
        device lists and rebuilds every row/group widget derived from them
        — but ONLY when that list actually changed. Called from
        set_project() on every project change, so guarding on an actual
        difference matters: without it, every ordinary edit (add a block,
        change a property) would tear down and recreate 64+ widgets for
        nothing."""
        from logic_studio.core.device_model import DeviceModel

        new_di = DeviceModel.get_ela_addresses(self.project)
        new_do = DeviceModel.get_ada_addresses(self.project)
        if new_di == self._di_addrs and new_do == self._do_addrs:
            return

        # A channel that still exists after the change keeps its current
        # forced value; one dropped by removing a device is simply
        # forgotten; one newly added starts at the same False a fresh
        # project would show it as.
        old_di_state, old_do_state = self._di_state, self._do_state
        self._teardown_di_do_widgets()

        self._di_addrs = new_di
        self._do_addrs = new_do
        self._di_state = {a: old_di_state.get(a, False) for a in new_di}
        self._do_state = {a: old_do_state.get(a, False) for a in new_do}

        self._build_di_do_rows()
        self._di_group_widgets = self._build_channel_groups(self._di_addrs, self._di_compact_rows)
        self._do_group_widgets = self._build_channel_groups(self._do_addrs, self._do_compact_rows)
        # Force the _recompute_group_columns() that set_project() triggers
        # right after this (via _apply_view_mode()) to actually place the
        # brand-new group widgets into the grid, even if the computed
        # column count happens to equal the stale one from before rebuild
        # (its early-return guard compares against this value).
        self._group_columns = None

    def _teardown_di_do_widgets(self):
        """Discards every row/group widget derived from the current DI/DO
        address lists, ahead of rebuilding them for a new device list.
        setParent(None) detaches a widget from whatever layout currently
        holds it (a used-list QVBoxLayout for a detail row, an all-channels
        QGridLayout for a group) before scheduling its actual deletion."""
        for rows in (self._di_detail_rows, self._di_compact_rows,
                     self._do_detail_rows, self._do_compact_rows):
            for w in rows.values():
                w.setParent(None)
                w.deleteLater()
            rows.clear()
        for group in self._di_group_widgets + self._do_group_widgets:
            group.setParent(None)
            group.deleteLater()
        self._di_group_widgets = []
        self._do_group_widgets = []

    # ---- Only-used toggle (§0A.2) ------------------------------------------

    def _read_only_used_setting(self) -> bool:
        val = self.settings.value(_SETTINGS_KEY_ONLY_USED, True)
        if isinstance(val, str):
            return val.lower() in ("true", "1")
        return bool(val)

    def _on_only_used_toggled(self, checked: bool):
        self._only_used = checked
        self.settings.setValue(_SETTINGS_KEY_ONLY_USED, checked)
        # Full rebuild, not just _apply_view_mode(): the analog sections
        # (§0A.6) are filtered by "only used" too, but only rebuilt inside
        # set_project() — a toggle needs the same rebuild a project change
        # gets, not just the DI/DO group visibility swap.
        self.set_project(self.project)

    def _used_di_addrs(self) -> set:
        if self.project is None:
            return set()
        return {b.properties.get("Address", "") for b in self.project.blocks if b.type_id == "input.di"}

    def _used_do_addrs(self) -> set:
        if self.project is None:
            return set()
        return {b.properties.get("Address", "") for b in self.project.blocks if b.type_id == "output.do"}

    def _used_analog_addrs(self) -> set:
        if self.project is None:
            return set()
        return {
            b.properties.get("Address", "")
            for b in self.project.blocks
            if b.type_id in ("input.ai", "output.ao")
        }

    def refresh(self):
        """Recomputes the used-channel set and rebuilds every filtered/
        grouped view from the CURRENT self.project — call after any project
        mutation that can change which channels are "used" (block added/
        removed, Address property edited). §0A.2."""
        self.set_project(self.project)

    def _apply_view_mode(self):
        used = self._only_used
        self.only_used_btn.setText(
            f"tylko użyte ({len(self._used_di_addrs() | self._used_do_addrs())})" if used
            else f"wszystkie ({len(self._di_addrs) + len(self._do_addrs)})"
        )
        self.di_used_group.setVisible(used)
        self.do_used_group.setVisible(used)
        self.di_all_group.setVisible(not used)
        self.do_all_group.setVisible(not used)
        self._recompute_group_columns()

    # ---- Dynamic group-column layout (§0A.1/§0A.4) -------------------------

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._recompute_group_columns()

    def _group_tile_width(self) -> int:
        """§0A.1: derived from QFontMetrics for the widest label a group can
        show (its header, e.g. "DI25-32", or a row's own short address),
        never a hardcoded guess."""
        fm = QFontMetrics(self.font())
        widest = max(
            fm.horizontalAdvance("DI25-32"),
            fm.horizontalAdvance("DO25-32"),
            fm.horizontalAdvance("DO32"),
        )
        return widest + _StateDot.DIAMETER + 24  # dot + margins/spacing

    def _recompute_group_columns(self):
        """§0A.1: column count comes from the scroll area's ACTUAL viewport
        width (not this widget's own requested width, which is what the
        previous, buggy version used and why 1/3 of channels rendered
        outside the visible area) minus the vertical scrollbar's own
        width."""
        viewport_w = self._scroll.viewport().width()
        if viewport_w <= 0:
            viewport_w = max(self.width(), 1)
        tile_w = max(self._group_tile_width(), 1)
        columns = max(1, viewport_w // tile_w)  # §0A.1: minimum one column

        if columns == self._group_columns:
            return
        self._group_columns = columns

        self._relayout_groups(self.di_all_grid, self._di_group_widgets, columns)
        self._relayout_groups(self.do_all_grid, self._do_group_widgets, columns)

    @staticmethod
    def _relayout_groups(grid_layout, group_widgets, columns):
        """Only the GROUP's position moves — never a channel's position
        within its group (§0A.4's central rule): each _ChannelGroup is a
        single opaque widget here, its own internal QVBoxLayout untouched."""
        while grid_layout.count():
            grid_layout.takeAt(0)
        for i, group in enumerate(group_widgets):
            grid_layout.addWidget(group, i // columns, i % columns)

    # ---- Row toggling / state --------------------------------------------

    def _toggle_di(self, addr):
        self._di_state[addr] = not self._di_state[addr]
        self._refresh_di_row(addr)

    def _refresh_di_row(self, addr):
        value = self._di_state[addr]
        used = addr in self._used_di_addrs()
        self._di_detail_rows[addr].refresh(value, used)
        self._di_compact_rows[addr].refresh(value, used)

    def _refresh_do_row(self, addr):
        value = self._do_state[addr]
        used = addr in self._used_do_addrs()
        self._do_detail_rows[addr].refresh(value, used)
        self._do_compact_rows[addr].refresh(value, used)

    def _rebuild_used_lists(self):
        from logic_studio.core.device_model import DeviceModel

        used_di = self._used_di_addrs()
        used_do = self._used_do_addrs()
        io_labels = (self.project.settings.get("io_labels", {}) if self.project else {}) or {}

        self._rebuild_one_used_list(
            self.di_used_layout, self.di_empty_label, self._di_addrs,
            used_di, self._di_detail_rows, io_labels,
        )
        self._rebuild_one_used_list(
            self.do_used_layout, self.do_empty_label, self._do_addrs,
            used_do, self._do_detail_rows, io_labels,
        )

        for addr in self._di_addrs:
            self._refresh_di_row(addr)
        for addr in self._do_addrs:
            self._refresh_do_row(addr)

    @staticmethod
    def _rebuild_one_used_list(target_layout, empty_label, all_addrs, used_addrs, detail_rows, io_labels):
        while target_layout.count():
            target_layout.takeAt(0)

        used_in_order = [a for a in all_addrs if a in used_addrs]
        if not used_in_order:
            target_layout.addWidget(empty_label)
            return

        for i, addr in enumerate(used_in_order):
            row = detail_rows[addr]
            row.set_description(io_labels.get(addr, ""))
            row.set_alternate_background(i % 2 == 1)
            target_layout.addWidget(row)

    # ---- Project wiring -----------------------------------------------------

    def set_project(self, project):
        """Rebuild every project-derived section — DI/DO used-lists, DI/DO
        used/unused dimming, and the analog sections. Call whenever the
        project (or anything that changes which channels are "used")
        changes: new/open/undo/redo, Project Settings, a block added/
        removed, an Address property edited (§0A.2) — see refresh(), the
        lightweight alias for "same project object, something changed"."""
        self.project = project
        self._rebuild_di_do_channels()

        self._clear_layout(self.ai_layout)
        self._clear_layout(self.ao_layout)
        self.ai_spinboxes.clear()
        self.ai_sliders.clear()
        self.ao_labels.clear()

        self._rebuild_used_lists()
        self._apply_view_mode()

        if project is None:
            return

        from logic_studio.core.device_model import DeviceModel
        points = DeviceModel.get_analog_points(project)
        used_analog = self._used_analog_addrs()
        io_labels = project.settings.get("io_labels", {}) or {}

        def _visible(addr):
            return (not self._only_used) or addr in used_analog

        row = 0
        for point in points:
            if point.get("direction") != "input":
                continue
            addr = point.get("address", "")
            if not _visible(addr):
                continue
            unit = point.get("unit", "")
            label_text = io_labels.get(addr) or point.get("name", addr) or addr
            min_v = float(point.get("min", 0.0))
            max_v = float(point.get("max", 100.0))
            span = (max_v - min_v) or 1.0

            self.ai_layout.addWidget(QLabel(addr), row, 0)
            desc = f"{label_text} [{unit}]" if unit else label_text
            desc_lbl = QLabel(desc)
            desc_lbl.setStyleSheet(_rgb_style("color", canvas_style.COLOR_COMMENT_TEXT))
            self.ai_layout.addWidget(desc_lbl, row, 1)

            slider = QSlider(Qt.Horizontal)
            slider.setRange(0, 1000)  # scaled 0..1000 across [min, max]

            spin = QDoubleSpinBox()
            spin.setRange(min_v, max_v)
            spin.setDecimals(2)
            spin.setValue(min_v)
            spin.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

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

            self.ai_layout.addWidget(slider, row, 2)
            self.ai_layout.addWidget(spin, row, 3)

            self.ai_spinboxes[addr] = spin
            self.ai_sliders[addr] = slider
            row += 1

        row = 0
        for point in points:
            if point.get("direction") != "output":
                continue
            addr = point.get("address", "")
            if not _visible(addr):
                continue
            unit = point.get("unit", "")
            label_text = io_labels.get(addr) or point.get("name", addr) or addr

            self.ao_layout.addWidget(QLabel(addr), row, 0)
            desc = f"{label_text} [{unit}]" if unit else label_text
            desc_lbl = QLabel(desc)
            desc_lbl.setStyleSheet(_rgb_style("color", canvas_style.COLOR_COMMENT_TEXT))
            self.ao_layout.addWidget(desc_lbl, row, 1)

            value_lbl = QLabel("-")
            value_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            value_lbl.setStyleSheet("background-color: white; padding: 2px; border: 1px solid black;")
            self.ao_layout.addWidget(value_lbl, row, 2)
            self.ao_labels[addr] = value_lbl
            row += 1

    @staticmethod
    def _clear_layout(layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    # ---- Public state API (unchanged contract — MainWindow/tests rely on it) --

    def set_ada_state(self, index: int, state: bool):
        """Update ADA (DO) output state. Index is 0-31."""
        if 0 <= index < len(self._do_addrs):
            addr = self._do_addrs[index]
            self._do_state[addr] = bool(state)
            self._refresh_do_row(addr)

    def get_ela_state(self, index: int) -> bool:
        """Get ELA (DI) input state. Index is 0-31."""
        if 0 <= index < len(self._di_addrs):
            return self._di_state[self._di_addrs[index]]
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


def _short_address(full_address: str) -> str:
    """"ELA01.DI01" -> "DI01" (§0A.3: the module prefix repeats 32 times, is
    already in the section header, and eats a third of the row's width for
    nothing a working engineer needs at a glance)."""
    return full_address.rsplit(".", 1)[-1] if "." in full_address else full_address
