"""fix/wire-labels-and-project-integrity §A1/§A2 — the one thing the
Wire data model (feat/wire-labels) existed to make possible and had
never actually done: two wires carrying the same label are ONE AND THE
SAME network node, wherever they physically sit on the schematic.
Before this module, `Wire.label` was pure, inert text — the compiler
never looked at it, so a labeled free end simply carried no signal at
all (Validator only warned "Input unconnected", never explaining why).

RULE: label comparison is CASE-INSENSITIVE ("Blokada ZS" and
"blokada zs" name the same node) and applies UNIFORMLY regardless of
wire geometry (§A1.2) — a fully-connected wire's label is purely
documentary ON ITS OWN (its two pins are already connected to each
other; merging changes nothing), but the INSTANT another wire anywhere
in the project shares that label, every pin from every wire in the
group becomes one node, free end or not. No special case for "how many
free ends" — that would make validation depend on schematic geometry,
which is exactly the kind of hidden, hard-to-predict rule this project
avoids elsewhere (BaseLogicBlock.evaluate()'s own docs make the same
argument against implicit per-type defaults).

Merging happens by literally calling the SAME `Pin.connect()` every
ordinary, physically-drawn wire already goes through — never a second,
parallel notion of "connected" that GraphBuilder/Exporter would have to
be taught about separately. This is what makes the "identical
execution_order" contract (this module's own test suite, and the
Part A acceptance test) hold BY CONSTRUCTION: after this pass runs,
a labeled network and a directly-wired equivalent are, from every
downstream stage's point of view, indistinguishable — same
Pin.connections, same graph, same execution order, same simulation
result. Called on `_ExpandedProjectView`'s already-cloned pins
(compiler/core.py's `compile_view`) — see that module's own note on
why mutating THOSE pins is always safe (never the live project's own).
"""
from logic_studio.blocks.pin import Pin


def group_labeled_pins(wires, blocks) -> dict:
    """Returns {label.lower(): {"label": <label as first seen>,
    "pins": [Pin, ...], "wires": [Wire, ...]}} for every wire carrying a
    non-empty (after stripping) label. A wire's OWN two ends can each
    contribute a pin (a fully-connected wire contributes both; a
    free-end wire contributes whichever single end is real) — the same
    pin object appearing via more than one wire in the same group
    (a fully-connected wire's own pair, both already this node) is
    listed once."""
    pin_by_uuid = {}
    for block in blocks:
        for pin in block.inputs + block.outputs:
            pin_by_uuid[pin.uuid] = pin

    groups = {}
    for wire in wires:
        label = (wire.label or "").strip()
        if not label:
            continue
        key = label.lower()
        group = groups.setdefault(key, {"label": label, "pins": [], "wires": []})
        group["wires"].append(wire)
        for pin_uuid in (wire.source_pin, wire.dest_pin):
            if pin_uuid is None:
                continue
            pin = pin_by_uuid.get(pin_uuid)
            if pin is not None and pin not in group["pins"]:
                group["pins"].append(pin)
    return groups


def describe_label_groups(wires, blocks) -> dict:
    """Read-only summary of every label group, for UI rendering
    (ui/canvas/wire_item.py's §A4.2/§A4.3/§A4.4) — computed ONCE per
    scene rebuild rather than inside paint() (called far too often to
    afford re-running grouping/validation on every repaint), and never
    calls Pin.connect() the way merge_and_validate_labels() does, so
    it's always safe to run directly against the LIVE project (never
    needs compile_view's throwaway clones).

    Returns {label.lower(): {"source_pos": (x, y) | None,
    "receiver_count": int, "has_error": bool}} — "source_pos" is the
    single source block's (x, y) if there is exactly one (None
    otherwise, including the "no source"/"multiple sources" error
    cases — nothing meaningful to point at); "has_error" mirrors
    exactly the conditions merge_and_validate_labels() itself would
    raise as compiler errors (wrong source count, or a type mismatch
    between the source and any receiver)."""
    groups = group_labeled_pins(wires, blocks)
    pin_to_block = {}
    for block in blocks:
        for pin in block.inputs + block.outputs:
            pin_to_block[pin.uuid] = block

    summary = {}
    for key, group in groups.items():
        pins = group["pins"]
        outputs = [p for p in pins if p.direction == Pin.DIR_OUTPUT]
        inputs = [p for p in pins if p.direction == Pin.DIR_INPUT]

        has_error = len(outputs) != 1
        source_pos = None
        if len(outputs) == 1:
            source = outputs[0]
            source_block = pin_to_block.get(source.uuid)
            if source_block is not None:
                source_pos = (source_block.x, source_block.y)
            for target in inputs:
                if (source.data_type != Pin.TYPE_ANY and target.data_type != Pin.TYPE_ANY
                        and source.data_type != target.data_type):
                    has_error = True

        summary[key] = {
            "source_pos": source_pos,
            "receiver_count": len(inputs),
            "has_error": has_error,
        }
    return summary


def _ref_for_pin(pin, blocks) -> str:
    for block in blocks:
        if pin in block.inputs or pin in block.outputs:
            return block.short_id or block.display_name
    return "?"


def merge_and_validate_labels(view, errors: list, warnings: list) -> None:
    """§A1/§A2's actual pass. Call BEFORE Validator (so its generic
    "Input is unconnected" check sees an input fed by a label as
    correctly connected, not flagged one stage too early — this was
    the actual, verified reason for this ordering, not just tidiness)
    and, transitively, BEFORE GraphBuilder (so the merged edges are in
    place — Pin.connections — by the time the graph is built; §A1's own
    acceptance test is exactly this: a labeled project and a directly-
    wired equivalent must compile to an identical execution_order).

    §A1.4 (type inheritance): NOT a separate check here — `Pin.connect()`
    already rejects a BOOL<->REAL-shaped mismatch on its own (blocks/
    pin.py's existing "Strict type checking"), so the source pin's type
    is enforced on every receiver simply by going through the same
    connect() every physically-drawn wire uses; this function only adds
    the label to the resulting message so a rejected connection is
    locatable (§A1.3)."""
    groups = group_labeled_pins(view.wires, view.blocks)

    for key in sorted(groups):
        group = groups[key]
        label = group["label"]
        pins = group["pins"]
        outputs = [p for p in pins if p.direction == Pin.DIR_OUTPUT]
        inputs = [p for p in pins if p.direction == Pin.DIR_INPUT]

        if not outputs:
            errors.append(f"Etykieta '{label}' nie ma źródła.")
            continue
        if len(outputs) > 1:
            refs = sorted({_ref_for_pin(p, view.blocks) for p in outputs})
            errors.append(f"Etykieta '{label}' ma więcej niż jedno źródło: {', '.join(refs)}.")
            continue
        source = outputs[0]

        if not inputs:
            warnings.append(f"Sygnał '{label}' nigdzie nie jest odbierany.")
            continue

        source_ref = _ref_for_pin(source, view.blocks)
        for target in inputs:
            if not source.connect(target):
                target_ref = _ref_for_pin(target, view.blocks)
                errors.append(
                    f"[{target_ref}] Niezgodny typ danych na wejściu połączonym przez "
                    f"etykietę '{label}' ze źródłem [{source_ref}] (typ {source.data_type})."
                )
