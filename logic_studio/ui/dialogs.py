from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QSpinBox, QDialogButtonBox,
    QTableWidget, QTableWidgetItem, QComboBox, QPushButton, QHBoxLayout,
    QLabel, QMessageBox, QHeaderView, QTabWidget, QWidget, QCheckBox, QFileDialog
)

ORIGINAL_ENTRY_ROLE = Qt.UserRole

# feat/internal-bits: type_ids that reference an internal-signal registry
# entry via their "Bit" property — used both by the registry editor tab
# (§7.2/§7.3) and, via internal_bit_id(), everywhere a resolved id is
# needed.
_INTERNAL_SIGNAL_TYPE_IDS = ("virtual.input", "virtual.output", "internal.reg_in", "internal.reg_out")


class ProjectSettingsDialog(QDialog):
    """Project Settings dialog: name/version/cycle time, plus the analog
    points table (AUDIT_REPORT.md §1.3). Unlike DI/DO, analog points have no
    fixed hardware channel list to pick from — the project IS the source of
    truth for what analog points exist, so they are edited here directly.
    """

    COLUMNS = ["Address", "Name", "Unit", "Min", "Max", "Direction"]

    # feat/internal-bits §7.1
    SIGNAL_COLUMNS = ["Nazwa", "Typ", "Trwały", "Kategoria", "Etykieta", "Opis", "Użycia"]

    # feat/io-labels-and-ids §2.1
    IO_LABEL_COLUMNS = ["Adres", "Etykieta", "Użycia"]

    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        self._result_points = None
        self._result_signals = None
        self.setWindowTitle("Project Settings")
        self.resize(760, 480)

        layout = QVBoxLayout(self)

        tabs = QTabWidget()
        layout.addWidget(tabs)

        general_tab = QWidget()
        general_layout = QVBoxLayout(general_tab)

        form = QFormLayout()
        self.name_edit = QLineEdit(str(project.settings.get("name", "New Project")))
        self.version_edit = QLineEdit(str(project.settings.get("version", "1.0")))
        self.cycle_spin = QSpinBox()
        self.cycle_spin.setRange(1, 60000)
        self.cycle_spin.setSuffix(" ms")
        self.cycle_spin.setValue(int(project.settings.get("cycle_time_ms", 100)))
        form.addRow("Name", self.name_edit)
        form.addRow("Version", self.version_edit)
        form.addRow("Cycle Time", self.cycle_spin)
        general_layout.addLayout(form)

        general_layout.addWidget(QLabel("Punkty analogowe"))
        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        general_layout.addWidget(self.table)

        row_buttons = QHBoxLayout()
        self.add_btn = QPushButton("Dodaj")
        self.remove_btn = QPushButton("Usuń")
        self.add_btn.clicked.connect(lambda: self._add_row())
        self.remove_btn.clicked.connect(self._remove_selected_rows)
        row_buttons.addWidget(self.add_btn)
        row_buttons.addWidget(self.remove_btn)
        row_buttons.addStretch()
        general_layout.addLayout(row_buttons)

        self._load_points(project.settings.get("analog_points", []))
        tabs.addTab(general_tab, "Ogólne")

        # feat/internal-bits §7.1: "Sygnały wewnętrzne" tab.
        signals_tab = QWidget()
        signals_layout = QVBoxLayout(signals_tab)

        self.signals_table = QTableWidget(0, len(self.SIGNAL_COLUMNS))
        self.signals_table.setHorizontalHeaderLabels(self.SIGNAL_COLUMNS)
        self.signals_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        signals_layout.addWidget(self.signals_table)

        signal_buttons = QHBoxLayout()
        self.add_signal_btn = QPushButton("Dodaj")
        self.remove_signal_btn = QPushButton("Usuń")
        self.import_signals_btn = QPushButton("Importuj...")
        self.export_signals_btn = QPushButton("Eksportuj...")
        self.add_signal_btn.clicked.connect(lambda: self._add_signal_row())
        self.remove_signal_btn.clicked.connect(self._remove_selected_signal_rows)
        self.import_signals_btn.clicked.connect(self._import_signals)
        self.export_signals_btn.clicked.connect(self._export_signals)
        signal_buttons.addWidget(self.add_signal_btn)
        signal_buttons.addWidget(self.remove_signal_btn)
        signal_buttons.addStretch()
        signal_buttons.addWidget(self.import_signals_btn)
        signal_buttons.addWidget(self.export_signals_btn)
        signals_layout.addLayout(signal_buttons)

        # Snapshot at open time — needed at accept time to detect renames
        # (§7.3) and deletions of a still-used entry (§7.2), by comparing
        # against whatever the table ends up holding.
        self._original_signals = [dict(e) for e in project.settings.get("internal_bits", [])]
        self._bit_renames = {}

        self._load_signals(project.settings.get("internal_bits", []))
        tabs.addTab(signals_tab, "Sygnały wewnętrzne")

        # feat/io-labels-and-ids §2.1: "Etykiety wejść/wyjść" tab.
        io_labels_tab = QWidget()
        io_labels_layout = QVBoxLayout(io_labels_tab)

        filter_row = QHBoxLayout()
        self.io_labels_filter_edit = QLineEdit()
        self.io_labels_filter_edit.setPlaceholderText("Szukaj po adresie lub etykiecie...")
        self.io_labels_filter_edit.textChanged.connect(self._apply_io_labels_filter)
        filter_row.addWidget(self.io_labels_filter_edit)
        self.io_labels_only_used_check = QCheckBox("Pokaż tylko używane")
        self.io_labels_only_used_check.setChecked(True)  # §2.1: default ON
        self.io_labels_only_used_check.toggled.connect(self._apply_io_labels_filter)
        filter_row.addWidget(self.io_labels_only_used_check)
        io_labels_layout.addLayout(filter_row)

        self.io_labels_table = QTableWidget(0, len(self.IO_LABEL_COLUMNS))
        self.io_labels_table.setHorizontalHeaderLabels(self.IO_LABEL_COLUMNS)
        self.io_labels_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        io_labels_layout.addWidget(self.io_labels_table)

        io_labels_buttons = QHBoxLayout()
        self.import_io_labels_btn = QPushButton("Importuj...")
        self.export_io_labels_btn = QPushButton("Eksportuj...")
        self.import_io_labels_btn.clicked.connect(self._import_io_labels)
        self.export_io_labels_btn.clicked.connect(self._export_io_labels)
        io_labels_buttons.addStretch()
        io_labels_buttons.addWidget(self.import_io_labels_btn)
        io_labels_buttons.addWidget(self.export_io_labels_btn)
        io_labels_layout.addLayout(io_labels_buttons)

        self._result_io_labels = None
        self._load_io_labels()
        tabs.addTab(io_labels_tab, "Etykiety wejść/wyjść")

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _load_points(self, points):
        self.table.setRowCount(0)
        for p in points:
            self._add_row(p)

    def _add_row(self, point=None):
        point = point or {"address": "", "name": "", "unit": "", "min": 0.0, "max": 100.0, "direction": "input"}
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(str(point.get("address", ""))))
        self.table.setItem(row, 1, QTableWidgetItem(str(point.get("name", ""))))
        self.table.setItem(row, 2, QTableWidgetItem(str(point.get("unit", ""))))
        self.table.setItem(row, 3, QTableWidgetItem(str(point.get("min", 0.0))))
        self.table.setItem(row, 4, QTableWidgetItem(str(point.get("max", 100.0))))
        combo = QComboBox()
        combo.addItems(["input", "output"])
        combo.setCurrentText(point.get("direction", "input"))
        self.table.setCellWidget(row, 5, combo)

    def _remove_selected_rows(self):
        rows = sorted({idx.row() for idx in self.table.selectedIndexes()}, reverse=True)
        for r in rows:
            self.table.removeRow(r)

    def _collect_points(self):
        """Returns (points, error_message); error_message is None if every
        row is valid (AUDIT_REPORT.md §1.3): address non-empty, unique,
        no spaces; min < max; direction in {input, output}."""
        points = []
        seen_addresses = set()
        for row in range(self.table.rowCount()):
            def cell_text(col):
                item = self.table.item(row, col)
                return item.text().strip() if item else ""

            addr = cell_text(0)
            name = cell_text(1)
            unit = cell_text(2)
            min_text = cell_text(3)
            max_text = cell_text(4)
            combo = self.table.cellWidget(row, 5)
            direction = combo.currentText() if combo else "input"

            if not addr:
                return None, f"Wiersz {row + 1}: adres nie może być pusty."
            if " " in addr:
                return None, f"Wiersz {row + 1}: adres '{addr}' nie może zawierać spacji."
            if addr in seen_addresses:
                return None, f"Wiersz {row + 1}: adres '{addr}' powtarza się w projekcie."
            seen_addresses.add(addr)

            try:
                min_v = float(min_text)
                max_v = float(max_text)
            except ValueError:
                return None, f"Wiersz {row + 1}: min/max muszą być liczbami."

            if not (min_v < max_v):
                return None, f"Wiersz {row + 1}: min ({min_v}) musi być mniejsze niż max ({max_v})."

            if direction not in ("input", "output"):
                return None, f"Wiersz {row + 1}: direction musi być 'input' albo 'output'."

            points.append({
                "address": addr, "name": name, "unit": unit,
                "min": min_v, "max": max_v, "direction": direction,
            })
        return points, None

    # ---- Internal signal registry (feat/internal-bits §7) --------------------

    @staticmethod
    def _block_signal_type(type_id: str) -> str:
        return "REAL" if type_id in ("internal.reg_in", "internal.reg_out") else "BOOL"

    def _usage_blocks(self, name: str) -> list:
        """Blocks referencing internal-signal registry entry `name` (§7.2's
        "Użycia" column and §7.3's rename-propagation both need this)."""
        if not name:
            return []
        lname = name.lower()
        return [
            b for b in self.project.blocks
            if b.type_id in _INTERNAL_SIGNAL_TYPE_IDS and b.properties.get("Bit", "").lower() == lname
        ]

    def _load_signals(self, entries):
        self.signals_table.setRowCount(0)
        for e in entries:
            self._add_signal_row(e, original=dict(e))

    def _add_signal_row(self, entry=None, original=None):
        entry = entry or {"name": "", "type": "BOOL", "retentive": False, "category": "", "label": "", "description": ""}
        row = self.signals_table.rowCount()
        self.signals_table.insertRow(row)

        name_item = QTableWidgetItem(str(entry.get("name", "")))
        name_item.setData(ORIGINAL_ENTRY_ROLE, original)
        self.signals_table.setItem(row, 0, name_item)

        type_combo = QComboBox()
        type_combo.addItems(["BOOL", "REAL"])
        type_combo.setCurrentText(entry.get("type", "BOOL"))
        self.signals_table.setCellWidget(row, 1, type_combo)

        retentive_check = QCheckBox()
        retentive_check.setChecked(bool(entry.get("retentive", False)))
        self.signals_table.setCellWidget(row, 2, retentive_check)

        self.signals_table.setItem(row, 3, QTableWidgetItem(str(entry.get("category", ""))))
        self.signals_table.setItem(row, 4, QTableWidgetItem(str(entry.get("label", ""))))
        self.signals_table.setItem(row, 5, QTableWidgetItem(str(entry.get("description", ""))))

        usage_item = QTableWidgetItem(str(len(self._usage_blocks(entry.get("name", "")))))
        usage_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)  # §7.2: read-only, informational
        self.signals_table.setItem(row, 6, usage_item)

    def _remove_selected_signal_rows(self):
        rows = sorted({idx.row() for idx in self.signals_table.selectedIndexes()}, reverse=True)
        for r in rows:
            self.signals_table.removeRow(r)

    def _signal_cell_text(self, row, col):
        item = self.signals_table.item(row, col)
        return item.text().strip() if item else ""

    def _collect_signals(self):
        """Returns (entries, error, renames). error is a message string —
        including format/uniqueness (§1.3) and a type change incompatible
        with existing usage, REJECTED here rather than applied and only
        caught later by the validator (§7.3's explicit requirement) — if
        anything is wrong. renames is {old_name: new_name} for rows whose
        name changed relative to what they were when the dialog opened."""
        entries = []
        renames = {}

        for row in range(self.signals_table.rowCount()):
            name = self._signal_cell_text(row, 0)
            type_combo = self.signals_table.cellWidget(row, 1)
            type_ = type_combo.currentText() if type_combo else "BOOL"
            retentive_check = self.signals_table.cellWidget(row, 2)
            retentive = retentive_check.isChecked() if retentive_check else False
            category = self._signal_cell_text(row, 3)
            label = self._signal_cell_text(row, 4)
            description = self._signal_cell_text(row, 5)

            entries.append({
                "name": name, "type": type_, "retentive": retentive,
                "category": category, "label": label, "description": description,
            })

            name_item = self.signals_table.item(row, 0)
            original = name_item.data(ORIGINAL_ENTRY_ROLE) if name_item else None
            if original:
                if original.get("name", "") != name and original.get("name", ""):
                    renames[original["name"]] = name
                if original.get("type") != type_:
                    usage = self._usage_blocks(original.get("name", ""))
                    wrong_family = [b for b in usage if self._block_signal_type(b.type_id) != type_]
                    if wrong_family:
                        required = self._block_signal_type(wrong_family[0].type_id)
                        names = ", ".join(b.display_name for b in wrong_family)
                        return None, (
                            f"Nie można zmienić typu sygnału '{original['name']}' na {type_} — "
                            f"używają go bloki wymagające typu {required}: {names}."
                        ), None

        from logic_studio.core.internal_bits import validate_internal_bits_registry
        format_errors = validate_internal_bits_registry(entries)
        if format_errors:
            return None, "\n".join(format_errors), None

        return entries, None, renames

    def _import_signals(self):
        """§7.4: import a registry from JSON, same shape as export."""
        path, _ = QFileDialog.getOpenFileName(self, "Importuj rejestr sygnałów wewnętrznych", "", "JSON (*.json)")
        if not path:
            return
        import json
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            entries = data.get("internal_bits", data) if isinstance(data, dict) else data
        except Exception as e:
            QMessageBox.critical(self, "Błąd importu", str(e))
            return

        from logic_studio.core.internal_bits import validate_internal_bits_registry
        errors = validate_internal_bits_registry(entries)
        if errors:
            QMessageBox.critical(self, "Nieprawidłowy plik", "\n".join(errors))
            return
        self._load_signals(entries)

    def _export_signals(self):
        """§7.4: export in the same format project.settings["internal_bits"]
        itself uses (§1.1) — shared with EPW-OS/Synoptic Editor rather than
        each tool inventing its own registry by hand."""
        entries, error, _ = self._collect_signals()
        if error:
            QMessageBox.critical(self, "Nieprawidłowe dane", error)
            return
        path, _ = QFileDialog.getSaveFileName(self, "Eksportuj rejestr sygnałów wewnętrznych", "internal_bits.json", "JSON (*.json)")
        if not path:
            return
        import json
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"format": "EPW_INTERNAL_BITS", "schema_version": 1, "internal_bits": entries}, f, indent=2, ensure_ascii=False)

    # ---- I/O address labels (feat/io-labels-and-ids §2) -----------------------

    def _address_usage_blocks(self, address: str) -> list:
        """Blocks in the project whose "Address" property names this
        channel — §2.1's "Użycia" column, and what "unused" (grayed out,
        hidden by the default filter) means here."""
        if not address:
            return []
        return [b for b in self.project.blocks if b.properties.get("Address", "") == address]

    def _load_io_labels(self):
        from logic_studio.core.device_model import DeviceModel

        self.io_labels_table.setRowCount(0)
        gray = QColor(150, 150, 150)

        for address in DeviceModel.all_addresses(self.project):
            row = self.io_labels_table.rowCount()
            self.io_labels_table.insertRow(row)

            addr_item = QTableWidgetItem(address)
            addr_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)  # read-only

            label_item = QTableWidgetItem(DeviceModel.get_io_label(self.project, address))
            # Editable by double-click/Enter — the default QTableWidgetItem
            # flags already include ItemIsEditable; Esc-to-cancel and
            # Enter-to-commit are Qt's own default cell-editor behavior,
            # nothing extra needed here (§2.1).

            usage_count = len(self._address_usage_blocks(address))
            usage_item = QTableWidgetItem(str(usage_count))
            usage_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)  # read-only

            if usage_count == 0:
                addr_item.setForeground(gray)
                label_item.setForeground(gray)
                usage_item.setForeground(gray)

            self.io_labels_table.setItem(row, 0, addr_item)
            self.io_labels_table.setItem(row, 1, label_item)
            self.io_labels_table.setItem(row, 2, usage_item)

        self._apply_io_labels_filter()

    def _apply_io_labels_filter(self):
        """§2.1: filters by address OR label text, and — default ON — by
        whether the address is actually used by any block in the project."""
        text = self.io_labels_filter_edit.text().strip().lower()
        only_used = self.io_labels_only_used_check.isChecked()

        for row in range(self.io_labels_table.rowCount()):
            addr = self.io_labels_table.item(row, 0).text()
            label = self.io_labels_table.item(row, 1).text()
            usage = int(self.io_labels_table.item(row, 2).text() or "0")

            visible = not (only_used and usage == 0)
            if visible and text and text not in addr.lower() and text not in label.lower():
                visible = False

            self.io_labels_table.setRowHidden(row, not visible)

    def _collect_io_labels(self) -> dict:
        """address -> label for every row with a non-empty (post-strip)
        label. A cleared row is simply absent here — apply_to_project()
        still iterates every KNOWN address, so an address missing from
        this dict is what tells DeviceModel.set_io_label() to remove it."""
        labels = {}
        for row in range(self.io_labels_table.rowCount()):
            addr = self.io_labels_table.item(row, 0).text()
            label = self.io_labels_table.item(row, 1).text().strip()
            if label:
                labels[addr] = label
        return labels

    def _import_io_labels(self):
        """§2.2: same shape as §1.1 — a plain {address: label} dict, or
        that dict wrapped in a small envelope (mirrors how internal_bits
        import/export already works). Never overwrites silently — reports
        how many entries will be added/changed/skipped (unknown address)
        and asks for confirmation before touching the table at all."""
        from logic_studio.core.device_model import DeviceModel

        path, _ = QFileDialog.getOpenFileName(self, "Importuj etykiety wejść/wyjść", "", "JSON (*.json)")
        if not path:
            return
        import json
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            incoming = data.get("io_labels", data) if isinstance(data, dict) else None
        except Exception as e:
            QMessageBox.critical(self, "Błąd importu", str(e))
            return
        if not isinstance(incoming, dict):
            QMessageBox.critical(self, "Nieprawidłowy plik", "Oczekiwano słownika adres -> etykieta.")
            return

        valid_addresses = set(DeviceModel.all_addresses(self.project))
        current = self._collect_io_labels()

        added = changed = skipped = 0
        for addr, label in incoming.items():
            if addr not in valid_addresses:
                skipped += 1
                continue
            label = (label or "").strip()
            if not label:
                continue
            old = current.get(addr, "")
            if not old:
                added += 1
            elif old != label:
                changed += 1

        reply = QMessageBox.question(
            self, "Import etykiet wejść/wyjść",
            f"Zostanie dodanych: {added}\nZmienionych: {changed}\n"
            f"Pominiętych (nieznany adres): {skipped}\n\nKontynuować?",
        )
        if reply != QMessageBox.Yes:
            return

        row_by_address = {self.io_labels_table.item(r, 0).text(): r for r in range(self.io_labels_table.rowCount())}
        for addr, label in incoming.items():
            row = row_by_address.get(addr)
            if row is None:
                continue  # unknown address — already counted as skipped above
            self.io_labels_table.item(row, 1).setText((label or "").strip())

    def _export_io_labels(self):
        """§2.2: same format §1.1 defines — {address: label} wrapped in the
        same small envelope internal_bits' own export already uses."""
        labels = self._collect_io_labels()
        path, _ = QFileDialog.getSaveFileName(self, "Eksportuj etykiety wejść/wyjść", "io_labels.json", "JSON (*.json)")
        if not path:
            return
        import json
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"format": "EPW_IO_LABELS", "schema_version": 1, "io_labels": labels}, f, indent=2, ensure_ascii=False)

    def _on_accept(self):
        points, error = self._collect_points()
        if error:
            QMessageBox.critical(self, "Nieprawidłowe dane", error)
            return

        signals, sig_error, renames = self._collect_signals()
        if sig_error:
            QMessageBox.critical(self, "Nieprawidłowe dane (sygnały wewnętrzne)", sig_error)
            return

        # §7.2: deleting a signal that's still used needs confirmation,
        # naming the blocks — a row simply missing from the final table
        # counts as deleted. A RENAMED entry is not a deletion (its old
        # name is legitimately gone from `signals`, same as a real
        # delete's would be) — skip anything `_collect_signals()` already
        # identified as a rename, or every rename would wrongly prompt
        # this confirmation for its own old name.
        new_names_lower = {e["name"].lower() for e in signals}
        for original in self._original_signals:
            orig_name = original.get("name", "")
            if orig_name.lower() in new_names_lower or orig_name in renames:
                continue
            usage = self._usage_blocks(orig_name)
            if usage:
                names = ", ".join(b.display_name for b in usage)
                reply = QMessageBox.question(
                    self, "Usunięcie używanego sygnału",
                    f"Sygnał '{original['name']}' jest używany przez: {names}.\n"
                    "Usunięcie go pozostawi te bloki bez skonfigurowanego sygnału. Kontynuować?",
                )
                if reply != QMessageBox.Yes:
                    return

        self._result_points = points
        self._result_signals = signals
        self._bit_renames = renames
        self._result_io_labels = self._collect_io_labels()
        self.accept()

    def apply_to_project(self):
        """Call after exec() returns Accepted. Pushes one undo snapshot and
        applies every edited setting, including the validated analog point
        list, atomically."""
        self.project.push_state()
        self.project.settings["name"] = self.name_edit.text()
        self.project.settings["version"] = self.version_edit.text()
        self.project.settings["cycle_time_ms"] = self.cycle_spin.value()
        self.project.settings["analog_points"] = self._result_points or []
        self.project.settings["internal_bits"] = self._result_signals or []

        # §7.3: a renamed registry entry must be propagated to every block
        # still pointing at its old name — a type/retentive change needs no
        # such propagation, since a block only stores the bare name; its
        # resolved M./MR./MW./MWR.<name> id is always derived fresh from
        # whatever the registry currently says (core.internal_bits.
        # internal_bit_id()), so that part updates automatically for free.
        for old_name, new_name in self._bit_renames.items():
            for block in self._usage_blocks(old_name):
                block.properties["Bit"] = new_name

        # feat/io-labels-and-ids §2.3: one push_state()/set_dirty() for the
        # whole dialog (set_dirty() is called by whoever calls
        # apply_to_project() — see main_window.py's _open_project_settings())
        # — not per-cell-edit, exactly like the points/signals tables above.
        # Iterates every KNOWN address (not just the ones with a label) so
        # a row the user cleared actually removes that address's entry via
        # DeviceModel.set_io_label()'s empty-label-removes-it rule, instead
        # of leaving a stale value behind.
        from logic_studio.core.device_model import DeviceModel
        result_io_labels = self._result_io_labels or {}
        for address in DeviceModel.all_addresses(self.project):
            DeviceModel.set_io_label(self.project, address, result_io_labels.get(address, ""))
