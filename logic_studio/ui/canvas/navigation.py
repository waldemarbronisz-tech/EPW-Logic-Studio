"""Canvas navigation helpers — "jump to and briefly pulse-highlight a
block" — factored out of SignalsPanel (feat/signal-crossref §3.1) so a
SECOND caller (BlockItem's own context menu, for jumping directly between
blocks that share the same signal reference) doesn't have to duplicate it.
Free functions, not tied to any particular widget: all they need is the
scene, the view, and a block uuid.
"""
from PySide6.QtGui import QPen, QColor
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGraphicsRectItem

from logic_studio.ui.qt_lifetime import create_owned_timer


def find_block_item(scene, block_uuid):
    from logic_studio.ui.canvas.block_item import BlockItem
    for it in scene.items():
        if isinstance(it, BlockItem) and it.logic_block.uuid == block_uuid:
            return it
    return None


def pulse_highlight(scene, item, cycles: int = 8, interval_ms: int = 125):
    """§3.1: "podświetla pulsowaniem przez około sekundę" — a temporary
    overlay rectangle flashed on/off `cycles` times (~1s total at the
    default interval), added directly to the scene and removed at the
    end.

    fix/qtimer-lifetime: this used to build a bare, ownerless QTimer()
    kept alive only by a Python attribute stashed on `overlay`, guarded
    by a try/except RuntimeError around the callback. That caught the
    common case (Qt raising cleanly on a stale wrapper) but not the one
    that actually took CI down: Qt is not guaranteed to raise a
    catchable exception when a timer this stale touches a destroyed
    QGraphicsItem — it can abort the process instead, which no
    try/except can intercept. create_owned_timer() fixes this at the
    root: `scene` is a real QObject, so it owns the timer outright
    (destroyed automatically along with the scene), and `overlay` — a
    QGraphicsItem, not a QObject, so it can never be a Qt parent — is
    instead checked with shiboken6.isValid() before every tick via
    `guard`, covering the scene.clear() case (item gone, scene very
    much alive) a Qt parent alone cannot."""
    rect = item.sceneBoundingRect().adjusted(-4, -4, 4, 4)
    overlay = QGraphicsRectItem(rect)
    overlay.setPen(QPen(QColor(255, 180, 0), 3))
    overlay.setBrush(Qt.NoBrush)
    overlay.setZValue(1000)
    scene.addItem(overlay)

    state = {"ticks": 0}

    def _toggle():
        state["ticks"] += 1
        overlay.setVisible(not overlay.isVisible())
        if state["ticks"] >= cycles:
            timer.stop()
            scene.removeItem(overlay)

    timer = create_owned_timer(scene, _toggle, guard=(overlay,))
    timer.start(interval_ms)


def jump_to_block(scene, view, block_uuid):
    """Selects, centers the view on, and pulse-highlights the block with
    this uuid. Returns the BlockItem, or None if scene/view aren't ready
    or no such block exists on the canvas right now."""
    if scene is None or view is None:
        return None
    item = find_block_item(scene, block_uuid)
    if item is None:
        return None
    scene.clearSelection()
    item.setSelected(True)
    view.centerOn(item)
    pulse_highlight(scene, item)
    return item
