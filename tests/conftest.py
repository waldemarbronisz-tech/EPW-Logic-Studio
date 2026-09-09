import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication


@pytest.fixture
def qsettings(tmp_path):
    """Scratch, file-backed QSettings for any test that constructs a
    MainWindow (which owns tree-expand-state, toolbar style, and recently-
    used block history — feat/block-rendering-library §4/§5). Without this,
    QSettings("BroniszLabs", "EPW Logic Studio") is NativeFormat on Windows,
    i.e. the real user registry (HKCU) — tests must never write there."""
    return QSettings(str(tmp_path / "test_settings.ini"), QSettings.IniFormat)


@pytest.fixture
def qapp():
    """fix/qtimer-lifetime §5.2: the shared replacement for the `_app()`
    helper hand-duplicated near-verbatim at the top of nearly every test
    file in this suite (`QApplication.instance() or QApplication([])`).
    New tests should prefer this fixture over defining their own copy;
    existing files' own `_app()` helpers are left as-is — retrofitting
    every one of the ~60 files that already has one is a separate, much
    larger cleanup than this PR's actual scope, deliberately deferred
    (see this PR's own summary)."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def qt_cleanup():
    """fix/qtimer-lifetime §5.2: register a widget/window for guaranteed
    close() + one processEvents() pass at THIS test's own teardown,
    instead of relying on whatever the NEXT test (or pytest's own global
    per-test event pump, if present) happens to do. This is what would
    have caught tests/test_canvas_navigation.py's test_jump_to_block_*
    tests leaving a ~1s pulse-highlight animation running past the
    test's own end long before it could go on to (mis)behave during some
    unrelated LATER test — see this PR's summary for the real bug that
    shape of leak caused.

    Usage: call the fixture with the widget right after creating it --
    `qt_cleanup(window)` -- teardown is automatic, nothing else to call.
    Prefer this in new tests; existing per-file `_close()` helpers are
    left as-is (see the `qapp` fixture's own docstring on why a project-
    wide retrofit is out of scope here).
    """
    registered = []

    def _register(widget):
        registered.append(widget)
        return widget

    yield _register

    for widget in registered:
        try:
            widget.close()
        except RuntimeError:
            pass  # already gone -- nothing left to close
    app = QApplication.instance()
    if app is not None:
        app.processEvents()
