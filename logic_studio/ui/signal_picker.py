"""feat/internal-bits §6 — SignalPickerDialog, modeled on eTango Studio's
"Wybór bitu dla logiki": one dialog handles every signal-typed property
("Bit"/"Sygnał"/"Address" on virtual.*/internal.reg_*/system.signal), with
a `value_type` filter (BOOL/REAL) so a context that can only use one type
never even shows the other.
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QLineEdit, QPushButton, QDialogButtonBox, QComboBox, QCheckBox,
    QFormLayout, QMessageBox
)
from PySide6.QtCore import Qt

SIGNAL_ID_ROLE = Qt.UserRole
KIND_ROLE = Qt.UserRole + 1  # "physical" | "internal" | "system" — for filtering/accept logic


class _NewInternalSignalDialog(QDialog):
    """§6.6: add a registry entry without leaving SignalPickerDialog."""

    def __init__(self, value_type: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Nowy sygnał wewnętrzny")
        self.entry = None

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.type_combo = QComboBox()
        self.type_combo.addItems(["BOOL", "REAL"])
        self.type_combo.setCurrentText(value_type)
        self.retentive_check = QCheckBox()
        self.description_edit = QLineEdit()
        self.label_edit = QLineEdit()
        self.category_edit = QLineEdit()
        form.addRow("Nazwa", self.name_edit)
        form.addRow("Typ", self.type_combo)
        form.addRow("Trwały (retentive)", self.retentive_check)
        form.addRow("Opis", self.description_edit)
        form.addRow("Etykieta", self.label_edit)
        form.addRow("Kategoria", self.category_edit)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_accept(self):
        from logic_studio.core.internal_bits import validate_internal_bit_name
        name = self.name_edit.text().strip()
        error = validate_internal_bit_name(name)
        if error:
            QMessageBox.critical(self, "Nieprawidłowa nazwa", error)
            return
        self.entry = {
            "name": name,
            "type": self.type_combo.currentText(),
            "retentive": self.retentive_check.isChecked(),
            "description": self.description_edit.text(),
            "label": self.label_edit.text(),
            "category": self.category_edit.text(),
        }
        self.accept()


class SignalPickerDialog(QDialog):
    def __init__(self, project, value_type: str = "BOOL", parent=None, sections=("physical", "internal", "system")):
        """`value_type`: "BOOL"/"REAL" filters every section to that type;
        None shows both (used for system.signal's "Sygnał", which can
        point at either). `sections` restricts which of the three §6.3
        top-level sections are populated at all — system.signal has no use
        for "Wejścia i wyjścia fizyczne"/"Sygnały wewnętrzne", so its
        picker passes sections=("system",)."""
        super().__init__(parent)
        self.project = project
        self.value_type = value_type
        self.sections = sections
        self._chosen_id = None
        self.setWindowTitle("Wybór sygnału")
        self.resize(640, 480)

        layout = QVBoxLayout(self)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Szukaj...")
        self.search_edit.textChanged.connect(self._apply_filter)
        layout.addWidget(self.search_edit)

        # §6.2: two-level tree, three columns — description first (main
        # column, per eTango), technical id in the middle, label on the
        # right.
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Opis", "Nazwa sygnału", "Etykieta"])
        self.tree.setColumnWidth(0, 280)
        self.tree.setColumnWidth(1, 180)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.tree)

        new_signal_row = QHBoxLayout()
        self.new_signal_btn = QPushButton("Nowy sygnał wewnętrzny...")
        self.new_signal_btn.clicked.connect(self._create_new_signal)
        new_signal_row.addWidget(self.new_signal_btn)
        new_signal_row.addStretch()
        layout.addLayout(new_signal_row)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.ok_button = buttons.button(QDialogButtonBox.Ok)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._populate()
        self.tree.itemSelectionChanged.connect(self._update_ok_enabled)
        self._update_ok_enabled()

    # ---- population ---------------------------------------------------------

    def _populate(self):
        self.tree.clear()
        from logic_studio.core.device_model import DeviceModel

        # §6.3, section 1: physical IO — sections are visually separated
        # top-level nodes since they carry a completely different character
        # (project-defined vs. platform contract).
        if "physical" in self.sections:
            phys_root = QTreeWidgetItem(self.tree, ["Wejścia i wyjścia fizyczne"])
            if self.value_type in (None, "BOOL"):
                for addr in DeviceModel.get_ela_addresses():
                    self._add_leaf(phys_root, "Wejście cyfrowe (ELA)", addr, "", addr, "physical")
                for addr in DeviceModel.get_ada_addresses():
                    self._add_leaf(phys_root, "Wyjście cyfrowe (ADA)", addr, "", addr, "physical")
            if self.value_type in (None, "REAL"):
                for point in DeviceModel.get_analog_points(self.project):
                    self._add_leaf(
                        phys_root, point.get("name", "") or point.get("address", ""),
                        point.get("address", ""), point.get("unit", ""),
                        point.get("address", ""), "physical",
                    )

        # §6.3, section 2: internal signals, grouped by their own "category".
        if "internal" in self.sections:
            internal_root = QTreeWidgetItem(self.tree, ["Sygnały wewnętrzne"])
            by_category = {}
            for entry in DeviceModel.get_internal_bits(self.project, type_filter=self.value_type):
                cat = entry.get("category") or "(bez kategorii)"
                by_category.setdefault(cat, []).append(entry)
            for cat in sorted(by_category):
                cat_item = QTreeWidgetItem(internal_root, [cat])
                for entry in by_category[cat]:
                    self._add_leaf(
                        cat_item, entry.get("description", ""), entry.get("name", ""),
                        entry.get("label", ""), entry.get("name", ""), "internal",
                    )

        # §6.3, section 3: fixed system-signal catalog.
        if "system" in self.sections:
            from logic_studio.core import system_signals
            sys_root = QTreeWidgetItem(self.tree, ["Sygnały systemowe"])
            for cat in system_signals.get_categories():
                matching = [s for s in cat["signals"] if self.value_type is None or s["type"] == self.value_type]
                if not matching:
                    continue
                cat_item = QTreeWidgetItem(sys_root, [cat["name"]])
                for sig in matching:
                    self._add_leaf(cat_item, sig["description"], sig["id"], sig.get("label", ""), sig["id"], "system")

        self.tree.expandAll()

    def _add_leaf(self, parent, description, name, label, signal_id, kind):
        item = QTreeWidgetItem(parent, [description, name, label])
        item.setData(0, SIGNAL_ID_ROLE, signal_id)
        item.setData(0, KIND_ROLE, kind)
        return item

    # ---- filtering (§6.5) -----------------------------------------------------

    def _apply_filter(self, text):
        text = text.strip().lower()
        for i in range(self.tree.topLevelItemCount()):
            root = self.tree.topLevelItem(i)
            root_visible = self._filter_subtree(root, text)
            root.setHidden(not root_visible)

    def _filter_subtree(self, item, text) -> bool:
        """Returns True if `item` (or any descendant) should stay visible.
        A leaf (has SIGNAL_ID_ROLE data) matches if `text` appears in any
        of its three columns; a category/section node is visible if any
        child is."""
        if item.data(0, SIGNAL_ID_ROLE) is not None:
            if not text:
                item.setHidden(False)
                return True
            haystack = " ".join(item.text(c) for c in range(3)).lower()
            visible = text in haystack
            item.setHidden(not visible)
            return visible

        any_visible = False
        for i in range(item.childCount()):
            child = item.child(i)
            if self._filter_subtree(child, text):
                any_visible = True
        item.setHidden(not any_visible)
        return any_visible

    # ---- selection ------------------------------------------------------------

    def _selected_leaf(self):
        items = self.tree.selectedItems()
        if not items:
            return None
        item = items[0]
        return item if item.data(0, SIGNAL_ID_ROLE) is not None else None

    def _update_ok_enabled(self):
        self.ok_button.setEnabled(self._selected_leaf() is not None)

    def _on_item_double_clicked(self, item, column):
        if item.data(0, SIGNAL_ID_ROLE) is not None:
            self.tree.setCurrentItem(item)
            self._on_accept()

    def _try_accept_item(self, item):
        if item.data(0, SIGNAL_ID_ROLE) is not None:
            self._on_accept()

    def _on_accept(self):
        leaf = self._selected_leaf()
        if leaf is None:
            return
        self._chosen_id = leaf.data(0, SIGNAL_ID_ROLE)
        self.accept()

    def selected_signal_id(self):
        """The chosen identifier — an "Address" for physical IO, an
        internal-bit registry NAME (not the M.-prefixed id — that's
        resolved from the name at compile/display time, see §1.2/§2) for
        internal signals, or a system-catalog id. None if the dialog was
        cancelled or nothing was ever selected."""
        return self._chosen_id

    # ---- §6.6: add a registry entry without leaving the dialog ---------------

    def _create_new_signal(self):
        sub = _NewInternalSignalDialog(self.value_type, parent=self)
        if sub.exec() != QDialog.Accepted or sub.entry is None:
            return

        from logic_studio.core.internal_bits import validate_internal_bits_registry
        entries = list(self.project.settings.get("internal_bits", []))
        new_lname = sub.entry["name"].lower()
        if any(e.get("name", "").lower() == new_lname for e in entries):
            QMessageBox.critical(self, "Duplikat nazwy", f"Sygnał '{sub.entry['name']}' już istnieje w rejestrze.")
            return

        entries.append(sub.entry)
        errors = validate_internal_bits_registry(entries)
        if errors:
            QMessageBox.critical(self, "Nieprawidłowy wpis", "\n".join(errors))
            return

        self.project.settings["internal_bits"] = entries
        self._populate()

        # Re-select the freshly created entry so the engineer can just hit OK.
        def _find_and_select(item):
            if item.data(0, KIND_ROLE) == "internal" and item.text(1) == sub.entry["name"]:
                self.tree.setCurrentItem(item)
                return True
            for i in range(item.childCount()):
                if _find_and_select(item.child(i)):
                    return True
            return False

        for i in range(self.tree.topLevelItemCount()):
            if _find_and_select(self.tree.topLevelItem(i)):
                break
