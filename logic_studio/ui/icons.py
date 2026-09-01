"""Every icon in the app, generated procedurally — zero image files in the
repo (feat/block-rendering-library §5). Two entry points:

    block_icon(type_id, size=24) -> QIcon    # library tree / preview panel
    action_icon(name, size=20) -> QIcon      # toolbar actions

Both cache by (key, size) so repeatedly refreshing the library tree or
switching toolbar display mode never re-renders a pixmap that's already been
drawn once.
"""
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QIcon, QPixmap, QPainter, QPen, QBrush, QColor, QPolygonF

from logic_studio.ui.canvas import style, shapes

_block_icon_cache = {}
_action_icon_cache = {}


def _shape_style_for(type_id: str, category: str) -> str:
    """Mirrors BlockItem._determine_shape_style() without constructing a full
    canvas item (and its ports) just to read one field — see block_item.py
    for the canonical, authoritative version this must stay consistent with."""
    if category == "Bramki logiczne":
        if type_id.startswith("logic.buffer"):
            return "BUFFER"
        if type_id.startswith("logic.and"):
            return "AND"
        if type_id.startswith("logic.or"):
            return "OR"
        if type_id.startswith("logic.nand"):
            return "NAND"
        if type_id.startswith("logic.nor"):
            return "NOR"
        if type_id.startswith("logic.xor"):
            return "XOR"
        if type_id.startswith("logic.xnor"):
            return "XNOR"
        if type_id.startswith("logic.not"):
            return "NOT"
        return "GATE_GENERIC"
    if category == "Wejścia / Wyjścia":
        return "IO"
    if category == "Dokumentacja":
        return "DOC"
    return "COMPLEX"


def block_icon(type_id: str, size: int = 24) -> QIcon:
    """Renders a block's canvas shape (via shapes.py — the same drawing code
    the canvas itself uses, so an icon never drifts from what the block
    actually looks like once placed) into a small QIcon."""
    key = (type_id, size)
    if key in _block_icon_cache:
        return _block_icon_cache[key]

    from logic_studio.blocks.registry import BlockRegistry

    block_class = BlockRegistry.get_block_class(type_id)
    icon = QIcon()
    if block_class is not None:
        dummy = block_class()
        shape_style = _shape_style_for(type_id, dummy.category)

        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        margin = max(2, size * 0.12)
        rect = QRectF(margin, margin, size - margin * 2, size - margin * 2)

        from logic_studio.ui.canvas.block_item import GATE_SHAPES
        if shape_style in GATE_SHAPES:
            # No lead lines at icon scale (§ redesign) — 24px has no room for
            # them, and the canvas/icon shape only needs to stay consistent
            # in silhouette, not in pin-lead styling.
            shapes.draw_gate_shape(painter, rect, shape_style, len(dummy.inputs), draw_leads=False)
        elif shape_style == "IO":
            direction = "input" if "input" in type_id else "output"
            shapes.draw_io_shape(painter, rect, direction)
        elif shape_style == "DOC":
            shapes.draw_doc_shape(painter, rect)
        else:
            shapes.draw_complex_shape(painter, rect)
            shapes.draw_complex_icon_pin_marks(painter, rect, len(dummy.inputs), len(dummy.outputs))

        painter.end()
        icon = QIcon(pixmap)

    _block_icon_cache[key] = icon
    return icon


def _new_pixmap(size):
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    return pixmap


