"""fix/wire-labels-and-project-integrity §A3 — the mutation logic behind
"Nadaj etykietę.../Usuń etykietę/Zamień na odnośnik" (a fully-connected
WireItem's context menu) and "Dodaj odnośnik..." (an unconnected port's
context menu). Kept separate from wire_item.py/port_item.py so the
graphics-item classes stay focused on presentation and menu wiring —
this module never touches a QGraphicsItem, only Project/Wire/Pin.
"""
from logic_studio.blocks.pin import Pin
from logic_studio.core.wire import Wire

# §A3.2: "długość dwa oczka siatki" — two grid cells, GRID_SNAP being
# the same unit ports/blocks already snap to (style.py).
_STUB_GRID_CELLS = 2


def find_wire_for_pins(project, pin_a_uuid, pin_b_uuid):
    """The Wire record (if any) whose two real ends are EXACTLY this
    pair — mirrors Project.remove_wire_by_pins()'s own matching rule
    (either ordering, since source/dest only ever recorded which end
    the user clicked first while drawing, never a logical distinction —
    see wire_item.py's own note on this)."""
    pins = {pin_a_uuid, pin_b_uuid}
    for wire in project.wires:
        if {wire.source_pin, wire.dest_pin} == pins:
            return wire
    return None


def get_or_create_wire_for_pins(project, pin_a_uuid, pin_b_uuid) -> Wire:
    """The Wire record for this already-connected pin pair, creating a
    fresh one if this is the common case (a plain wire with no metadata
    of its own yet — core/wire.py's own module docstring on why THAT
    case normally carries no Wire record at all) and the caller is
    about to attach a label to it, which does require one."""
    existing = find_wire_for_pins(project, pin_a_uuid, pin_b_uuid)
    if existing is not None:
        return existing
    wire = Wire()
    wire.source_pin = pin_a_uuid
    wire.dest_pin = pin_b_uuid
    project.add_wire(wire)
    return wire


def clear_label_and_prune_if_pointless(project, wire) -> None:
    """§A3.1 "Usuń etykietę": blanks the label, then removes the Wire
    record entirely if it no longer carries anything Pin.connections
    can't already represent on its own (fully connected, no free end,
    no label — core/wire.py's own "gets NO Wire record at all" case) —
    otherwise an empty, pointless Wire record would sit in
    project.wires forever, exactly the kind of drift
    check_wire_pin_consistency()/state_diff exist to catch, not create."""
    wire.label = ""
    if wire.is_fully_connected():
        project.remove_wire(wire)


def _stub_offset(scene, direction_sign: int):
    from logic_studio.ui.canvas import style
    grid = getattr(scene, "grid_size", style.GRID_SNAP)
    return _STUB_GRID_CELLS * grid * direction_sign


def add_stub_wire_from_port(project, port_item) -> Wire:
    """§A3.2 "Dodaj odnośnik...": a fresh free-end Wire anchored at
    `port_item.pin`, its free end positioned a short, fixed distance
    OUT of the port in the direction the port itself faces (the same
    "which side of the block" facing wire_item.py's own routing already
    computes for a real wire's first/last segment — reused here rather
    than reimplemented, see the import below)."""
    from logic_studio.ui.canvas.wire_item import _port_facing

    pin = port_item.pin
    scene_pos = port_item.scenePos()
    dx = _stub_offset(port_item.scene(), _port_facing(port_item))
    free_pos = {"x": scene_pos.x() + dx, "y": scene_pos.y()}

    wire = Wire()
    if pin.direction == Pin.DIR_OUTPUT:
        wire.source_pin = pin.uuid
        wire.free_end_dest = free_pos
    else:
        wire.dest_pin = pin.uuid
        wire.free_end_source = free_pos
    project.add_wire(wire)
    return wire


def convert_wire_to_stubs(project, source_port, dest_port) -> tuple:
    """§A3.1 "Zamień na odnośnik": cuts the physical connection between
    `source_port.pin` and `dest_port.pin` (Pin.disconnect(), same as
    outright deleting the wire — ui/canvas/scene.py's own
    delete_selected_items() WireItem branch) and replaces it with TWO
    independent free-end Wire records, one stub at each original port,
    each facing the same direction that port's own real wire segment
    always leaves/enters from. Returns (wire_at_source, wire_at_dest) —
    caller applies one shared label to both (§A3.1: "pyta o nazwę raz,
    dla obu końców"). Does NOT push undo state or remove the old
    WireItem graphics itself — the caller (WireItem.contextMenuEvent)
    already owns that, the same split delete_selected_items() uses
    between pin-graph and canvas-graphics cleanup."""
    source_pin, dest_pin = source_port.pin, dest_port.pin
    old_wire = find_wire_for_pins(project, source_pin.uuid, dest_pin.uuid)
    if old_wire is not None:
        project.remove_wire(old_wire)
    source_pin.disconnect(dest_pin)

    wire_at_source = add_stub_wire_from_port(project, source_port)
    wire_at_dest = add_stub_wire_from_port(project, dest_port)
    return wire_at_source, wire_at_dest
