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


def centered_port_offsets(count: int, pitch: float = None) -> list:
    """Y offsets from a block's own vertical center for `count` ports,
    spaced `pitch` apart (default style.PORT_PITCH), symmetric around 0 —
    the shared symmetry rule for gate inputs, IO pins, and COMPLEX block
    inputs/outputs alike (feat/editor-modes-and-geometry §1.2/§1.4). Shared
    between block_item.py (actual PortItem placement) and this module (lead-
    line/rail drawing) so the two can never disagree about where a port
    really is."""
    pitch = style.PORT_PITCH if pitch is None else pitch
    if count <= 0:
        return []
    return [(i - (count - 1) / 2) * pitch for i in range(count)]


def draw_gate_shape(painter, rect: QRectF, shape_style: str, inputs_count: int = 2, draw_leads: bool = True):
    """Draws a logic-gate body, the negation bubble for NOT/NAND/NOR/XNOR,
    and — when `draw_leads` is true — a short straight "lead" line on every
    pin between its port square and the body, matching the reference IEC/
    ANSI symbol style instead of the body touching the port squares
    directly. `draw_leads` defaults to true for the canvas; icons.py passes
    false to keep small tree/preview icons from being eaten alive by lead
    lines that make no sense at 24px.

    feat/editor-modes-and-geometry §1: the drawn BODY is always exactly
    GATE_BODY x GATE_BODY, vertically centered within `rect` — never
    stretched taller for more inputs the way it used to be (that stretching
    is exactly what made the D-shape/shield curve look "flattened" for
    anything past 2-3 inputs, since the curve's own proportions followed
    the body's full height). Inputs beyond what fits inside that fixed
    body (`|offset| > GATE_BODY/2`, i.e. 4 or more) spread out
    symmetrically above/below it — see centered_port_offsets() — and are
    collected by a vertical "rail" at the same x the body's own (lead-
    pulled-back) left edge sits at, so the rail visually continues straight
    into the body rather than sitting merely adjacent to it. For
    `draw_leads=False` (icons), there's no separate "body vs. block"
    distinction — the body just fills whatever (small, fixed-size) rect the
    icon was given, as before this section.

    The rect's right edge (x0 + w) is always the gate's actual output
    connection point (where PortItem sits), negated or not, and its left
    edge (x0) is where every input PortItem sits — pulled back from both by
    GATE_LEAD (plus, for a negated gate's output side, the negation bubble
    and its own clearance from the port — see BUBBLE_PORT_GAP) with lead
    lines filling the resulting gaps. This keeps every port's own position
    completely unchanged (still exactly at 0 / width, still grid-aligned).

    The D-shape (AND/NAND) right-side curve is a true ELLIPSE, not a fixed-
    radius semicircle — sized to the always-fixed GATE_BODY now, so it's
    never anything but the same clean curve regardless of input count.
    """
    painter.setPen(QPen(style.COLOR_OUTLINE, 1))
    painter.setBrush(Qt.NoBrush)

    x0, y0, w, h = rect.left(), rect.top(), rect.width(), rect.height()
    negated = shape_style in NEGATED_GATES
    lead = style.GATE_LEAD if draw_leads else 0.0

    body_h = style.GATE_BODY if draw_leads else h
    body_y0 = y0 + (h - body_h) / 2
    center_y = y0 + h / 2

    left_bound = x0 + lead
    if negated:
        right_bound = x0 + w - (style.PORT_RADIUS + style.BUBBLE_PORT_GAP + 2 * style.BUBBLE_RADIUS)
    else:
        right_bound = x0 + w - lead
    body_w = max(1.0, right_bound - left_bound)

    path = QPainterPath()

    if shape_style in DSHAPE_GATES:
        # D-shape: straight left edge, then an elliptical bulge to the tip.
        flat_len = body_w * 0.35
        rx = body_w - flat_len
        path.moveTo(left_bound, body_y0)
        path.lineTo(left_bound + flat_len, body_y0)
        path.arcTo(QRectF(left_bound + flat_len - rx, body_y0, rx * 2, body_h), 90, -180)
        path.lineTo(left_bound, body_y0 + body_h)
        path.closeSubpath()

    elif shape_style in SHIELD_GATES:
        # Shield shape. XOR/XNOR get their body shifted right by
        # XOR_ACCENT_OFFSET so the extra distinguishing curve (drawn below,
        # anchored at the block's own left edge — exactly where input leads
        # start, per the IEC/ANSI XOR symbol) has room to be fully visible
        # instead of merging into the shield's own leading edge (§2.2). The
        # tip (sx + bw) always lands at `right_bound` regardless of the
        # accent, so the negation bubble / output lead placement below
        # doesn't need to special-case it.
        accent = style.XOR_ACCENT_OFFSET if shape_style in ("XOR", "XNOR") else 0
        sx = left_bound + accent
        bw = (right_bound - left_bound) - accent
        path.moveTo(sx, body_y0)
        path.quadTo(sx + bw * 0.75, body_y0, sx + bw, body_y0 + body_h / 2)
        path.quadTo(sx + bw * 0.75, body_y0 + body_h, sx, body_y0 + body_h)
        path.quadTo(sx + bw * 0.25, body_y0 + body_h / 2, sx, body_y0)

        if shape_style in ("XOR", "XNOR"):
            extra = QPainterPath()
            extra.moveTo(x0, body_y0)
            extra.quadTo(x0 + w * 0.25, body_y0 + body_h / 2, x0, body_y0 + body_h)
            painter.drawPath(extra)

    elif shape_style in ("NOT", "BUFFER"):
        path.moveTo(left_bound, body_y0)
        path.lineTo(right_bound, body_y0 + body_h / 2)
        path.lineTo(left_bound, body_y0 + body_h)
        path.closeSubpath()

    else:
        # GATE_GENERIC fallback: plain rectangle.
        path.addRect(QRectF(left_bound, body_y0, body_w, body_h))

    painter.drawPath(path)

    bubble_right_edge = None
    if negated:
        painter.setBrush(style.COLOR_BACKGROUND)
        # Touches the body's tip (right_bound) on the left; its own right
        # edge stops BUBBLE_PORT_GAP short of the output port square, so the
        # two never touch, let alone overlap.
        bubble_center = QPointF(right_bound + style.BUBBLE_RADIUS, center_y)
        painter.drawEllipse(bubble_center, style.BUBBLE_RADIUS, style.BUBBLE_RADIUS)
        bubble_right_edge = bubble_center.x() + style.BUBBLE_RADIUS

    if draw_leads:
        painter.setPen(QPen(style.COLOR_OUTLINE, 1))

        input_ys = [center_y + off for off in centered_port_offsets(inputs_count)]
        for y_i in input_ys:
            painter.drawLine(QPointF(x0, y_i), QPointF(left_bound, y_i))

        # §1.3: rail — only when an input lands outside the fixed body's
        # own vertical span (4+ inputs, given GATE_BODY=40/PORT_PITCH=20).
        # Drawn at the SAME x the body's own left edge sits at, so it reads
        # as continuing straight into the body rather than a separate line
        # merely alongside it ("szyna...wchodząca w jego lewą krawędź").
        if input_ys:
            body_top, body_bottom = body_y0, body_y0 + body_h
            top_y, bottom_y = min(input_ys), max(input_ys)
            if top_y < body_top:
                painter.drawLine(QPointF(left_bound, top_y), QPointF(left_bound, body_top))
            if bottom_y > body_bottom:
                painter.drawLine(QPointF(left_bound, body_bottom), QPointF(left_bound, bottom_y))

        lead_start = bubble_right_edge if negated else right_bound
        painter.drawLine(QPointF(lead_start, center_y), QPointF(x0 + w, center_y))


