import math

from PySide6.QtWidgets import QGraphicsItem, QStyleOptionGraphicsItem, QInputDialog, QLineEdit
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QFont, QCursor, QPainterPath, QFontMetricsF
from PySide6.QtWidgets import QMenu
from PySide6.QtCore import Qt, QRectF, QPointF

from logic_studio.ui.canvas import style, shapes

GATE_SHAPES = ("AND", "OR", "NOT", "XOR", "NAND", "NOR", "XNOR", "BUFFER", "GATE_GENERIC")

# shape_styles whose ports must always suppress PortItem's generic pin-name
# label — gates only; the type label under the body already says enough.
# IO blocks are handled by pin_labels_suppressed() below instead, since
# whether a label is needed there depends on the block's actual pin count,
# not just its shape_style (§0.1 audit follow-up).
NO_PIN_LABEL_SHAPES = GATE_SHAPES


def pin_labels_suppressed(item) -> bool:
    """Whether PortItem should skip drawing this block's generic pin-name
    label. Gates always do (the type label under the body says enough). IO
    blocks (DI/DO/AI/AO/Virtual IN/OUT/...) do only when the block has
    exactly one pin in total — its own Address/Tag + display-name text
    already say everything a single generic pin name would, and for an
    output-direction single-pin IO block (DO/AO) that one port sits on the
    SAME left edge as that text, so the redundant label used to render
    right on top of it (e.g. ADA01.DO14's "Cmd" overlapping its green "DO"
    display-name line).

    This used to be a blanket "every IO block" rule (`shape_style == "IO"`)
    — wrong since PR #4 added input.ai, a 2-output IO block (Value +
    Quality): with no labels at all, the two identical-looking ports were
    indistinguishable, and Quality (the one PR #4's whole quality-tracking
    mechanism depends on) couldn't reliably be told apart from Value."""
    if item.shape_style in GATE_SHAPES:
        return True
    if item.shape_style == "IO":
        block = item.logic_block
        return (len(block.inputs) + len(block.outputs)) <= 1
    return False


def _round_up_to_grid(value, grid=None):
    grid = grid or style.GRID_SIZE
    return math.ceil(value / grid) * grid


def _round_up_to_pitch(value):
    """Like _round_up_to_grid(), but against the finer PORT_PITCH sub-grid
    rather than GRID_SIZE — used for sizes (IO block height, §0.1) that
    only need to land on a pin-pitch multiple, not the coarser block-
    placement grid."""
    return math.ceil(value / style.PORT_PITCH) * style.PORT_PITCH


def io_text_margin_x(width, direction):
    """Left margin for an IO block's identifier/display-name text (§0.4/0.5
    audit follow-up). A plain 6px for input-direction blocks (chevron
    points right — the left edge is a straight vertical line); 6px plus
    the chevron's own notch depth for output-direction blocks, whose left
    edge has a notch carved into it (shapes.draw_io_shape()) that a bare
    6px margin used to sit right on top of. Shared between
    BlockItem._draw_io_text_lines() and the block-width calculation in
    _determine_shape_style() so the two can never disagree about how much
    room the notch actually needs."""
    return 6 + (shapes.io_notch_width(width) if direction == "output" else 0)


def _complex_readout_y(pins_count):
    """Top y (local, below the type-name label) for a COMPLEX block's
    param_text/sim_text readout (TON/TOF/TP's "T=...[s]", counters'
    "PV=.../CV=..."). Must clear every pin row's own label — a pin's label
    is vertically centered on its row at PORT_MARGIN + i*PORT_PITCH and
    reserves roughly [-10, +10] around that — so this starts 5px below the
    bottom of the LAST row's reserved band, regardless of how many pins the
    block has or how long the readout string is (§ "bramki się rozjechały"
    follow-up: a fixed offset that happened to work for short strings on
    few-pin blocks silently collided for longer strings / more pins)."""
    last_pin_y = style.PORT_MARGIN + max(0, pins_count - 1) * style.PORT_PITCH
    return last_pin_y + style.PORT_PITCH / 2 + 5


# Shared with shapes.py (which draws the output lead line at this same y —
# see shapes.gate_output_y()) so the two can never drift apart; kept under
# its old name here since existing tests import it from this module.
_round_half_up_to_pitch = shapes.round_half_up_to_pitch


