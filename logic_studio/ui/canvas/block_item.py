from PySide6.QtWidgets import QGraphicsItem, QStyleOptionGraphicsItem
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QFont, QCursor, QPainterPath, QFontMetricsF
from PySide6.QtWidgets import QMenu
from PySide6.QtCore import Qt, QRectF, QPointF

from logic_studio.ui.canvas import style, shapes

GATE_SHAPES = ("AND", "OR", "NOT", "XOR", "NAND", "NOR", "XNOR", "BUFFER", "GATE_GENERIC")


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

        self.setPos(logic_block.x, logic_block.y)

        self._determine_shape_style()
        self._create_ports()

    def _determine_shape_style(self):
        """Determines the visual rendering style based on category and type_id."""
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

            # Gate sizes are relatively fixed but ports scale
            self.width = 40
            # The body always spans the block's full height now (§2.3) — no
            # separate, possibly-shorter "gate_body_height" to keep in sync
            # with where multi-input ports are actually placed.
            inputs_count = len(self.logic_block.inputs)
            self.height = max(40, inputs_count * 20)

        elif self.category == "Wejścia / Wyjścia":
            self.shape_style = "IO"
            self.width = 80
            # Analog IO shows address+unit and a live value on top of the name,
            # so it needs a bit more room than the single-line DI/DO/VI/VO tags.
            self.height = 45 if self.type_id in ("input.ai", "output.ao") else 30
        else:
            self.shape_style = "COMPLEX"
            # Complex blocks use the win98 style or clean rectangle with properties inside

    def _create_ports(self):
        from logic_studio.ui.canvas.port_item import PortItem

        if self.shape_style in GATE_SHAPES:
            # Inputs distributed evenly on a vertical line (bus bar)
            inputs_count = len(self.logic_block.inputs)
            if inputs_count > 0:
                spacing = self.height / (inputs_count + 1)
                for i, pin in enumerate(self.logic_block.inputs):
                    port = PortItem(pin, parent=self)
                    port.setPos(0, (i + 1) * spacing)

            # Output port sits past the negation bubble for NOT/NAND/NOR/XNOR
            # (§1) — never on top of it, so the bubble stays visible instead
            # of being fully occluded by the port square drawn on top of it.
            output_x = self.width + shapes.gate_output_offset(self.shape_style)
            for pin in self.logic_block.outputs:
                port = PortItem(pin, parent=self)
                port.setPos(output_x, self.height / 2)

        elif self.shape_style == "IO":
            if "input" in self.type_id:
                # Port on the right
                for pin in self.logic_block.outputs: # Input blocks have output pins
                    port = PortItem(pin, parent=self)
                    port.setPos(self.width, self.height / 2)
            else:
                # Port on the left
                for pin in self.logic_block.inputs: # Output blocks have input pins
                    port = PortItem(pin, parent=self)
                    port.setPos(0, self.height / 2)

        else:
            # Complex blocks
            y_offset = 20
            for pin in self.logic_block.inputs:
                port = PortItem(pin, parent=self)
                port.setPos(0, y_offset)
                y_offset += 20

            y_offset = 20
            for pin in self.logic_block.outputs:
                port = PortItem(pin, parent=self)
                port.setPos(self.width, y_offset)
                y_offset += 20

    def boundingRect(self):
        margin = style.BOUNDING_RECT_MARGIN
        block = self.logic_block

        extra_right = 0.0
        if self.shape_style in shapes.NEGATED_GATES:
            extra_right = shapes.gate_output_offset(self.shape_style) + style.PORT_CLICK_MARGIN

        top_margin = margin
        if block.properties.get("Tag") or block.properties.get("Comment"):
            # Room for the Tag line plus up to two Comment lines above the body.
            top_margin = margin + 40

        bottom_margin = margin
        if self.shape_style in GATE_SHAPES:
            # Room for the type-name label drawn below a gate's body (§3.2).
            bottom_margin = margin + 14

        right_margin = margin + extra_right
        if block.properties.get("Comment"):
            # Comment wraps up to 3x the block width (§3.2).
            right_margin = max(right_margin, self.width * 2 + margin)

        return QRectF(
            -margin, -top_margin,
            self.width + margin + right_margin,
            self.height + top_margin + bottom_margin
        )

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)

        if self.shape_style in GATE_SHAPES:
            self._paint_logic_gate(painter)
        elif self.shape_style == "IO":
            self._paint_io_tag(painter)
        else:
            self._paint_complex_block(painter)

        self._paint_tag_and_comment(painter)

        # Draw Unconnected Warning (???)
        self._paint_unconnected_warning(painter)

        # Draw Selection Border
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

        # Type-name label below the gate body, centered (§3.2).
        painter.setPen(QPen(style.COLOR_TYPE_LABEL_TEXT))
        font = QFont(style.FONT_FAMILY, style.FONT_SIZE_PIN_LABEL)
        painter.setFont(font)
        label_rect = QRectF(-10, self.height + 1, self.width + 20, 13)
        painter.drawText(label_rect, Qt.AlignHCenter | Qt.AlignTop, self.logic_block.display_name)

    def _paint_io_tag(self, painter):
        direction = "input" if "input" in self.type_id else "output"
        shapes.draw_io_shape(painter, QRectF(0, 0, self.width, self.height), direction)

        # Draw text
        painter.setPen(QPen(style.COLOR_TYPE_LABEL_TEXT))
        font = QFont(style.FONT_FAMILY, style.FONT_SIZE_PIN_LABEL)
        painter.setFont(font)

        display_text = self.logic_block.display_name

        if self.type_id in ("input.ai", "output.ao"):
            addr = self.logic_block.properties.get("Address", "")
            unit = self._lookup_analog_unit(addr)
            label = f"{addr} [{unit}]" if (addr and unit) else addr
            if label:
                display_text += f"\n{label}"

            sim_value = self.logic_block.simulation_state.get("sim_value")
            if sim_value is not None:
                try:
                    display_text += f"\n{float(sim_value):.2f}"
                except (TypeError, ValueError):
                    pass
        # Tag is no longer shown here as an ad-hoc second line — every block
        # type (IO included) gets it drawn uniformly above the block by
        # _paint_tag_and_comment(), so it isn't duplicated on this one.

        rect = QRectF(10, 2, self.width - 20, self.height - 4)
        painter.drawText(rect, Qt.AlignLeft | Qt.AlignVCenter | Qt.TextWordWrap, display_text)

        # Quality indicator: a red dot when the AI block's last reading was
        # not trustworthy (AUDIT_REPORT.md §2.5/§2.1).
        if self.type_id == "input.ai" and self.logic_block.simulation_state.get("quality") is False:
            painter.setPen(Qt.NoPen)
            painter.setBrush(style.COLOR_ERROR)
            painter.drawEllipse(QPointF(self.width - 6, 6), 4, 4)

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

    def _paint_complex_block(self, painter):
        rect = QRectF(0, 0, self.width, self.height)
        shapes.draw_complex_shape(painter, rect)

        # Inner text
        painter.setPen(style.COLOR_OUTLINE)
        font = QFont(style.FONT_FAMILY, style.FONT_SIZE_PIN_LABEL)
        painter.setFont(font)

        # Type name, centered inside the body (§3.2).
        painter.drawText(rect.adjusted(2, 2, -2, -2), Qt.AlignTop | Qt.AlignHCenter, self.logic_block.display_name)

        # Parameters (e.g. T=1.00[s])
        param_text = ""

        # Live simulation values
        sim_text = ""
        state = self.logic_block.simulation_state

        if self.category == "Timers":
            delay = self.logic_block.properties.get("Delay", 1000)
            param_text = f"T={delay/1000:.2f}[s]"

            if "running" in state:
                if len(self.logic_block.outputs) > 1:
                    val = self.logic_block.outputs[1].value
                    if val is not None:
                        sim_text = f"ET={val/1000:.2f}[s]"

        elif self.category == "Liczniki":
            limit = self.logic_block.properties.get("Limit", 0)
            param_text = f"L={limit}"
            if "count" in state:
                sim_text = f"CV={state['count']}"

        # Draw Parameters
        if param_text:
            painter.setPen(QPen(style.COLOR_TYPE_LABEL_TEXT))
            painter.drawText(rect.adjusted(2, 15, -2, -2), Qt.AlignTop | Qt.AlignLeft, param_text)

        # Draw Live Values
        if sim_text:
            painter.setPen(QPen(Qt.red))
            painter.drawText(rect.adjusted(2, 28, -2, -2), Qt.AlignTop | Qt.AlignLeft, sim_text)

    def _paint_tag_and_comment(self, painter):
        """Tag (bold, above the block) and Comment (italic, below the Tag,
        wrapped to at most 2 lines) — every block type, drawn from one place
        so no shape-specific paint method duplicates it (§3.2)."""
        block = self.logic_block
        tag = block.properties.get("Tag", "")
        comment = block.properties.get("Comment", "")
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
        # Draw red '???' near unassigned tags or completely unconnected critical blocks
        # Simplified logic: If it's an IO tag and has no Tag property, show ???
        # (unchanged pre-existing check — see AUDIT_REPORT.md for the Tag/Address
        # naming overlap this predates; not in scope for this PR).
        if self.shape_style == "IO":
            tag = self.logic_block.properties.get("Tag", "")
            if not tag:
                painter.setPen(QPen(Qt.red))
                font = QFont(style.FONT_FAMILY, 8, QFont.Bold)
                painter.setFont(font)
                painter.drawText(QRectF(0, self.height, self.width, 15), Qt.AlignHCenter | Qt.AlignTop, "???")

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

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self.scene() is not None:
            if getattr(self.scene(), 'snap_enabled', True):
                grid = getattr(self.scene(), 'grid_size', 20)
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
