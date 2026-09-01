from PySide6.QtWidgets import QGraphicsItem, QStyleOptionGraphicsItem
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QFont, QCursor, QPainterPath
from PySide6.QtWidgets import QMenu
from PySide6.QtCore import Qt, QRectF, QPointF

class BlockItem(QGraphicsItem):
    def __init__(self, logic_block, parent=None):
        super().__init__(parent)
        self.logic_block = logic_block

        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)

        # Industrial look colors
        self.bg_color = QColor(255, 255, 255) # Clean white for most blocks
        self.header_color = QColor(100, 100, 100)
        if logic_block.color.startswith("#"):
            self.header_color = QColor(logic_block.color)

        self.border_color = QColor(0, 0, 0)
        self.selected_color = QColor(0, 120, 215) # Standard selection blue
        self.live_color = QColor(0, 170, 0) # Green for logic 1

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
            if self.type_id.startswith("logic.and"):
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
            self.gate_body_height = 40
            # Height depends on input count
            inputs_count = len(self.logic_block.inputs)
            self.height = max(40, inputs_count * 20)

        elif self.category == "Wejścia / Wyjścia":
            self.shape_style = "IO"
            self.width = 80
            self.height = 30
        else:
            self.shape_style = "COMPLEX"
            # Complex blocks use the win98 style or clean rectangle with properties inside

    def _create_ports(self):
        from logic_studio.ui.canvas.port_item import PortItem

        if self.shape_style in ["AND", "OR", "NOT", "XOR", "NAND", "NOR", "XNOR", "GATE_GENERIC"]:
            # Inputs distributed evenly on a vertical line (bus bar)
            inputs_count = len(self.logic_block.inputs)
            if inputs_count > 0:
                spacing = self.height / (inputs_count + 1)
                for i, pin in enumerate(self.logic_block.inputs):
                    port = PortItem(pin, parent=self)
                    port.setPos(0, (i + 1) * spacing)

            # Single output in the middle right
            for pin in self.logic_block.outputs:
                port = PortItem(pin, parent=self)
                port.setPos(self.width, self.height / 2)

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
        margin = 15
        return QRectF(-margin, -margin, self.width + margin*2, self.height + margin*2)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)

        if self.shape_style in ["AND", "OR", "NOT", "XOR", "NAND", "NOR", "XNOR"]:
            self._paint_logic_gate(painter)
        elif self.shape_style == "IO":
            self._paint_io_tag(painter)
        else:
            self._paint_complex_block(painter)

        # Draw Unconnected Warning (???)
        self._paint_unconnected_warning(painter)

        # Draw Selection Border
        if self.isSelected():
            rect = QRectF(0, 0, self.width, self.height)
            pen = QPen(self.selected_color, 1, Qt.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(rect.adjusted(-4, -4, 4, 4))

    def _paint_logic_gate(self, painter):
        painter.setPen(QPen(Qt.black, 1))
        painter.setBrush(Qt.NoBrush)

        path = QPainterPath()

        # Center the gate body vertically if the block is tall (many inputs)
        body_y = (self.height - self.gate_body_height) / 2

        # Draw vertical input bus bar if needed
        if self.height > self.gate_body_height:
             painter.drawLine(0, 0, 0, self.height)

        if self.shape_style in ["AND", "NAND"]:
            # D-shape
            path.moveTo(0, body_y)
            path.lineTo(self.width / 2, body_y)
            path.arcTo(0, body_y, self.width, self.gate_body_height, 90, -180)
            path.lineTo(0, body_y + self.gate_body_height)
            path.closeSubpath()
        elif self.shape_style in ["OR", "NOR", "XOR", "XNOR"]:
            # Shield-shape
            path.moveTo(0, body_y)
            path.quadTo(self.width * 0.75, body_y, self.width, body_y + self.gate_body_height / 2)
            path.quadTo(self.width * 0.75, body_y + self.gate_body_height, 0, body_y + self.gate_body_height)
            path.quadTo(self.width * 0.25, body_y + self.gate_body_height / 2, 0, body_y)

            if self.shape_style in ["XOR", "XNOR"]:
                # Draw extra arc
                extra_path = QPainterPath()
                extra_path.moveTo(-4, body_y)
                extra_path.quadTo(self.width * 0.25 - 4, body_y + self.gate_body_height / 2, -4, body_y + self.gate_body_height)
                painter.drawPath(extra_path)

        elif self.shape_style == "NOT":
            # Triangle
            path.moveTo(0, body_y)
            path.lineTo(self.width - 6, body_y + self.gate_body_height / 2)
            path.lineTo(0, body_y + self.gate_body_height)
            path.closeSubpath()

        painter.drawPath(path)

        # Draw inversion circles
        if self.shape_style in ["NOT", "NAND", "NOR", "XNOR"]:
            painter.setBrush(Qt.white)
            painter.drawEllipse(QPointF(self.width, self.height / 2), 3, 3)

    def _paint_io_tag(self, painter):
        painter.setPen(QPen(Qt.black, 1))
        painter.setBrush(Qt.white)

        path = QPainterPath()

        if "input" in self.type_id:
            # Chevron pointing right
            path.moveTo(0, 0)
            path.lineTo(self.width - 10, 0)
            path.lineTo(self.width, self.height / 2)
            path.lineTo(self.width - 10, self.height)
            path.lineTo(0, self.height)
            path.closeSubpath()
        else:
            # Chevron with indentation on left
            path.moveTo(0, 0)
            path.lineTo(self.width, 0)
            path.lineTo(self.width, self.height)
            path.lineTo(0, self.height)
            path.lineTo(10, self.height / 2)
            path.closeSubpath()

        painter.drawPath(path)

        # Draw text
        painter.setPen(QPen(QColor(0, 100, 0))) # Dark green text
        font = QFont("Arial", 7)
        painter.setFont(font)

        display_text = self.logic_block.display_name
        tag = self.logic_block.properties.get("Tag", "")
        if tag:
             display_text += f"\n{tag}"

        rect = QRectF(10, 2, self.width - 20, self.height - 4)
        painter.drawText(rect, Qt.AlignLeft | Qt.AlignVCenter | Qt.TextWordWrap, display_text)

    def _paint_complex_block(self, painter):
        rect = QRectF(0, 0, self.width, self.height)

        # Simple crisp rectangle
        painter.setPen(QPen(Qt.black, 1))
        painter.setBrush(Qt.white)
        painter.drawRect(rect)

        # Inner text
        painter.setPen(Qt.black)
        font = QFont("Arial", 7)
        painter.setFont(font)

        # Title
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
            painter.setPen(QPen(QColor(0, 100, 0)))
            painter.drawText(rect.adjusted(2, 15, -2, -2), Qt.AlignTop | Qt.AlignLeft, param_text)

        # Draw Live Values
        if sim_text:
            painter.setPen(QPen(Qt.red))
            painter.drawText(rect.adjusted(2, 28, -2, -2), Qt.AlignTop | Qt.AlignLeft, sim_text)

    def _paint_unconnected_warning(self, painter):
        # Draw red '???' near unassigned tags or completely unconnected critical blocks
        # Simplified logic: If it's an IO tag and has no Tag property, show ???
        if self.shape_style == "IO":
            tag = self.logic_block.properties.get("Tag", "")
            if not tag:
                painter.setPen(QPen(Qt.red))
                font = QFont("Arial", 8, QFont.Bold)
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
