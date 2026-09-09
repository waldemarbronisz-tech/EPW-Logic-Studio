"""fix/wire-labels-and-project-integrity §A3.3/§A3.4 — logic_studio/ui/label_dialog.py."""
import pytest
from PySide6.QtWidgets import QApplication, QDialog

from logic_studio.ui.label_dialog import (
    label_validation_error, find_similar_label, LabelNameDialog, prompt_for_label,
)
from logic_studio.blocks import register_builtin_blocks
from logic_studio.blocks.registry import BlockRegistry
from logic_studio.core.project import Project
from logic_studio.core.wire import Wire

register_builtin_blocks()


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ---- §A3.4: validation ------------------------------------------------

@pytest.mark.parametrize("text", ['Has"Quote', "Has/Slash", "Has\\Backslash"])
def test_forbidden_characters_are_rejected(text):
    assert label_validation_error(text) is not None

def test_spaces_are_allowed():
    assert label_validation_error("Wyl. Q1") is None

def test_empty_text_is_not_a_validation_error():
    """Empty is a legal (if unhelpful) confirmation -- e.g. "Usuń
    etykietę" reusing the same dialog plumbing with an empty result."""
    assert label_validation_error("") is None


# ---- §A3.3: similarity detection --------------------------------------

def test_exact_case_insensitive_match_is_not_similar():
    """Same node (compiler/label_merge.py's own grouping), not a typo."""
    assert find_similar_label("blokada zs", ["Blokada ZS"]) is None

def test_single_character_difference_is_similar():
    assert find_similar_label("Wyl. Q2", ["Wyl. Q1"]) == "Wyl. Q1"

def test_one_character_inserted_is_similar():
    assert find_similar_label("Blokada", ["Blokad"]) == "Blokad"

def test_one_character_deleted_is_similar():
    assert find_similar_label("Blokad", ["Blokada"]) == "Blokada"

def test_two_character_difference_is_not_similar():
    assert find_similar_label("Completely Different", ["Blokada ZS"]) is None

def test_empty_text_has_no_similar_match():
    assert find_similar_label("", ["Blokada ZS"]) is None

def test_no_existing_labels_means_no_similar_match():
    assert find_similar_label("Anything", []) is None


# ---- LabelNameDialog / prompt_for_label --------------------------------

def test_dialog_rejects_forbidden_character_without_closing():
    _app()
    dialog = LabelNameDialog(existing_labels=[], initial="")
    dialog.edit.setText('Bad"Name')
    dialog._on_accept()
    assert dialog.result() != QDialog.Accepted  # never got to accept()
    assert dialog.error_label.text()  # a message was set, even if not on-screen
    dialog.close()

def test_dialog_accepts_a_valid_name():
    _app()
    dialog = LabelNameDialog(existing_labels=[], initial="")
    dialog.edit.setText("Blokada ZS")
    dialog._on_accept()
    assert dialog.result() == QDialog.Accepted
    assert dialog.label_text() == "Blokada ZS"
    dialog.close()

def test_dialog_starts_empty_by_default_with_no_autofill():
    """§A3.4: "Pole nazwy domyślnie PUSTE, bez podpowiadania z automatu"."""
    _app()
    dialog = LabelNameDialog(existing_labels=["Blokada ZS"], initial="")
    assert dialog.edit.text() == ""
    dialog.close()

def test_prompt_for_label_gathers_existing_labels_from_the_project(qsettings):
    _app()
    p = Project()
    di = BlockRegistry.create_block("input.di")
    p.add_block(di)
    w = Wire()
    w.source_pin = di.outputs[0].uuid
    w.label = "Blokada ZS"
    w.free_end_dest = {"x": 0.0, "y": 0.0}
    assert p.add_wire(w)

    dialog_holder = {}

    def fake_exec(self):
        dialog_holder["labels"] = sorted(self.edit.completer().model().stringList())
        self.edit.setText("Blokada Z1")  # one char off from "Blokada ZS"
        return QDialog.Accepted

    LabelNameDialog.exec = fake_exec
    try:
        text, similar = prompt_for_label(None, p)
    finally:
        del LabelNameDialog.exec

    assert dialog_holder["labels"] == ["Blokada ZS"]
    assert text == "Blokada Z1"
    assert similar == "Blokada ZS"
