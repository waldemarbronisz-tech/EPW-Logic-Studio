"""fix/wire-labels-and-project-integrity §A3.3/§A3.4 — the one dialog
every "Nadaj etykietę.../Zamień na odnośnik/Dodaj odnośnik..." context
menu action opens, so completion/validation/similarity-warning logic
lives in exactly one place rather than being reimplemented per menu.
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QCompleter,
)
from PySide6.QtCore import Qt

# §A3.4: forbidden characters -- a label never reaches the runtime
# export (compiler/label_merge.py only ever reads it in-process), but
# it DOES get embedded verbatim into compiler error/warning strings
# ("Etykieta 'X' nie ma źródła") and rendered as free text on the
# canvas -- a stray quote or path separator in either is exactly the
# kind of thing that looks like a typo or a rendering bug later.
_FORBIDDEN_CHARS = '"/\\'


def label_validation_error(text: str) -> str | None:
    """None if `text` is an acceptable label (spaces allowed, per
    §A3.4 — "Wyl. Q1"/"Wyl. Q2" are legitimate), else a short message
    naming which character is the problem."""
    for ch in _FORBIDDEN_CHARS:
        if ch in text:
            return f"Etykieta nie może zawierać znaku {ch!r}."
    return None


def _edit_distance_at_most_one(a: str, b: str) -> bool:
    """True if `a` and `b` differ by at most one character edit
    (insertion, deletion, or substitution) -- deliberately NOT a full
    Levenshtein implementation; §A3.3 only ever needs "at most 1", and
    that's checkable in O(len) instead of O(len_a * len_b)."""
    if a == b:
        return True
    len_a, len_b = len(a), len(b)
    if abs(len_a - len_b) > 1:
        return False
    if len_a == len_b:
        # Substitution: exactly one differing position.
        diffs = sum(1 for x, y in zip(a, b) if x != y)
        return diffs == 1
    # Insertion/deletion: walk both strings, allow exactly one skip.
    shorter, longer = (a, b) if len_a < len_b else (b, a)
    i = j = skipped = 0
    while i < len(shorter) and j < len(longer):
        if shorter[i] == longer[j]:
            i += 1
            j += 1
        else:
            skipped += 1
            if skipped > 1:
                return False
            j += 1
    return True


def find_similar_label(text: str, existing_labels) -> str | None:
    """§A3.3: "po zatwierdzeniu nazwy różniącej się od istniejącej
    wyłącznie wielkością liter albo pojedynczym znakiem" — an exact
    case-insensitive match is NOT "similar", it's the SAME node
    (compiler/label_merge.py's own grouping key) and needs no warning;
    only a genuinely near-miss (likely typo) is worth surfacing. Never
    blocks — "Wyl. Q1"/"Wyl. Q2" are one edit apart and both
    legitimate."""
    text_lower = text.strip().lower()
    if not text_lower:
        return None
    for existing in existing_labels:
        existing_lower = existing.lower()
        if existing_lower == text_lower:
            continue  # same node, not "similar" -- see docstring
        if _edit_distance_at_most_one(text_lower, existing_lower):
            return existing
    return None


class LabelNameDialog(QDialog):
    """§A3.3: a QLineEdit with a QCompleter over every label already
    used in the project, matching anywhere in the text (not just a
    prefix) — a typo creates a new, orphaned node (caught at compile
    time by compiler/label_merge.py's "no source"/"no receiver" checks)
    but the completer is what stops most typos before they happen at
    all."""

    def __init__(self, existing_labels, initial: str = "", title: str = "Etykieta", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Nazwa etykiety:"))

        self.edit = QLineEdit(initial)
        # §A3.4: empty by default, no auto-suggestion of an existing name.
        completer = QCompleter(sorted(set(existing_labels)), self)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        self.edit.setCompleter(completer)
        layout.addWidget(self.edit)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #C0392B;")
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)

        button_row = QHBoxLayout()
        button_row.addStretch()
        cancel_btn = QPushButton("Anuluj")
        cancel_btn.clicked.connect(self.reject)
        ok_btn = QPushButton("OK")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self._on_accept)
        button_row.addWidget(cancel_btn)
        button_row.addWidget(ok_btn)
        layout.addLayout(button_row)

    def _on_accept(self):
        error = label_validation_error(self.edit.text())
        if error:
            self.error_label.setText(error)
            self.error_label.setVisible(True)
            return
        self.accept()

    def label_text(self) -> str:
        return self.edit.text().strip()


def prompt_for_label(parent, project, initial: str = "", title: str = "Etykieta"):
    """Opens LabelNameDialog modally. Returns `(text, similar_existing)`
    on OK — `similar_existing` is the near-miss label to warn about
    (§A3.3), or None if there isn't one — or `(None, None)` if the
    dialog was cancelled."""
    existing_labels = sorted({w.label for w in project.wires if w.label})
    dialog = LabelNameDialog(existing_labels, initial, title, parent)
    if dialog.exec() != QDialog.Accepted:
        return None, None
    text = dialog.label_text()
    return text, find_similar_label(text, existing_labels)
