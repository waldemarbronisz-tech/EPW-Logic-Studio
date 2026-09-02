"""feat/signal-crossref §5 — CSV export of the signals list."""
import csv
import pytest
from PySide6.QtWidgets import QApplication

from logic_studio.blocks import register_builtin_blocks
from logic_studio.blocks.registry import BlockRegistry
from logic_studio.core.project import Project
from logic_studio.core.device_model import DeviceModel
from logic_studio.ui.panels.signals import SignalsPanel

register_builtin_blocks()


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _di(address):
    b = BlockRegistry.create_block("input.di")
    b.properties["Address"] = address
    return b


def _read_csv_rows(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        lines = f.readlines()
    comment, rest = lines[0], lines[1:]
    reader = csv.reader(rest, delimiter=";")
    return comment, list(reader)


def test_export_writes_utf8_bom(tmp_path, qsettings):
    _app()
    p = Project()
    p.settings["name"] = "Test"
    panel = SignalsPanel(settings=qsettings)
    panel.set_project(p)

    path = tmp_path / "out.csv"
    panel.export_csv(str(path))

    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")  # UTF-8 BOM

def test_export_first_line_is_a_comment_with_project_name_and_date(tmp_path, qsettings):
    _app()
    p = Project()
    p.settings["name"] = "Instalacja Testowa"
    panel = SignalsPanel(settings=qsettings)
    panel.set_project(p)

    path = tmp_path / "out.csv"
    panel.export_csv(str(path))

    comment, _rows = _read_csv_rows(path)
    assert comment.startswith("#")
    assert "Instalacja Testowa" in comment
    assert "Filtr zastosowany: nie" in comment

def test_export_header_matches_table_plus_problemy(tmp_path, qsettings):
    _app()
    panel = SignalsPanel(settings=qsettings)
    panel.set_project(Project())

    path = tmp_path / "out.csv"
    panel.export_csv(str(path))

    _comment, rows = _read_csv_rows(path)
    assert rows[0] == ["Stan", "Sygnał", "Typ", "Etykieta", "Zapisuje", "Czyta", "Problemy"]

def test_export_includes_a_real_row(tmp_path, qsettings):
    _app()
    p = Project()
    p.add_block(_di("ELA01.DI01"))
    DeviceModel.set_io_label(p, "ELA01.DI01", "Wyłącznik Q1")
    panel = SignalsPanel(settings=qsettings)
    panel.set_project(p)

    path = tmp_path / "out.csv"
    panel.export_csv(str(path))

    _comment, rows = _read_csv_rows(path)
    data_row = rows[1]
    assert data_row[1] == "ELA01.DI01"
    assert data_row[3] == "Wyłącznik Q1"
    assert data_row[4] == "urządzenie"

def test_export_includes_problem_text_for_flagged_rows(tmp_path, qsettings):
    _app()
    p = Project()
    ghost = BlockRegistry.create_block("virtual.input")
    ghost.properties["Bit"] = "GHOST"
    p.add_block(ghost)
    panel = SignalsPanel(settings=qsettings)
    panel.set_project(p)

    path = tmp_path / "out.csv"
    panel.export_csv(str(path))

    _comment, rows = _read_csv_rows(path)
    data_row = next(r for r in rows[1:] if r[1] == "GHOST")
    assert data_row[0] == "Błąd"
    assert "nie istnieje" in data_row[6]


# ---- §5.2: only visible (filtered) rows are exported -----------------------

def test_export_respects_the_search_filter(tmp_path, qsettings):
    _app()
    p = Project()
    p.add_block(_di("ELA01.DI01"))
    p.add_block(_di("ELA01.DI02"))
    panel = SignalsPanel(settings=qsettings)
    panel.set_project(p)
    panel.search_edit.setText("DI01")

    path = tmp_path / "out.csv"
    panel.export_csv(str(path))

    comment, rows = _read_csv_rows(path)
    signal_ids = [r[1] for r in rows[1:]]
    assert signal_ids == ["ELA01.DI01"]
    assert "Filtr zastosowany: tak" in comment

def test_export_respects_the_only_issues_filter(tmp_path, qsettings):
    _app()
    p = Project()
    p.add_block(_di("ELA01.DI01"))  # clean
    ghost = BlockRegistry.create_block("virtual.input")
    ghost.properties["Bit"] = "GHOST"
    p.add_block(ghost)
    panel = SignalsPanel(settings=qsettings)
    panel.set_project(p)
    panel.only_issues_check.setChecked(True)

    path = tmp_path / "out.csv"
    panel.export_csv(str(path))

    comment, rows = _read_csv_rows(path)
    signal_ids = [r[1] for r in rows[1:]]
    assert signal_ids == ["GHOST"]
    assert "Filtr zastosowany: tak" in comment


# ---- §5.3: Polish characters + semicolon in a label round-trip correctly --

def test_polish_characters_and_semicolon_in_label_round_trip(tmp_path, qsettings):
    """The exact required test: a signal name containing Polish characters
    and a semicolon in its label must be correctly re-parsed by the csv
    module (which must correctly quote the semicolon, since ';' is also
    this file's own field delimiter)."""
    _app()
    p = Project()
    p.settings["internal_bits"] = [
        {"name": "BLOKADA_ZS", "type": "BOOL", "retentive": False, "description": "Ostrzeżenie; wyłącznik główny zwarty"},
    ]
    vi = BlockRegistry.create_block("virtual.input")
    vi.properties["Bit"] = "BLOKADA_ZS"
    p.add_block(vi)
    panel = SignalsPanel(settings=qsettings)
    panel.set_project(p)

    path = tmp_path / "out.csv"
    panel.export_csv(str(path))

    _comment, rows = _read_csv_rows(path)
    data_row = next(r for r in rows[1:] if r[1] == "M.BLOKADA_ZS")
    assert data_row[3] == "Ostrzeżenie; wyłącznik główny zwarty"

def test_export_signal_id_with_polish_characters(tmp_path, qsettings):
    """A signal reference (typo'd Bit name, so it stays unresolved/raw)
    containing Polish diacritics survives the round trip too."""
    _app()
    p = Project()
    vi = BlockRegistry.create_block("virtual.input")
    vi.properties["Bit"] = "BŁĄD_ŹRÓDŁA"
    p.add_block(vi)
    panel = SignalsPanel(settings=qsettings)
    panel.set_project(p)

    path = tmp_path / "out.csv"
    panel.export_csv(str(path))

    _comment, rows = _read_csv_rows(path)
    assert any(r[1] == "BŁĄD_ŹRÓDŁA" for r in rows[1:])
