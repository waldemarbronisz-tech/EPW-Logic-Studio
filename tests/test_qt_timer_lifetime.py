"""fix/qtimer-lifetime — the mechanism (ui/qt_lifetime.create_owned_timer),
its audit test, and guardian tests reproducing the exact shape of crash
that took CI down: a timer still ticking when the object(s) its callback
touches get destroyed out from under it.

See ui/qt_lifetime.py's own module docstring for the full write-up of
WHY a try/except RuntimeError around a stale callback was not enough —
short version: Qt is not guaranteed to turn a stale-object touch into a
catchable Python exception; sometimes it aborts the whole process
instead, and no amount of try/except in Python can intercept that.
"""
import ast
from pathlib import Path

import pytest
import shiboken6
from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication, QGraphicsRectItem, QGraphicsScene

from logic_studio.blocks import register_builtin_blocks
from logic_studio.ui.qt_lifetime import create_owned_timer
from logic_studio.ui.canvas.navigation import pulse_highlight

register_builtin_blocks()


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ============================================================================
# §4.2 — audit test: no direct QTimer()/QTimer.singleShot() outside the one
# sanctioned factory.
# ============================================================================

_SRC_ROOT = Path(__file__).resolve().parent.parent / "logic_studio"
_FACTORY_FILE = (_SRC_ROOT / "ui" / "qt_lifetime.py").resolve()

# No exceptions today -- every call site this project had (navigation.py,
# signals.py, main_window.py) was migrated to create_owned_timer() as part
# of this same PR. If a future change genuinely needs one, add its path
# here, explicitly, with a comment justifying it -- per this test's own
# purpose, an exception must never be silent.
_ALLOWED_EXTRA_FILES = frozenset()


def _qtimer_call_lines(path: Path) -> list:
    """Uses ast, not a text/regex search, specifically so a *mention* of
    "QTimer(" in a comment or docstring (this test's own file, or
    navigation.py's fix/qtimer-lifetime writeup) is never mistaken for an
    actual call."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    lines = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "QTimer":
            lines.append(node.lineno)
        elif isinstance(func, ast.Attribute) and func.attr == "singleShot":
            target = func.value
            if (isinstance(target, ast.Name) and target.id == "QTimer") or (
                isinstance(target, ast.Attribute) and target.attr == "QTimer"
            ):
                lines.append(node.lineno)
    return lines


def _all_source_files():
    return sorted(_SRC_ROOT.rglob("*.py"))


@pytest.mark.parametrize(
    "path", _all_source_files(),
    ids=lambda p: str(p.relative_to(_SRC_ROOT)).replace("\\", "/"),
)
def test_no_direct_qtimer_construction_outside_the_sanctioned_factory(path):
    resolved = path.resolve()
    if resolved == _FACTORY_FILE or resolved in _ALLOWED_EXTRA_FILES:
        pytest.skip("sanctioned QTimer() construction site")
    violations = _qtimer_call_lines(path)
    assert violations == [], (
        f"{path}: direct QTimer construction / QTimer.singleShot at line(s) "
        f"{violations} -- use logic_studio.ui.qt_lifetime.create_owned_timer() "
        "instead (see that module's docstring)."
    )


# ============================================================================
# fix/wire-labels-and-project-integrity §C1.1 — the SAME disease, other Qt
# classes with their own independent lifecycle. create_owned_timer() only
# ever covers QTimer specifically; none of the classes below are used
# ANYWHERE in this codebase today (confirmed by this test itself, not just
# a one-off grep) — this closed, currently-empty list exists so the
# instant one of them IS introduced, whoever adds it is forced to
# consciously decide how its lifetime is managed (a QThread outliving the
# window that started it is a far more serious version of the exact same
# bug fix/qtimer-lifetime closed for QTimer — a stuck background thread,
# not just a stray callback) rather than it slipping in unnoticed the way
# the original bare QTimer() in pulse_highlight() did.
# ============================================================================

_OTHER_LIFECYCLE_CLASSES = (
    "QThread", "QPropertyAnimation", "QTimeLine", "QMovie",
    "QSequentialAnimationGroup", "QParallelAnimationGroup",
    "QVariantAnimation", "QAbstractAnimation",
)


def _lifecycle_class_call_lines(path: Path) -> dict:
    """Same ast-based approach as _qtimer_call_lines() (a *mention* in a
    comment/docstring — this very file's own, included — must never be
    mistaken for a real call): returns {class_name: [lineno, ...]} for
    every direct `ClassName(...)` construction found."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    hits = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = None
        if isinstance(func, ast.Name):
            name = func.id
        elif isinstance(func, ast.Attribute):
            name = func.attr
        if name in _OTHER_LIFECYCLE_CLASSES:
            hits.setdefault(name, []).append(node.lineno)
    return hits


