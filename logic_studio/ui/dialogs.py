from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QSpinBox, QDialogButtonBox,
    QTableWidget, QTableWidgetItem, QComboBox, QPushButton, QHBoxLayout,
    QLabel, QMessageBox, QHeaderView
)


class ProjectSettingsDialog(QDialog):
    """Project Settings dialog: name/version/cycle time, plus the analog
    points table (AUDIT_REPORT.md §1.3). Unlike DI/DO, analog points have no
    fixed hardware channel list to pick from — the project IS the source of
    truth for what analog points exist, so they are edited here directly.
    """

    COLUMNS = ["Address", "Name", "Unit", "Min", "Max", "Direction"]

    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        self._result_points = None
        self.setWindowTitle("Project Settings")
        self.resize(640, 420)

        layout = QVBoxLayout(self)

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
        layout.addLayout(form)

        layout.addWidget(QLabel("Punkty analogowe"))
        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)

        row_buttons = QHBoxLayout()
        self.add_btn = QPushButton("Dodaj")
        self.remove_btn = QPushButton("Usuń")
        self.add_btn.clicked.connect(lambda: self._add_row())
        self.remove_btn.clicked.connect(self._remove_selected_rows)
        row_buttons.addWidget(self.add_btn)
        row_buttons.addWidget(self.remove_btn)
        row_buttons.addStretch()
        layout.addLayout(row_buttons)

        self._load_points(project.settings.get("analog_points", []))

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

    def _on_accept(self):
        points, error = self._collect_points()
        if error:
            QMessageBox.critical(self, "Nieprawidłowe dane", error)
            return
        self._result_points = points
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