class BlockItem(QGraphicsItem):
    def __init__(self, logic_block, parent=None):
        super().__init__(parent)
        self.logic_block = logic_block

        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)

        # Industrial look colors
        self.bg_color = style.COLOR_BACKGROUND
        self.header_color = QColor(100, 100, 100)
        if logic_block.color.startswith("#"):
            self.header_color = QColor(logic_block.color)

        self.border_color = style.COLOR_OUTLINE
        self.selected_color = style.COLOR_SELECTION
        self.live_color = style.COLOR_LOGIC_HIGH

        self.width = logic_block.width
        self.height = logic_block.height
        self.category = logic_block.category
        self.type_id = logic_block.type_id

        self._resizing = False
        self._resize_start_scene_pos = None
        self._resize_start_size = None

        self.setPos(logic_block.x, logic_block.y)

        self._determine_shape_style()
        self._create_ports()

    # ---- Geometry (§4: every port must land on a grid intersection) --------

    def _determine_shape_style(self):
        """Determines the visual rendering style AND the block's size, based
        on category and type_id. Sizing follows §4's grid rule everywhere:
        every port sits at PORT_MARGIN + i*PORT_PITCH from the block's own
        top/left edge, so a grid-aligned block origin (guaranteed by
        snap-on-drop and snap-on-move) is enough to put every port on the
        scene grid too — no per-block special-casing needed downstream."""
        if self.category == "Bramki logiczne":
            if self.type_id.startswith("logic.buffer"):
                self.shape_style = "BUFFER"
            elif self.type_id.startswith("logic.and"):
                self.shape_style = "AND"
            elif self.type_id.startswith("logic.or"):
                self.shape_style = "OR"
            elif self.type_id.startswith("logic.nand"):
                self.shape_style = "NAND"
            elif self.type_id.startswith("logic.nor"):
                self.shape_style = "NOR"
            elif self.type_id.startswith("logic.xor"):
                self.shape_style = "XOR"
            elif self.type_id.startswith("logic.xnor"):
                self.shape_style = "XNOR"
            elif self.type_id.startswith("logic.not"):
                self.shape_style = "NOT"
            else:
                self.shape_style = "GATE_GENERIC"

            # Symmetric top/bottom margin around the input pins: the first
            # sits PORT_MARGIN below the top edge, the last PORT_MARGIN
            # above the bottom edge, with PORT_PITCH between consecutive
            # ones — not the old `(inputs_count+1)*PORT_PITCH`, which only
            # produced that same symmetric result back when PORT_MARGIN and
            # PORT_PITCH were equal (§ grid-density redesign).
            #
            # §0.3 audit follow-up: rounded UP to a multiple of 2*PORT_PITCH
            # on top of that, so height/2 always lands exactly on a
            # PORT_PITCH multiple — for an even input count the raw formula
            # above isn't one (e.g. 2 inputs: 50, center 25 — not a
            # PORT_PITCH multiple), which used to force gate_output_y() to
            # round the output port away from the body's true geometric
            # center; the D-shape/shield curve's tip (drawn at the real
            # center) and the output port (rounded to the nearest one) then
            # visibly disagreed. This costs perfect top/bottom input-margin
            # symmetry for even input counts (bottom ends up PORT_PITCH
            # taller than top) in exchange for the output port always
            # sitting exactly where the curve's tip actually is — the more
            # visible of the two problems.
            inputs_count = len(self.logic_block.inputs)
            raw_height = 2 * style.PORT_MARGIN + max(0, inputs_count - 1) * style.PORT_PITCH
            self.height = math.ceil(raw_height / (2 * style.PORT_PITCH)) * (2 * style.PORT_PITCH)

            # Every gate is the same width regardless of negation — only how
            # shapes.draw_gate_shape() fills the last few pixels near the tip
            # differs (the body is drawn pulled back to make room for the
            # bubble; see that function). The output port always sits at
            # exactly `width`, identical to the non-negated sibling, so
            # negating a gate never shifts its output connection point, and
            # AND/NAND are always drawn the same size (§4.2).
            self.width = 2 * style.GRID_SIZE

        elif self.category == "Wejścia / Wyjścia":
            self.shape_style = "IO"
            base_height = 60 if self.type_id in ("input.ai", "output.ao") else 40

            # §0.1 audit follow-up: height must fit however many pins this
            # IO block actually has — input.ai's 2 outputs (Value, Quality)
            # both landed at the same y before this, since nothing here
            # accounted for more than one. max(existing, needed) so no
            # current block shrinks; rounded up to a PORT_PITCH multiple so
            # the last pin's own margin stays a clean grid value.
            n_pins = len(self.logic_block.outputs) if self._io_direction() == "input" else len(self.logic_block.inputs)
            needed_height = style.PORT_MARGIN + max(0, n_pins - 1) * style.PORT_PITCH + style.PORT_MARGIN
            self.height = _round_up_to_pitch(max(base_height, needed_height))

            # §0.4/§0.5 audit follow-up: the same formula for both
            # directions (nothing here special-cases "input"/"output") —
            # but an output-direction block's chevron has a notch carved
            # into its left edge (shapes.draw_io_shape()) that a plain
            # fixed 6px text margin used to sit right on top of. Budgeting
            # IO_NOTCH_MAX here (rather than the exact, width-dependent
            # notch — computing that would need the width this is
            # computing) keeps both directions' sizing identical in shape,
            # while still reserving enough room that the identifier text
            # never starts before the notch's tip.
            base_width = 80
            identifier = self._io_identifier()
            if identifier:
                font = QFont(style.FONT_FAMILY, style.FONT_SIZE_TAG, QFont.Bold)
                direction = self._io_direction()
                # io_text_margin_x() wants the notch width, which itself
                # depends on the block's width — but io_notch_width() caps
                # at IO_NOTCH_MAX for any width >= 50 (every real IO block
                # is at least 80), so budgeting with the (not yet known)
                # base_width floor here always gives the same answer the
                # final width will too.
                left_margin = io_text_margin_x(base_width, direction)
                needed = QFontMetricsF(font).horizontalAdvance(identifier) + left_margin + 6
                base_width = max(base_width, _round_up_to_grid(needed))
            self.width = base_width

        elif self.category == "Dokumentacja":
            self.shape_style = "DOC"
            self._size_doc_block()

        else:
            self.shape_style = "COMPLEX"
            inputs_count = len(self.logic_block.inputs)
            outputs_count = len(self.logic_block.outputs)
            min_height = style.PORT_MARGIN + max(inputs_count, outputs_count) * style.PORT_PITCH + style.PORT_MARGIN
            self.height = _round_up_to_grid(max(self.height, min_height))
            self.width = _round_up_to_grid(max(self.width, style.GRID_SIZE * 2))

    def _size_doc_block(self):
        """DOC blocks have no pins to align to a grid, so they size to their
        text content instead (§6.6) — except doc.note, which is manually
        resizable (§6.6/§6.5): its persisted width/height IS the size, only
        rounded up to the grid, never recomputed from the text."""
        if self.type_id == "doc.note":
            self.width = _round_up_to_grid(max(self.logic_block.width, style.GRID_SIZE * 2))
            self.height = _round_up_to_grid(max(self.logic_block.height, style.GRID_SIZE * 2))
            return

        text = self.logic_block.properties.get("Text", "") or " "
        if self.type_id == "doc.section":
            font = QFont(style.FONT_FAMILY, style.FONT_SIZE_DOC_SECTION, QFont.Bold)
        else:
            font = QFont(style.FONT_FAMILY, style.FONT_SIZE_DOC_TEXT)

        fm = QFontMetricsF(font)
        self.width = _round_up_to_grid(max(fm.horizontalAdvance(text) + 20, style.GRID_SIZE * 2))
        self.height = _round_up_to_grid(max(fm.height() + 10, style.GRID_SIZE))

    def _create_ports(self):
        from logic_studio.ui.canvas.port_item import PortItem

        if self.shape_style == "DOC":
            return  # documentation blocks have no pins (§6.3)

        if self.shape_style in GATE_SHAPES:
            for i, pin in enumerate(self.logic_block.inputs):
                port = PortItem(pin, parent=self)
                port.setPos(0, style.PORT_MARGIN + i * style.PORT_PITCH)

            output_y = shapes.gate_output_y(self.height)
            for pin in self.logic_block.outputs:
                port = PortItem(pin, parent=self)
                port.setPos(self.width, output_y)

        elif self.shape_style == "IO":
            # §0.1 audit follow-up: spaced by PORT_PITCH like every other
            # multi-pin block, not all pinned to the same y — input.ai's
            # Value and Quality used to land exactly on top of each other,
            # making Quality (the pin PR #4's whole quality-tracking
            # mechanism depends on) unreachable by a wire.
            if self._io_direction() == "input":
                for i, pin in enumerate(self.logic_block.outputs):  # Input blocks have output pins
                    port = PortItem(pin, parent=self)
                    port.setPos(self.width, style.PORT_MARGIN + i * style.PORT_PITCH)
            else:
                for i, pin in enumerate(self.logic_block.inputs):  # Output blocks have input pins
                    port = PortItem(pin, parent=self)
                    port.setPos(0, style.PORT_MARGIN + i * style.PORT_PITCH)

        else:
            for i, pin in enumerate(self.logic_block.inputs):
                port = PortItem(pin, parent=self)
                port.setPos(0, style.PORT_MARGIN + i * style.PORT_PITCH)

            for i, pin in enumerate(self.logic_block.outputs):
                port = PortItem(pin, parent=self)
                port.setPos(self.width, style.PORT_MARGIN + i * style.PORT_PITCH)

    def boundingRect(self):
        if self.shape_style == "DOC":
            m = style.BLOCK_SELECTION_MARGIN + 2
            return QRectF(-m, -m, self.width + m * 2, self.height + m * 2)

        margin = style.BOUNDING_RECT_MARGIN
        block = self.logic_block

        # A negated gate's bubble is drawn inset within [width - 2*BUBBLE_
        # RADIUS, width] — it never extends past the rect passed to
        # draw_gate_shape(), so no extra margin is needed for it here; the
        # base `margin` already covers the port's own click area.

        tag, comment = self._effective_tag_and_comment()
        top_margin = margin
        if tag or comment:
            # Room for the Tag line plus up to two Comment lines above the body.
            top_margin = margin + 40

        bottom_margin = margin
        if self.shape_style in GATE_SHAPES:
            # Room for the type-name label drawn below a gate's body (§7.2).
            bottom_margin = margin + 14

        right_margin = margin
        if comment:
            # Comment wraps up to 3x the block width (§7.2).
            right_margin = max(right_margin, self.width * 2 + margin)

        return QRectF(
            -margin, -top_margin,
            self.width + margin + right_margin,
            self.height + top_margin + bottom_margin
        )

    # ---- Painting -----------------------------------------------------------

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)

        if self.shape_style in GATE_SHAPES:
            self._paint_logic_gate(painter)
        elif self.shape_style == "IO":
            self._paint_io_tag(painter)
        elif self.shape_style == "DOC":
            self._paint_doc_block(painter)
        else:
            self._paint_complex_block(painter)

        if self.shape_style != "DOC":
            # Documentation blocks are annotations, not "functional blocks" —
            # they don't get the Tag/Comment/"???" treatment from §7/§1.
            self._paint_tag_and_comment(painter)
            self._paint_unconnected_warning(painter)

        if self.isSelected():
            rect = QRectF(0, 0, self.width, self.height)
            pen = QPen(self.selected_color, 1, Qt.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            m = style.BLOCK_SELECTION_MARGIN
            painter.drawRect(rect.adjusted(-m, -m, m, m))

    def _paint_logic_gate(self, painter):
        body_rect = QRectF(0, 0, self.width, self.height)
        shapes.draw_gate_shape(painter, body_rect, self.shape_style, len(self.logic_block.inputs))

        # Type-name label below the gate body, centered (§7.2).
        painter.setPen(QPen(style.COLOR_TYPE_LABEL_TEXT))
        font = QFont(style.FONT_FAMILY, style.FONT_SIZE_PIN_LABEL)
        painter.setFont(font)
        label_rect = QRectF(-10, self.height + 1, self.width + 20, 13)
        painter.drawText(label_rect, Qt.AlignHCenter | Qt.AlignTop, self.logic_block.display_name)

    # ---- IO blocks (§1, §5) --------------------------------------------------

    def _io_direction(self) -> str:
        """"input" if this IO-shape block SOURCES a value (has outputs, no
        inputs — DI/AI/virtual.input/internal.reg_in), else "output"
        (SINKS one — DO/AO/virtual.output/internal.reg_out). Derived from
        the block's actual pins, not a `"input" in type_id` substring
        check — that heuristic silently broke for "internal.reg_in" (which
        contains "in" but not the substring "input")."""
        return "input" if self.logic_block.outputs else "output"

    # type_ids whose identifier comes from the internal-signal registry
    # ("Bit" property, resolved to M./MR./MW./MWR.<name> — see
    # _resolved_internal_signal_id()) rather than "Address"/"Tag".
    INTERNAL_SIGNAL_TYPE_IDS = ("virtual.input", "virtual.output", "internal.reg_in", "internal.reg_out")

    def _io_identifier(self):
        """Whatever actually configures this IO block: "Address" for
        physical/analog IO (DI/DO/AI/AO), the resolved internal-signal id
        for Virtual IN/OUT and register blocks (§2.4), else "Tag" —
        system-signal blocks use "Tag" as their own HMI/network identifier
        (see BaseLogicBlock.properties). Empty string if none apply. One
        place, used by both the on-block label and the missing-config
        warning, so they can never read two different properties and
        disagree with each other again (§1)."""
        if self.type_id in self.INTERNAL_SIGNAL_TYPE_IDS:
            return self._resolved_internal_signal_id()
        props = self.logic_block.properties
        return props.get("Address", "") or props.get("Tag", "")

    def _resolved_internal_signal_id(self) -> str:
        """Best-effort M./MR./MW./MWR.<name> id for on-canvas display
        (§2.4) — UI-only, reaches into the live Project like
        _lookup_analog_unit() (the runtime engine never holds one). Falls
        back to the bare "Bit" name if the registry entry can't be found
        (project not wired up yet, or the name no longer exists in the
        registry — the latter is exactly what validator §4.4 flags)."""
        name = self.logic_block.properties.get("Bit", "")
        if not name:
            return ""
        try:
            window = self.scene().views()[0].window()
            project = getattr(window, 'project', None)
            if project is None:
                return name
            from logic_studio.core.device_model import DeviceModel
            from logic_studio.core.internal_bits import internal_bit_id
            entry = DeviceModel.get_internal_bit(project, name)
            return internal_bit_id(entry) if entry else name
        except Exception:
            return name

    def _internal_signal_entry(self):
        """The full registry entry (for its "label"/"retentive" fields) —
        None if unavailable for any reason. Same best-effort UI-only Project
        reach-in as _resolved_internal_signal_id()."""
        if self.type_id not in self.INTERNAL_SIGNAL_TYPE_IDS:
            return None
        name = self.logic_block.properties.get("Bit", "")
        if not name:
            return None
        try:
            window = self.scene().views()[0].window()
            project = getattr(window, 'project', None)
            if project is None:
                return None
            from logic_studio.core.device_model import DeviceModel
            return DeviceModel.get_internal_bit(project, name)
        except Exception:
            return None

    # Per shape_style, a callable (BlockItem) -> str returning the identifier
    # that must be non-empty for the block to count as "configured" — add an
    # entry here for a future category that needs the same red "???"
    # treatment; _paint_unconnected_warning() itself never needs to change.
    _REQUIRED_IDENTIFIER_GETTERS = {
        "IO": lambda item: item._io_identifier(),
    }

    def _paint_io_tag(self, painter):
        direction = self._io_direction()
        shapes.draw_io_shape(painter, QRectF(0, 0, self.width, self.height), direction)

        identifier = self._io_identifier()

        if self.type_id in self.INTERNAL_SIGNAL_TYPE_IDS:
            # §2.4: identifier (M.BLOKADA_ZS-style), then the registry's
            # own short "label" underneath if one is set — not the generic
            # display_name ("Wejście bitowe (wewn.)"), which says nothing
            # about THIS signal.
            entry = self._internal_signal_entry()
            second_line = entry.get("label", "") if entry else ""
            lines = [(identifier, True), (second_line, False)]
        else:
            lines = [(identifier, True), (self.logic_block.display_name, False)]

        if self.type_id in ("input.ai", "output.ao"):
            unit = self._lookup_analog_unit(identifier) if identifier else ""
            sim_value = self.logic_block.simulation_state.get("sim_value")
            value_text = ""
            if sim_value is not None:
                try:
                    value_text = f"{float(sim_value):.2f}"
                except (TypeError, ValueError):
                    value_text = str(sim_value)
            unit_line = " ".join(t for t in (unit, value_text) if t)
            if unit_line:
                lines.append((unit_line, False))

        self._draw_io_text_lines(painter, lines, direction)

        # Quality indicator: a red dot when the AI block's last reading was
        # not trustworthy.
        if self.type_id == "input.ai" and self.logic_block.simulation_state.get("quality") is False:
            painter.setPen(Qt.NoPen)
            painter.setBrush(style.COLOR_ERROR)
            painter.drawEllipse(QPointF(self.width - 6, 6), 4, 4)

        # Retentive marker (§2.4) — a small filled square in the corner,
        # distinct from the quality dot above (different shape, opposite
        # corner) so the two never get confused if a future block needs
        # both.
        if self.type_id in self.INTERNAL_SIGNAL_TYPE_IDS:
            entry = self._internal_signal_entry()
            if entry and entry.get("retentive"):
                painter.setPen(QPen(style.COLOR_OUTLINE, 1))
                painter.setBrush(style.COLOR_OUTLINE)
                painter.drawRect(QRectF(self.width - 9, self.height - 9, 6, 6))

    def _draw_io_text_lines(self, painter, lines, direction="input"):
        """Each line gets its OWN QRectF, never one multi-line wrapped
        string — that's what let "VI.NEW_INPUT" float above the block and
        "State"/"Cmd" pin labels overlap the block name before (§5). Text
        that still doesn't fit is elided, never drawn past the block's own
        outline; a line that would land past the bottom edge is skipped
        entirely rather than spilling over.

        §0.4 audit follow-up: the left margin depends on the block's shape,
        not a bare constant — an output-direction chevron has a notch cut
        into its left edge (shapes.draw_io_shape()), and a fixed 6px margin
        used to sit right on top of its diagonal edge (e.g. "ADA01.DO01"'s
        first letter landing on the notch line)."""
        margin_x = io_text_margin_x(self.width, direction)
        available_width = max(1.0, self.width - margin_x - 6)
        y = 3.0

        for text, bold in lines:
            if not text:
                continue

            size = style.FONT_SIZE_TAG if bold else style.FONT_SIZE_PIN_LABEL
            font = QFont(style.FONT_FAMILY, size)
            font.setBold(bold)
            fm = QFontMetricsF(font)
            line_height = fm.height()

            if y + line_height > self.height - 2:
                break

            painter.setFont(font)
            painter.setPen(QPen(style.COLOR_OUTLINE if bold else style.COLOR_TYPE_LABEL_TEXT))
            elided = fm.elidedText(text, Qt.ElideRight, available_width)
            painter.drawText(QRectF(margin_x, y, available_width, line_height), Qt.AlignLeft | Qt.AlignTop, elided)
            y += line_height

    def _lookup_analog_unit(self, address: str) -> str:
        """Best-effort lookup of an analog point's unit for on-canvas display.
        This is a UI-only concern — BlockItem may reach into the live Project
        via its scene's view, unlike the runtime engine which never holds a
        Project reference. Returns "" if unavailable for any reason (no
        scene/view yet, no project, unknown address)."""
        if not address:
            return ""
        try:
            window = self.scene().views()[0].window()
            project = getattr(window, 'project', None)
            if project is None:
                return ""
            from logic_studio.core.device_model import DeviceModel
            point = DeviceModel.get_analog_point(project, address)
            return point.get("unit", "") if point else ""
        except Exception:
            return ""

    # ---- COMPLEX blocks -------------------------------------------------------

    def _paint_complex_block(self, painter):
        rect = QRectF(0, 0, self.width, self.height)
        shapes.draw_complex_shape(painter, rect)

        painter.setPen(style.COLOR_OUTLINE)
        font = QFont(style.FONT_FAMILY, style.FONT_SIZE_PIN_LABEL)
        painter.setFont(font)

        # Type name, centered inside the body (§7.2).
        painter.drawText(rect.adjusted(2, 2, -2, -2), Qt.AlignTop | Qt.AlignHCenter, self.logic_block.display_name)

        param_text = ""
        sim_text = ""
        state = self.logic_block.simulation_state

        if self.category == "Timery":
            delay = self.logic_block.properties.get("Preset (ms)")
            if delay is not None:
                param_text = f"T={float(delay)/1000:.2f}[s]"
        elif self.category == "Liczniki":
            preset = self.logic_block.properties.get("Preset")
            if preset is not None:
                param_text = f"PV={preset}"
            if "count" in state:
                sim_text = f"CV={state['count']}"

        # These used to sit at a fixed (2, 15)/(2, 28) offset — exactly
        # where the first/second pin ROW's own label lands (PORT_MARGIN,
        # PORT_MARGIN + PORT_PITCH), so a counter/timer's "CU"/"CD"/"IN"
        # label rendered right on top of "PV=.../T=...[s]". Centering
        # helped but wasn't enough on its own — TON/TOF's longer
        # "T=1.00[s]" still reached both the left input-label column and
        # the right output-label column on a 100px-wide block. Placed below
        # every pin row instead (however many a given block has), which the
        # already-generous per-category block heights always leave room
        # for — this can never land on a pin's own row again, regardless of
        # pin count or how long the readout string is.
        if param_text or sim_text:
            pins_count = max(len(self.logic_block.inputs), len(self.logic_block.outputs))
            y = _complex_readout_y(pins_count)
            line_rect = QRectF(2, y, self.width - 4, 13)

            if param_text:
                painter.setPen(QPen(style.COLOR_TYPE_LABEL_TEXT))
                painter.drawText(line_rect, Qt.AlignTop | Qt.AlignHCenter, param_text)
                line_rect.translate(0, 13)

            if sim_text:
                painter.setPen(QPen(style.COLOR_ERROR))
                painter.drawText(line_rect, Qt.AlignTop | Qt.AlignHCenter, sim_text)

    # ---- Documentation blocks (§6) ---------------------------------------------

    def _paint_doc_block(self, painter):
        rect = QRectF(0, 0, self.width, self.height)
        text = self.logic_block.properties.get("Text", "")

        if self.type_id == "doc.note":
            painter.setPen(QPen(style.COLOR_DOC_NOTE_BORDER, 1))
            painter.setBrush(style.COLOR_DOC_NOTE_BACKGROUND)
            painter.drawRect(rect)

            painter.setPen(QPen(style.COLOR_DOC_TEXT))
            painter.setFont(QFont(style.FONT_FAMILY, style.FONT_SIZE_DOC_NOTE))
            painter.drawText(rect.adjusted(6, 6, -6, -6), Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, text)

            h = style.DOC_NOTE_RESIZE_HANDLE
            painter.setPen(QPen(style.COLOR_DOC_NOTE_BORDER, 1))
            for offset in (3, 6):
                painter.drawLine(
                    QPointF(self.width - offset, self.height),
                    QPointF(self.width, self.height - offset)
                )

        elif self.type_id == "doc.section":
            painter.setPen(QPen(style.COLOR_OUTLINE))
            painter.setFont(QFont(style.FONT_FAMILY, style.FONT_SIZE_DOC_SECTION, QFont.Bold))
            painter.drawText(rect, Qt.AlignLeft | Qt.AlignVCenter, text)

        else:  # doc.text
            painter.setPen(QPen(style.COLOR_DOC_TEXT))
            painter.setFont(QFont(style.FONT_FAMILY, style.FONT_SIZE_DOC_TEXT))
            painter.drawText(rect, Qt.AlignLeft | Qt.AlignVCenter, text)

    def _is_doc_note_resizable(self):
        return self.shape_style == "DOC" and self.type_id == "doc.note"

    def _in_resize_handle(self, pos: QPointF) -> bool:
        h = style.DOC_NOTE_RESIZE_HANDLE
        handle_rect = QRectF(self.width - h, self.height - h, h, h)
        return handle_rect.contains(pos)

    def _start_doc_edit(self):
        current_text = self.logic_block.properties.get("Text", "")
        if self.type_id == "doc.note":
            new_text, ok = QInputDialog.getMultiLineText(None, "Edytuj notatkę", "Tekst:", current_text)
        else:
            new_text, ok = QInputDialog.getText(None, "Edytuj tekst", "Tekst:", QLineEdit.Normal, current_text)
        if ok:
            self.apply_doc_text(new_text)

    def apply_doc_text(self, new_text: str):
        """Applies edited Text to a DOC block, pushes undo state, and refits
        its size. Split out from _start_doc_edit() so this path is testable
        without driving a real modal QInputDialog (§6.5)."""
        if new_text == self.logic_block.properties.get("Text", ""):
            return
        self._push_state_if_possible()
        self.logic_block.properties["Text"] = new_text
        self.prepareGeometryChange()
        self._determine_shape_style()
        self.update()

    def _push_state_if_possible(self):
        if self.scene() and self.scene().views():
            window = self.scene().views()[0].window()
            project = getattr(window, 'project', None)
            if project:
                project.push_state()
                window.set_dirty()

    # ---- Tag / Comment (§7) -----------------------------------------------------

    def _effective_tag_and_comment(self):
        """(tag, comment) as they will actually be drawn above the block —
        used by both _paint_tag_and_comment() and boundingRect() so they can
        never disagree about how much space Tag/Comment need (that
        disagreement was exactly bug §1's shape: two places reading related
        state independently and drifting apart).

        For IO blocks whose "Tag" IS their own identifier (Virtual IN/OUT,
        system signals — see _io_identifier()), that value is already shown
        inside the block by _paint_io_tag(); showing it again above the
        block would just duplicate it. Only IO blocks addressed via
        "Address" (DI/DO/AI/AO) treat "Tag" as the separate, generic
        schematic designation from §7.1 here.
        """
        block = self.logic_block
        tag = block.properties.get("Tag", "")
        comment = block.properties.get("Comment", "")

        if self.shape_style == "IO" and not block.properties.get("Address"):
            tag = ""

        return tag, comment

    def _paint_tag_and_comment(self, painter):
        """Tag (bold, above the block) and Comment (italic, below the Tag,
        wrapped to at most 2 lines) — every functional block type, drawn
        from one place so no shape-specific paint method duplicates it."""
        tag, comment = self._effective_tag_and_comment()
        if not tag and not comment:
            return

        y_cursor = -2.0  # just above the block's top edge (y=0)

        if comment:
            comment_font = QFont(style.FONT_FAMILY, style.FONT_SIZE_COMMENT)
            comment_font.setItalic(True)
            max_width = self.width * 3
            lines = self._wrap_lines(comment, comment_font, max_width, max_lines=2)

            painter.setFont(comment_font)
            painter.setPen(QPen(style.COLOR_COMMENT_TEXT))
            line_height = QFontMetricsF(comment_font).height()
            for line in reversed(lines):
                y_cursor -= line_height
                painter.drawText(QRectF(0, y_cursor, max_width, line_height), Qt.AlignLeft | Qt.AlignTop, line)
            y_cursor -= 2

        if tag:
            tag_font = QFont(style.FONT_FAMILY, style.FONT_SIZE_TAG, QFont.Bold)
            painter.setFont(tag_font)
            painter.setPen(QPen(style.COLOR_TAG_TEXT))
            line_height = QFontMetricsF(tag_font).height()
            y_cursor -= line_height
            painter.drawText(QRectF(0, y_cursor, max(self.width, 60), line_height), Qt.AlignLeft | Qt.AlignTop, tag)

    @staticmethod
    def _wrap_lines(text, font, max_width, max_lines):
        """Greedy word-wrap into at most `max_lines` lines that fit
        `max_width`; if text is left over, the last line is elided with an
        ellipsis instead of silently dropping it."""
        fm = QFontMetricsF(font)
        words = text.split()
        lines = []
        current = ""
        i = 0
        while i < len(words):
            word = words[i]
            trial = (current + " " + word).strip()
            if not current or fm.horizontalAdvance(trial) <= max_width:
                current = trial
                i += 1
            else:
                lines.append(current)
                current = ""
                if len(lines) == max_lines:
                    break
        if current and len(lines) < max_lines:
            lines.append(current)
            i = len(words)

        if i < len(words) and lines:
            leftover = " ".join(words[i:])
            lines[-1] = fm.elidedText(f"{lines[-1]} {leftover}", Qt.ElideRight, int(max_width))

        return lines

    def _paint_unconnected_warning(self, painter):
        getter = self._REQUIRED_IDENTIFIER_GETTERS.get(self.shape_style)
        if getter and not getter(self):
            painter.setPen(QPen(Qt.red))
            font = QFont(style.FONT_FAMILY, 8, QFont.Bold)
            painter.setFont(font)
            painter.drawText(QRectF(0, self.height, self.width, 15), Qt.AlignHCenter | Qt.AlignTop, "???")

    # ---- Interaction --------------------------------------------------------

    def contextMenuEvent(self, event):
        menu = QMenu()
        menu.setStyleSheet("""
            QMenu { background-color: #F0F0F0; border: 1px solid #A0A0A0; }
            QMenu::item { padding: 4px 20px; color: black; }
            QMenu::item:selected { background-color: #0078D7; color: white; }
        """)

        prop_action = menu.addAction("Properties")
        menu.addSeparator()
        dup_action = menu.addAction("Duplicate")
        del_action = menu.addAction("Delete")

        action = menu.exec(QCursor.pos())
        if action == del_action:
            if self.scene():
                self.scene().delete_selected_items()
        elif action == dup_action:
            if self.scene():
                self.scene().duplicate_selected_items()
        elif action == prop_action:
            self.setSelected(True)

    def mousePressEvent(self, event):
        if self._is_doc_note_resizable() and self._in_resize_handle(event.pos()):
            self._resizing = True
            self._resize_start_scene_pos = event.scenePos()
            self._resize_start_size = (self.width, self.height)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resizing:
            delta = event.scenePos() - self._resize_start_scene_pos
            min_size = style.GRID_SIZE * 2
            new_w = max(min_size, self._resize_start_size[0] + delta.x())
            new_h = max(min_size, self._resize_start_size[1] + delta.y())
            if self.scene() is None or getattr(self.scene(), 'snap_enabled', True):
                new_w = _round_up_to_grid(new_w)
                new_h = _round_up_to_grid(new_h)

            self.prepareGeometryChange()
            self.width = new_w
            self.height = new_h
            self.logic_block.width = new_w
            self.logic_block.height = new_h
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._resizing:
            self._resizing = False
            self._push_state_if_possible()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if self.shape_style == "DOC":
            self._start_doc_edit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self.scene() is not None:
            if getattr(self.scene(), 'snap_enabled', True):
                grid = getattr(self.scene(), 'grid_size', style.GRID_SIZE)
                return QPointF(round(value.x() / grid) * grid, round(value.y() / grid) * grid)
            return value

        if change == QGraphicsItem.ItemPositionHasChanged:
            self.logic_block.set_position(self.pos().x(), self.pos().y())
            if self.scene():
                from logic_studio.ui.canvas.wire_item import WireItem
                for item in self.scene().items():
                    if isinstance(item, WireItem):
                        if (item.source_port and item.source_port.parentItem() == self) or \
                           (item.dest_port and item.dest_port.parentItem() == self):
                            item.update_path()
        return super().itemChange(change, value)