@pytest.mark.parametrize(
    "path", _all_source_files(),
    ids=lambda p: str(p.relative_to(_SRC_ROOT)).replace("\\", "/"),
)
def test_no_other_qt_lifecycle_object_used_anywhere_yet(path):
    """§C1.1: confirms today's audit finding (none of QThread/
    QPropertyAnimation/QTimeLine/QMovie/QSequentialAnimationGroup/
    QParallelAnimationGroup/QVariantAnimation/QAbstractAnimation are used
    ANYWHERE in logic_studio/) stays true — and fails loudly, by class
    name and line number, the moment one is introduced without a
    corresponding, deliberate update to this test (and, expected
    alongside it, a real answer for how that object's lifetime is
    managed — the conversation this test exists to force)."""
    hits = _lifecycle_class_call_lines(path)
    assert hits == {}, (
        f"{path}: found direct construction of {sorted(hits)} — none of "
        "these Qt classes with their own independent lifecycle (a "
        "background thread, a running animation) were used anywhere in "
        "this codebase as of fix/wire-labels-and-project-integrity §C1. "
        "Before using one here, decide explicitly how its lifetime is "
        "bounded (owner, explicit stop on teardown, guard against a "
        "destroyed target) — see ui/qt_lifetime.py's own docstring for "
        "why this matters — then update this test's own expectations."
    )


# ============================================================================
# create_owned_timer() itself
# ============================================================================

def test_rejects_a_non_qobject_owner():
    with pytest.raises(TypeError):
        create_owned_timer(object(), lambda: None)

def test_fires_the_callback_while_owner_and_guards_are_alive():
    _app()
    owner = QObject()
    calls = []
    timer = create_owned_timer(owner, lambda: calls.append(1), single_shot=True)
    timer.start(0)
    QApplication.processEvents()
    assert calls == [1]

def test_bound_method_callback_is_resolved_dynamically_not_snapshotted():
    """Regression test for a real bug found while building this factory:
    the first version passed `callback` straight into a Python closure,
    which captures it BY VALUE -- silently different from what a direct
    `timer.timeout.connect(owner.some_method)` does, which PySide
    resolves dynamically against the CURRENT `owner.some_method`
    attribute on every emission (verified directly against bare Qt
    below, and relied on by
    tests/test_signals_panel.py::test_repeated_requests_coalesce_into_one_rebuild,
    which monkey-patches `panel._rebuild` to instrument it). A frozen
    snapshot would silently keep calling the ORIGINAL method forever."""
    _app()

    class _Owner(QObject):
        def method(self):
            calls.append("original")

    owner = _Owner()
    calls = []
    timer = create_owned_timer(owner, owner.method, single_shot=True)

    def _replacement():
        calls.append("replacement")
    owner.method = _replacement

    timer.start(0)
    QApplication.processEvents()

    assert calls == ["replacement"]

def test_timer_is_destroyed_along_with_its_owner():
    """The ordinary case create_owned_timer() relies on for everything
    that doesn't need an explicit `guard`: real Qt parent-child ownership
    means the timeout signal simply cannot fire again once `owner` is
    gone -- no guard check even has a chance to run."""
    _app()
    owner = QObject()
    calls = []
    timer = create_owned_timer(owner, lambda: calls.append(1))
    timer.start(1000)  # long enough it would not fire on its own below
    assert shiboken6.isValid(timer)

    # Immediate, synchronous destruction -- deleteLater()'s DeferredDelete
    # event is loop-level-sensitive and isn't reliably drained by a bare
    # processEvents() outside a real exec() loop (confirmed directly: it
    # is not, in this Qt/PySide combination). shiboken6.delete() destroys
    # `owner` right now, on the spot, exercising the exact guarantee this
    # test cares about -- Qt's parent-child cascade -- without depending
    # on the event queue at all.
    shiboken6.delete(owner)

    assert not shiboken6.isValid(timer)
    assert calls == []

