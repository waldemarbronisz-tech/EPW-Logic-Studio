from PySide6.QtWidgets import QGraphicsPathItem
from PySide6.QtGui import QPainterPath, QPen, QColor
from PySide6.QtCore import Qt, QPointF

from logic_studio.ui.canvas import style


def _port_facing(port) -> int:
    """+1 if `port` is mounted on the RIGHT edge of its parent block, -1
    if on the LEFT edge — every port in this app sits at local x=0 or
    x=width (see BlockItem's own pin-layout code), so this threshold is
    safe regardless of block type, and regardless of whether the port is
    nominally an input or an output: a WireItem's source_port/dest_port
    only record which end the user clicked FIRST/SECOND while dragging a
    new wire, not which one is logically the output — routing off of each
    port's own mounted side, rather than off source-vs-dest or relative
    on-screen position, is what makes a wire always leave/enter a module
    from the side its own connector is actually on."""
    parent = port.parentItem()
    width = getattr(parent, 'width', None)
    if not width:
        return 1
    return 1 if port.pos().x() >= width / 2.0 else -1


class WireItem(QGraphicsPathItem):
    def __init__(self, source_port, dest_port=None, parent=None):
        super().__init__(parent)
        self.source_port = source_port
        self.dest_port = dest_port
        self.temp_end_point = None # Used when dragging a new wire

        self.setZValue(-1) # Draw wires behind blocks
        self.setFlag(QGraphicsPathItem.ItemIsSelectable, True)

        self.color = style.COLOR_LOGIC_LOW # OFF state
        self.thickness = style.WIRE_THICKNESS

        self.update_path()

    def update_live_state(self):
        """Update wire color based on source port pin value."""
        if not self.source_port or not self.source_port.pin:
            return

        val = self.source_port.pin.value
        if isinstance(val, bool):
            self.color = style.COLOR_LOGIC_HIGH if val else style.COLOR_LOGIC_LOW
        elif val is not None:
            self.color = style.COLOR_ANALOG_VALUE
        else:
            self.color = style.COLOR_LOGIC_LOW

        self.update_path()

    def update_path(self):
        if not self.source_port:
            return

        # feat/clipboard-and-align §4.3: a wire LEAVING a disabled block
        # (i.e. this wire's SOURCE pin belongs to one) is dimmed right
        # along with the block itself — recomputed on every path update, so
        # toggling a block's enabled state (scene.set_blocks_enabled())
        # takes effect immediately without needing a fresh connection.
        source_block = self.source_port.parentItem()
        source_logic_block = getattr(source_block, 'logic_block', None)
        self.setOpacity(0.35 if source_logic_block is not None and not source_logic_block.enabled else 1.0)

        start_pos = self.source_port.scenePos()
        end_pos = self.dest_port.scenePos() if self.dest_port else self.temp_end_point

        if not end_pos:
            return

        path = QPainterPath(start_pos)

        # Orthogonal Manhattan routing, rigid/square (no rounding), built
        # from a padded "stub" at each end that always points OUT of its
        # own connector — rightward from a right-mounted port, leftward
        # from a left-mounted one (see _port_facing()) — instead of
        # deciding direction from which end is source vs dest or from
        # their relative on-screen X. That old relative-position test
        # (previously: route straight across only when the dest was
        # comfortably to the right; loop around otherwise) could make a
        # module's own wires leave/enter from whichever side happened to
        # face the other end that particular time, and looked especially
        # wrong for a short vertical offset with little horizontal room:
        # the "loop around" shape's own 15px final approach segment is
        # easy to miss at a glance next to a 40px+ forced detour, reading
        # as "enters from below" even though it technically still entered
        # from the left. Padding BOTH ends first and only THEN connecting
        # the two stub points (which — since both already face the right
        # way — can always be joined by a plain 2-bend Manhattan path, no
        # separate "is there room" case) makes every wire's own
        # first/last segment the same fixed length in the correct
        # direction regardless of geometry, forward or backward.
        offset = 15  # Minimum extension before turning

        start_stub = QPointF(start_pos.x() + offset * _port_facing(self.source_port), start_pos.y())

        if self.dest_port is not None:
            end_stub = QPointF(end_pos.x() + offset * _port_facing(self.dest_port), end_pos.y())
        else:
            # Dragging a new wire with no real pin at the far end yet —
            # just follow the cursor directly, no padding to fake.
            end_stub = end_pos

        path.lineTo(start_stub.x(), start_stub.y())
        if abs(start_stub.y() - end_stub.y()) < 0.5:
            path.lineTo(end_stub.x(), end_stub.y())
        else:
            mid_x = (start_stub.x() + end_stub.x()) / 2.0
            path.lineTo(mid_x, start_stub.y())
            path.lineTo(mid_x, end_stub.y())
            path.lineTo(end_stub.x(), end_stub.y())
        if end_stub != end_pos:
            path.lineTo(end_pos.x(), end_pos.y())

        self.setPath(path)

        # SquareCap and MiterJoin ensure strict 90-degree visually sharp lines
        pen = QPen(self.color, self.thickness, Qt.SolidLine, Qt.SquareCap, Qt.MiterJoin)
        if self.isSelected():
            pen.setColor(style.COLOR_WIRE_SELECTED)
            pen.setWidth(self.thickness) # Keep thickness same but change color
        self.setPen(pen)
