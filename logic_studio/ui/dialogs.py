from PySide6.QtCore import Qt
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