def test_guard_object_going_invalid_stops_the_timer_without_calling_back():
    """The case a Qt parent CANNOT cover: `guard` is something that isn't
    even a QObject (a QGraphicsItem, exactly like pulse_highlight's
    overlay) and can be destroyed independently of `owner`. scene.clear()
    (not scene.removeItem() -- that only detaches an item, handing its
    ownership back to Python; it does NOT delete the underlying C++
    object) is exactly how pulse_highlight's own overlay can go away
    while the scene it belongs to lives on."""
    _app()
    scene = QGraphicsScene()
    item = QGraphicsRectItem(0, 0, 10, 10)
    scene.addItem(item)

    calls = []
    timer = create_owned_timer(scene, lambda: calls.append(1), guard=(item,))
    timer.setSingleShot(False)

    scene.clear()  # deletes `item`'s C++ object; `scene` itself lives on
    assert not shiboken6.isValid(item)

    timer.start(0)
    QApplication.processEvents()
    QApplication.processEvents()

    assert calls == []  # never touched the gone item
    assert not timer.isActive()  # stopped itself, not left ticking forever
    assert shiboken6.isValid(timer)  # but NOT destroyed -- `scene` (its owner) is still alive


# ============================================================================
# §5.3 guardian tests — reproduce the EXACT shape of the CI crash: a timer
# still pending when the thing(s) it touches are destroyed immediately
# after, followed by however many processEvents() calls it takes to give a
# leftover timer the chance to fire into nothing. This is precisely what
# tests/test_canvas_navigation.py's test_jump_to_block_* tests were already
# doing by accident (jump_to_block()'s default ~1s pulse animation, closed
# immediately after) -- these make it deliberate and immediate instead of
# relying on however many OTHER tests' worth of wall-clock time it takes
# the next pytest-qt teardown to stumble into it.
# ============================================================================

def _make_window(qsettings):
    from logic_studio.ui.main_window import MainWindow
    window = MainWindow(settings=qsettings)
    window.scene.clear()
    return window


def test_pulse_highlight_survives_its_scene_being_cleared_immediately(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    from logic_studio.ui.canvas.block_item import BlockItem
    item = next(i for i in window.scene.items() if isinstance(i, BlockItem))

    pulse_highlight(window.scene, item)  # default cycles=8, interval_ms=125 -- ~1s of ticks left pending
    window.scene.clear()  # the overlay is gone; the scene itself lives on

    # Enough processEvents() calls to cover every pending tick the pulse
    # would have made had nothing interrupted it -- if the old ownerless
    # timer + try/except design were still in place, one of these is
    # exactly where CI's abort happened.
    for _ in range(10):
        QApplication.processEvents()

    window.is_dirty = False
    window.close()

def test_pulse_highlight_survives_its_window_being_closed_immediately(qsettings):
    """The literal shape of test_canvas_navigation.py's
    test_jump_to_block_selects_and_returns_the_item -- jump (which pulse-
    highlights), then close the whole window without waiting out the
    animation. MainWindow.closeEvent() calls scene.clear() itself (its own
    "Clean up C++ items to prevent pointer crash on exit" comment), which
    is exactly the moment a leftover unowned timer used to be able to
    fire into a now-deleted overlay."""
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    window.scene.add_block_from_library("logic.not", 300, 0)
    target = window.project.blocks[1]

    from logic_studio.ui.canvas.navigation import jump_to_block
    jump_to_block(window.scene, window.view, target.uuid)

    window.is_dirty = False
    window.close()

    for _ in range(10):
        QApplication.processEvents()

def test_signals_panel_debounced_rebuild_survives_immediate_destruction(qapp, qsettings, qt_cleanup):
    """§5.3's own named scenario: create a panel with a deferred rebuild,
    request one, immediately destroy the panel, process events, confirm
    nothing explodes. Uses conftest.py's new `qapp`/`qt_cleanup` fixtures
    (§5.2) rather than this file's own `_app()` helper + manual
    deleteLater()/gc.collect()/processEvents() dance, as an example of
    the pattern new tests should prefer."""
    from logic_studio.ui.panels.signals import SignalsPanel
    from logic_studio.core.project import Project

    panel = qt_cleanup(SignalsPanel(settings=qsettings))
    panel.project = Project()
    panel.request_refresh()  # starts the 200ms debounce timer

def test_sim_timer_survives_window_close_while_running(qsettings):
    """MainWindow.sim_timer, started directly (bypassing start_simulation()'s
    compile step, irrelevant to this lifetime question) then the window
    closed mid-tick -- stop_simulation() (closeEvent's own first call)
    already stops it explicitly, this just confirms that holds even with
    events processed afterwards."""
    _app()
    window = _make_window(qsettings)
    window.sim_timer.start(5)

    window.is_dirty = False
    window.close()

    for _ in range(10):
        QApplication.processEvents()

    assert not window.sim_timer.isActive()
