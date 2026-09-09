"""fix/qtimer-lifetime — the ONE place in this codebase allowed to
construct a QTimer. See ARCHITECTURE.md's "Cykl życia obiektów Qt"
section for the full write-up; this module docstring is the short
version.

THE RULE: a QTimer must never outlive the object(s) its own callback
touches. When a timer that DOES outlive them eventually fires, Qt is
not always able to turn that into a catchable Python RuntimeError —
sometimes the process segfaults or aborts instead, and no try/except
inside the callback can catch a fault in the C++ runtime itself. A
try/except RuntimeError around a stale callback (as ui/canvas/
navigation.py's pulse_highlight() used to have) only ever masked the
SYMPTOM on the runs where Qt happened to raise cleanly — the disease
was always "this timer has no owner," and on the runs where Qt didn't
raise cleanly, the whole process went down with it.

This is the SEVENTH occurrence of "an element added without covering
every path that needs to know about it" this project has hit — six
earlier ones were FIELDS missing from a serialization/clone/diff path
(see test_pin_serialization.py's own docstring for the first few, and
core/state_diff.py's for the sixth). This one is a Qt OBJECT created
without an owner and without a liveness check on what it touches. The
fix follows the same shape as those: a single enforced mechanism
(there, SERIALIZED_FIELDS; here, create_owned_timer()) plus an
audit test that fails the moment anyone bypasses it
(tests/test_qt_timer_lifetime.py).

Two things every timer in this codebase needs, both provided here:

1. AN OWNER: parenting the QTimer to a real QObject means Qt itself
   stops and deletes it the instant that QObject is destroyed — the
   timeout signal simply cannot fire again afterwards. This alone is
   enough for a callback that only ever touches its own owner (the
   common case — see ui/panels/signals.py's debounced rebuild timer,
   ui/main_window.py's simulation clock).

2. A LIVENESS GUARD: some callbacks need to touch OTHER objects that
   the owner does not itself destroy in lockstep with — most notably a
   QGraphicsItem, which is not a QObject at all and so can never be
   given a Qt parent to begin with. This is exactly the shape of
   pulse_highlight(): the timer's natural owner is the QGraphicsScene,
   but what each tick actually touches is the transient highlight
   overlay it drew ON that scene, which can be individually removed
   (scene.clear() included) while the scene object itself lives on.
   `guard` objects are checked with shiboken6.isValid() — a safe,
   documented liveness check that consults shiboken's own bookkeeping
   instead of dereferencing the (possibly already-freed) C++ object —
   before every single invocation of the real callback. The timer
   stops itself the moment a guarded object is found gone, instead of
   ticking `cycles` more times into nothing.
"""
import shiboken6
from PySide6.QtCore import QObject, QTimer


def create_owned_timer(owner: QObject, callback, *, guard=(), single_shot: bool = False) -> QTimer:
    """The one sanctioned way to create a QTimer in this codebase.

    `owner` MUST be a real QObject — it becomes the timer's Qt parent,
    so Qt stops and deletes the timer automatically when `owner` is
    destroyed, and it is always included in the liveness guard (there
    is nothing left worth calling `callback` for once `owner` itself
    is gone, even with no extra `guard` objects). Pass any additional
    non-owner objects the callback touches — typically a QGraphicsItem
    — via `guard`; each one is re-checked with shiboken6.isValid()
    before every tick.

    Returns the QTimer, not yet started — call .start(interval_ms)
    (or, for single_shot=True, .start(interval_ms) once) exactly as
    with a plain QTimer.
    """
    if not isinstance(owner, QObject):
        raise TypeError(
            f"create_owned_timer() requires a real QObject owner, got {owner!r} — "
            "an unowned QTimer is exactly the bug this function exists to make "
            "impossible. See logic_studio/ui/qt_lifetime.py's module docstring."
        )

    timer = QTimer(owner)
    timer.setSingleShot(single_shot)

    guarded_objects = (owner,) + tuple(guard)

    # If `callback` is a bound method (the common case: create_owned_timer(
    # self, self._rebuild, ...)), re-resolve it from the instance by name on
    # every tick instead of calling the bound-method object captured here —
    # this matches what a direct `timer.timeout.connect(self._rebuild)`
    # would have done (PySide resolves a bound-method connection dynamically
    # against the current attribute, not a frozen snapshot: reassigning
    # `self._rebuild` — exactly what
    # tests/test_signals_panel.py::test_repeated_requests_coalesce_into_one_rebuild
    # does to instrument it — changes what the NEXT tick calls). Capturing
    # `callback` by value here would silently break that and call the
    # original method forever instead — a real regression this fixed
    # during development. A plain function/lambda (pulse_highlight's
    # `_toggle`, this module's own tests) was never dynamically
    # re-dispatchable in the first place and is simply called as-is.
    method_owner = getattr(callback, "__self__", None)
    method_name = getattr(callback, "__name__", None)
    if method_owner is not None and method_name is not None:
        def _invoke():
            getattr(method_owner, method_name)()
    else:
        def _invoke():
            callback()

    def _guarded_tick():
        if not all(shiboken6.isValid(obj) for obj in guarded_objects):
            # One of the objects this callback needs has already been
            # destroyed — stop ticking rather than fire uselessly (or
            # dangerously) again. Unreachable for `owner` itself in the
            # common case (Qt would already have deleted `timer` along
            # with `owner`, so this closure could not even run) — this
            # branch exists for the `guard` objects a Qt parent can't
            # protect, per the module docstring's QGraphicsItem example.
            timer.stop()
            return
        _invoke()

    timer.timeout.connect(_guarded_tick)
    return timer
