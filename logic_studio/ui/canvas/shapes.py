"""Procedural drawing of every block shape — the single source of truth for
"what does a NAND / DI tag / generic block look like", shared by the canvas
(BlockItem, in block_item.py) and the library icons (icons.py). Every
function takes a QPainter and a QRectF and draws entirely relative to that
rect's top-left corner, so the exact same code renders a full-size canvas
block or a 24x24 tree-view icon. No image files anywhere — this module is it
(feat/block-rendering-library §5.1).
"""
from PySide6.QtGui import QPainterPath, QPen, QColor, QFont
from PySide6.QtCore import Qt, QRectF, QPointF

from logic_studio.ui.canvas import style

NEGATED_GATES = ("NOT", "NAND", "NOR", "XNOR")
SHIELD_GATES = ("OR", "NOR", "XOR", "XNOR")
DSHAPE_GATES = ("AND", "NAND")


def gate_output_offset(shape_style: str) -> float:
    """How far past the body's right edge a gate's output port sits: past
    the negation bubble for negated gates, flush with the body otherwise.
    Shared by BlockItem (port placement) and draw_gate_shape (bubble
    placement) so the two can never drift apart again (§1)."""
    return 2 * style.BUBBLE_RADIUS if shape_style in NEGATED_GATES else 0.0


def draw_gate_shape(painter, rect: QRectF, shape_style: str, inputs_count: int = 2):
    """Draws a logic-gate body filling `rect` entirely (§2.3: the body always
    spans the full block height now — there is no separate "gate_body_height"
    shorter than the block, so no bus-bar line is needed to visually bridge
    a gap that no longer exists), plus the negation bubble at the right edge
    for NOT/NAND/NOR/XNOR.
    """
    painter.setPen(QPen(style.COLOR_OUTLINE, 1))
    painter.setBrush(Qt.NoBrush)

    x0, y0, w, h = rect.left(), rect.top(), rect.width(), rect.height()
    path = QPainterPath()

    if shape_style in DSHAPE_GATES:
        # D-shape: straight left edge, semicircle bulging out the right half.
        path.moveTo(x0, y0)
        path.lineTo(x0 + w * 0.5, y0)
        path.arcTo(x0 + w * 0.5 - h / 2, y0, h, h, 90, -180)
        path.lineTo(x0, y0 + h)
        path.closeSubpath()

    elif shape_style in SHIELD_GATES:
        # Shield shape. XOR/XNOR get their body shifted right by
        # XOR_ACCENT_OFFSET so the extra distinguishing curve (drawn below,
        # anchored at the rect's left edge — exactly where input ports sit,
        # per the IEC/ANSI XOR symbol) has room to be fully visible instead
        # of merging into the shield's own leading edge (§2.2).
        accent = style.XOR_ACCENT_OFFSET if shape_style in ("XOR", "XNOR") else 0
        sx = x0 + accent
        path.moveTo(sx, y0)
        path.quadTo(sx + w * 0.75, y0, x0 + w, y0 + h / 2)
        path.quadTo(sx + w * 0.75, y0 + h, sx, y0 + h)
        path.quadTo(sx + w * 0.25, y0 + h / 2, sx, y0)

        if shape_style in ("XOR", "XNOR"):
            extra = QPainterPath()
            extra.moveTo(x0, y0)
            extra.quadTo(x0 + w * 0.25, y0 + h / 2, x0, y0 + h)
            painter.drawPath(extra)

    elif shape_style == "NOT":
        path.moveTo(x0, y0)
        path.lineTo(x0 + w - style.BUBBLE_RADIUS, y0 + h / 2)
        path.lineTo(x0, y0 + h)
        path.closeSubpath()

    elif shape_style == "BUFFER":
        # Same triangle as NOT, no negation bubble.
        path.moveTo(x0, y0)
        path.lineTo(x0 + w, y0 + h / 2)
        path.lineTo(x0, y0 + h)
        path.closeSubpath()

    else:
        # GATE_GENERIC fallback: plain rectangle.
        path.addRect(rect)

    painter.drawPath(path)

    if shape_style in NEGATED_GATES:
        painter.setBrush(style.COLOR_BACKGROUND)
        bubble_center = QPointF(x0 + w + style.BUBBLE_RADIUS, y0 + h / 2)
        painter.drawEllipse(bubble_center, style.BUBBLE_RADIUS, style.BUBBLE_RADIUS)


def draw_io_shape(painter, rect: QRectF, direction: str):
    """Chevron "tag" shape used by DI/DO/AI/AO/Virtual IN/OUT. `direction` is
    "input" or "output" — an input block's chevron points right (signal
    flowing out to the right), an output block's chevron is notched on the
    left (signal flowing in from the left)."""
    painter.setPen(QPen(style.COLOR_OUTLINE, 1))
    painter.setBrush(style.COLOR_BACKGROUND)

    x0, y0, w, h = rect.left(), rect.top(), rect.width(), rect.height()
    notch = min(10, w * 0.2)
    path = QPainterPath()

    if direction == "input":
        path.moveTo(x0, y0)
        path.lineTo(x0 + w - notch, y0)
        path.lineTo(x0 + w, y0 + h / 2)
        path.lineTo(x0 + w - notch, y0 + h)
        path.lineTo(x0, y0 + h)
        path.closeSubpath()
    else:
        path.moveTo(x0, y0)
        path.lineTo(x0 + w, y0)
        path.lineTo(x0 + w, y0 + h)
        path.lineTo(x0, y0 + h)
        path.lineTo(x0 + notch, y0 + h / 2)
        path.closeSubpath()

    painter.drawPath(path)


def draw_complex_shape(painter, rect: QRectF, inputs_count: int = 0, outputs_count: int = 0):
    """Plain rectangle used by every block without a dedicated symbol (TON,
    DEADBAND, comparators, math, ...). inputs_count/outputs_count are
    accepted for icon generation (§5.3: a COMPLEX block's icon marks its pin
    counts) but the canvas body itself is just the rectangle — pins are
    drawn separately as PortItem children."""
    painter.setPen(QPen(style.COLOR_OUTLINE, 1))
    painter.setBrush(style.COLOR_BACKGROUND)
    painter.drawRect(rect)


def draw_complex_icon_pin_marks(painter, rect: QRectF, inputs_count: int, outputs_count: int):
    """Small tick marks on a COMPLEX block's rectangle indicating how many
    inputs/outputs it has — used only for the library icon (§5.3), where
    there's no room for individual PortItem children."""
    painter.setPen(QPen(style.COLOR_OUTLINE, 1))
    x0, y0, w, h = rect.left(), rect.top(), rect.width(), rect.height()

    def ticks(count, x):
        if count <= 0:
            return
        spacing = h / (count + 1)
        for i in range(count):
            y = y0 + spacing * (i + 1)
            painter.drawLine(QPointF(x, y), QPointF(x + (w * 0.12 if x == x0 else -w * 0.12), y))

    ticks(inputs_count, x0)
    ticks(outputs_count, x0 + w)
