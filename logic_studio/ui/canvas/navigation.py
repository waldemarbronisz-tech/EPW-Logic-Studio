"""Canvas navigation helpers — "jump to and briefly pulse-highlight a
block" — factored out of SignalsPanel (feat/signal-crossref §3.1) so a
SECOND caller (BlockItem's own context menu, for jumping directly between
blocks that share the same signal reference) doesn't have to duplicate it.
Free functions, not tied to any particular widget: all they need is the
scene, the view, and a block uuid.
"""
from PySide6.QtGui import QPen, QColor
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QGraphicsRectItem


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
    end."""
    rect = item.sceneBoundingRect().adjusted(-4, -4, 4, 4)
    overlay = QGraphicsRectItem(rect)
    overlay.setPen(QPen(QColor(255, 180, 0), 3))
    overlay.setBrush(Qt.NoBrush)
    overlay.setZValue(1000)
    scene.addItem(overlay)

    timer = QTimer()
    state = {"ticks": 0}

    def _toggle():
        try:
            state["ticks"] += 1
            overlay.setVisible(not overlay.isVisible())
            if state["ticks"] >= cycles:
                timer.stop()
                scene.removeItem(overlay)
        except RuntimeError:
            # The overlay (or its scene) was already destroyed out from
            # under this pulse — e.g. the project/window was closed
            # before the ~1s animation finished. Nothing left to clean
            # up; just stop ticking.
            timer.stop()

    timer.timeout.connect(_toggle)
    # Kept alive on the overlay item itself — nothing else holds a
    # reference to `timer`, and the overlay stays alive (owned by the
    # scene) for exactly as long as the timer needs to keep firing.
    overlay._pulse_timer = timer
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