def action_icon(name: str, size: int = 20) -> QIcon:
    """Simple, legible pictograms for the main toolbar (§5.4) — this build
    shipped with plain text-only actions and an explicit code comment
    admitting there were no icons; these replace that."""
    key = (name, size)
    if key in _action_icon_cache:
        return _action_icon_cache[key]

    pixmap = _new_pixmap(size)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(style.COLOR_OUTLINE, 1.4))
    painter.setBrush(Qt.NoBrush)

    m = size * 0.18
    rect = QRectF(m, m, size - 2 * m, size - 2 * m)
    cx, cy = size / 2, size / 2

    if name == "new":
        fold = rect.width() * 0.35
        painter.drawRect(QRectF(rect.left(), rect.top(), rect.width(), rect.height()))
        painter.drawLine(QPointF(rect.right() - fold, rect.top()), QPointF(rect.right(), rect.top() + fold))
        painter.drawLine(QPointF(cx, rect.top() + rect.height() * 0.4), QPointF(cx, rect.bottom() - rect.height() * 0.15))
        painter.drawLine(QPointF(rect.left() + rect.width() * 0.25, cy + rect.height() * 0.12),
                          QPointF(rect.right() - rect.width() * 0.25, cy + rect.height() * 0.12))

    elif name == "open":
        painter.drawLine(QPointF(rect.left(), rect.top() + 2), QPointF(rect.left() + rect.width() * 0.4, rect.top() + 2))
        painter.drawLine(QPointF(rect.left() + rect.width() * 0.4, rect.top() + 2), QPointF(rect.left() + rect.width() * 0.5, rect.top() + 6))
        folder = QPolygonF([
            QPointF(rect.left(), rect.top() + 6),
            QPointF(rect.right(), rect.top() + 6),
            QPointF(rect.right() - 3, rect.bottom()),
            QPointF(rect.left() + 3, rect.bottom()),
        ])
        painter.drawPolygon(folder)

    elif name == "save":
        painter.drawRect(rect)
        inner = QRectF(rect.left() + rect.width() * 0.2, rect.top(), rect.width() * 0.6, rect.height() * 0.45)
        painter.drawRect(inner)
        painter.drawRect(QRectF(rect.left() + rect.width() * 0.2, rect.bottom() - rect.height() * 0.35, rect.width() * 0.6, rect.height() * 0.3))

    elif name in ("undo", "redo"):
        flip = -1 if name == "redo" else 1
        arrow_cx = cx
        painter.drawArc(QRectF(cx - rect.width() * 0.35, cy - rect.height() * 0.3, rect.width() * 0.7, rect.height() * 0.6), 20 * 16, 300 * 16)
        tip_x = cx - flip * rect.width() * 0.28
        tip_y = cy - rect.height() * 0.28
        head = QPolygonF([
            QPointF(tip_x, tip_y - 4),
            QPointF(tip_x - flip * 6, tip_y + 1),
            QPointF(tip_x + 1, tip_y + 5),
        ])
        painter.setBrush(style.COLOR_OUTLINE)
        painter.drawPolygon(head)

    elif name == "compile":
        # Simple gear-ish glyph: circle with tick marks.
        painter.drawEllipse(rect.adjusted(rect.width() * 0.18, rect.height() * 0.18, -rect.width() * 0.18, -rect.height() * 0.18))
        for i in range(8):
            import math
            a = i * math.pi / 4
            r1, r2 = rect.width() * 0.5, rect.width() * 0.62
            x1, y1 = cx + r1 * math.cos(a), cy + r1 * math.sin(a)
            x2, y2 = cx + r2 * math.cos(a), cy + r2 * math.sin(a)
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    elif name == "start":
        painter.setBrush(style.COLOR_LOGIC_HIGH)
        painter.setPen(Qt.NoPen)
        tri = QPolygonF([QPointF(rect.left(), rect.top()), QPointF(rect.left(), rect.bottom()), QPointF(rect.right(), cy)])
        painter.drawPolygon(tri)

    elif name == "pause":
        painter.setBrush(style.COLOR_OUTLINE)
        painter.setPen(Qt.NoPen)
        bar_w = rect.width() * 0.3
        painter.drawRect(QRectF(rect.left(), rect.top(), bar_w, rect.height()))
        painter.drawRect(QRectF(rect.right() - bar_w, rect.top(), bar_w, rect.height()))

    elif name == "stop":
        painter.setBrush(style.COLOR_ERROR)
        painter.setPen(Qt.NoPen)
        painter.drawRect(rect)

    elif name in ("zoom_in", "zoom_out"):
        glass_rect = QRectF(rect.left(), rect.top(), rect.width() * 0.7, rect.height() * 0.7)
        painter.drawEllipse(glass_rect)
        painter.drawLine(glass_rect.bottomRight() - QPointF(2, 2), rect.bottomRight())
        gcx, gcy = glass_rect.center().x(), glass_rect.center().y()
        span = glass_rect.width() * 0.25
        painter.drawLine(QPointF(gcx - span, gcy), QPointF(gcx + span, gcy))
        if name == "zoom_in":
            painter.drawLine(QPointF(gcx, gcy - span), QPointF(gcx, gcy + span))

    elif name == "grid":
        step = rect.width() / 3
        for i in range(4):
            painter.drawLine(QPointF(rect.left() + i * step, rect.top()), QPointF(rect.left() + i * step, rect.bottom()))
            painter.drawLine(QPointF(rect.left(), rect.top() + i * step), QPointF(rect.right(), rect.top() + i * step))

    elif name == "snap":
        painter.drawLine(QPointF(cx, rect.top()), QPointF(cx, rect.bottom()))
        painter.drawLine(QPointF(rect.left(), cy), QPointF(rect.right(), cy))
        painter.setBrush(style.COLOR_OUTLINE)
        painter.drawEllipse(QPointF(cx, cy), 2, 2)

    elif name == "about":
        painter.drawEllipse(rect)
        f = painter.font()
        f.setBold(True)
        painter.setFont(f)
        painter.drawText(rect, Qt.AlignCenter, "i")

    elif name == "settings":
        painter.drawRect(rect.adjusted(0, rect.height() * 0.15, 0, -rect.height() * 0.15))
        painter.drawLine(QPointF(cx, rect.top()), QPointF(cx, rect.bottom()))

    else:
        painter.drawRect(rect)

    painter.end()
    icon = QIcon(pixmap)
    _action_icon_cache[key] = icon
    return icon
