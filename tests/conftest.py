import pytest
from PySide6.QtCore import QSettings


@pytest.fixture
def qsettings(tmp_path):
    """Scratch, file-backed QSettings for any test that constructs a
    MainWindow (which owns tree-expand-state, toolbar style, and recently-
    used block history — feat/block-rendering-library §4/§5). Without this,
    QSettings("BroniszLabs", "EPW Logic Studio") is NativeFormat on Windows,
    i.e. the real user registry (HKCU) — tests must never write there."""
    return QSettings(str(tmp_path / "test_settings.ini"), QSettings.IniFormat)