IO_NOTCH_MAX = 10  # cap on the output-direction chevron's notch depth


def io_notch_width(w: float) -> float:
    """The output-direction chevron's notch depth for a block of width `w`
    — shared by draw_io_shape() and BlockItem's IO text layout (§0.4 audit
    follow-up) so the two can never disagree about how much of the left
    edge is actually cut away. A block narrower than IO_NOTCH_MAX*5 gets a
    proportionally shallower notch; every real IO block is wide enough
    (>=80px) that this is always exactly IO_NOTCH_MAX in practice."""
    return min(IO_NOTCH_MAX, w * 0.2)


def draw_io_shape(painter, rect: QRectF, direction: str):
    """Chevron "tag" shape used by DI/DO/AI/AO/Virtual IN/OUT. `direction` is
    "input" or "output" — an input block's chevron points right (signal
    flowing out to the right), an output block's chevron is notched on the
    left (signal flowing in from the left)."""
    painter.setPen(QPen(style.COLOR_OUTLINE, 1))
    painter.setBrush(style.COLOR_BACKGROUND)

    x0, y0, w, h = rect.left(), rect.top(), rect.width(), rect.height()
    notch = io_notch_width(w)
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


def draw_doc_shape(painter, rect: QRectF):
    """Icon-only symbol for doc.text/doc.note/doc.section (§10.3) — a page
    outline with a few horizontal rules standing in for text lines. The
    canvas itself never calls this: a placed DOC block renders its actual
    Text via BlockItem._paint_doc_block(), not this generic glyph."""
    painter.setPen(QPen(style.COLOR_OUTLINE, 1))
    painter.setBrush(Qt.NoBrush)
    painter.drawRect(rect)

    x0, y0, w, h = rect.left(), rect.top(), rect.width(), rect.height()
    n_lines = 3
    inset = w * 0.18
    for i in range(n_lines):
        y = y0 + h * (0.28 + i * 0.22)
        painter.drawLine(QPointF(x0 + inset, y), QPointF(x0 + w - inset, y))


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
