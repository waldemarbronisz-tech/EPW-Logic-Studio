"""feat/project-diff — ProjectDiffDialog: a read-only tree view of
core/project_diff.py's compare_projects() output, opened by MainWindow's
File menu ("Porównaj z zapisanym plikiem..."/"Porównaj dwa projekty...").
Qt-thin: calls compare_projects() once at construction and renders
whatever it returns — never touches Project/the block registry, mirrors
core/*.py vs. ui/panels/*.py's usual split elsewhere in this app.
"""
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QTreeWidget, QTreeWidgetItem, QDialogButtonBox

from logic_studio.core.project_diff import summarize, block_label


class ProjectDiffDialog(QDialog):
    def __init__(self, comparison: dict, base_label: str, target_label: str, parent=None):
        """`comparison`: compare_projects()'s own return dict.
        `base_label`/`target_label`: short, human strings identifying
        the two sides being compared (a filename, or "Bieżący stan") —
        purely for the header line, never parsed."""
        super().__init__(parent)
        self.setWindowTitle("Porównanie projektów")
        self.resize(640, 520)

        layout = QVBoxLayout(self)
        header = QLabel(f"<b>{base_label}</b> → <b>{target_label}</b><br>{summarize(comparison)}")
        header.setWordWrap(True)
        layout.addWidget(header)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        layout.addWidget(self.tree)
        self._populate(comparison)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.accept)
        layout.addWidget(buttons)

    def _populate(self, comparison: dict):
        self.tree.clear()

        if comparison["blocks_added"]:
            root = QTreeWidgetItem(self.tree, [f"Dodane bloki ({len(comparison['blocks_added'])})"])
            for b in comparison["blocks_added"]:
                QTreeWidgetItem(root, [f"+ {block_label(b)}  ({b.get('type_id', '')})"])

        if comparison["blocks_removed"]:
            root = QTreeWidgetItem(self.tree, [f"Usunięte bloki ({len(comparison['blocks_removed'])})"])
            for b in comparison["blocks_removed"]:
                QTreeWidgetItem(root, [f"− {block_label(b)}  ({b.get('type_id', '')})"])

        if comparison["blocks_changed"]:
            root = QTreeWidgetItem(self.tree, [f"Zmienione bloki ({len(comparison['blocks_changed'])})"])
            for change in comparison["blocks_changed"]:
                label = change["short_id"] or change["uuid"]
                if change["display_name"]:
                    label = f"{label} — {change['display_name']}"
                block_item = QTreeWidgetItem(root, [label])
                if change["moved"]:
                    QTreeWidgetItem(block_item, ["Przesunięty na kanwie"])
                for fc in change["field_changes"]:
                    QTreeWidgetItem(block_item, [f"{fc['field']}: {fc['old']!r} → {fc['new']!r}"])
                for cc in change["connection_changes"]:
                    for _ in cc["added"]:
                        QTreeWidgetItem(block_item, [f"Pin {cc['pin_name']}: nowe połączenie"])
                    for _ in cc["removed"]:
                        QTreeWidgetItem(block_item, [f"Pin {cc['pin_name']}: usunięte połączenie"])

        if comparison["settings_changes"]:
            root = QTreeWidgetItem(self.tree, [f"Zmiany ustawień ({len(comparison['settings_changes'])})"])
            for sc in comparison["settings_changes"]:
                if sc["old"] is None:
                    text = f"{sc['key']}: dodane"
                elif sc["new"] is None:
                    text = f"{sc['key']}: usunięte"
                else:
                    text = f"{sc['key']}: zmienione"
                QTreeWidgetItem(root, [text])

        if self.tree.topLevelItemCount() == 0:
            QTreeWidgetItem(self.tree, ["Brak różnic"])

        self.tree.expandAll()
