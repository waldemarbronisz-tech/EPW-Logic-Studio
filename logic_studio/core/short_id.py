"""feat/io-labels-and-ids §4 — short, human-readable block identifiers.

Problem: the property panel and compiler messages showed a raw UUID (36
characters nobody reads or reads out over the phone). e²TANGO shows
something like "x181" instead — a category letter plus a running number.

Format: <letter><n>, e.g. "g12", "i3", "o7". The letter is derived from the
block's own type_id (or, for the generic "Elementy Analogowe" library
category, from that category — comparators/math/analog-processing blocks
all share it and there's no shorter, equally clear split).

Assignment happens exactly once, in Project.add_block() — the single choke
point every block passes through whether it comes from the library, a
paste/duplicate, or the project loader (see Project.deserialize(), which
calls add_block() once per block in FILE ORDER — that's what makes loading
an older project without short_id assign ids deterministically in file
order "for free", with no separate migration pass needed). A block that
already carries a short_id (restored from a save file via
BaseLogicBlock.SERIALIZED_FIELDS) is left alone.

The counter is a project-persistent, monotonically increasing value per
prefix (project.settings["short_id_counters"]) — NOT derived by scanning
which numbers are currently in use, because that would let a deleted
block's number be reissued (§4.2: renumbering after a delete is exactly
what makes comparing two versions of a project confusing "did g3 come back,
or is this a different block").
"""
import re

# Category letter, by type_id — the primary lookup (§4.1's table).
_PREFIX_BY_TYPE_ID = {
    # g — logic gates
    "logic.and": "g", "logic.and3": "g", "logic.and4": "g",
    "logic.or": "g", "logic.or3": "g", "logic.or4": "g",
    "logic.not": "g", "logic.xor": "g",
    "logic.nand": "g", "logic.nand3": "g", "logic.nand4": "g",
    "logic.nor": "g", "logic.nor3": "g", "logic.nor4": "g",
    "logic.xnor": "g", "logic.buffer": "g",
    # i — inputs: DI, AI, and the internal-signal blocks that READ a bit/
    # register another block writes (virtual.input/internal.reg_in)
    "input.di": "i", "input.ai": "i", "virtual.input": "i", "internal.reg_in": "i",
    # o — outputs: DO, AO, and the internal-signal blocks that WRITE one
    "output.do": "o", "output.ao": "o", "virtual.output": "o", "internal.reg_out": "o",
    # t — timers
    "timer.ton": "t", "timer.tof": "t", "timer.tp": "t",
    # f — flip-flops / latches
    "memory.sr": "f", "memory.rs": "f",
    # e — edge detection
    "edge.rtrig": "e", "edge.ftrig": "e", "edge.change": "e",
    # c — counters
    "counter.ctu": "c", "counter.ctd": "c", "counter.ctud": "c",
    # d — documentation (non-executable canvas annotations)
    "doc.text": "d", "doc.note": "d", "doc.section": "d",
}

# Fallback lookup by library category, for type_ids not listed above.
# "Elementy Analogowe" spans analog_processing.py, comparators.py and
# math_blocks.py — different modules, same library category, same letter.
_PREFIX_BY_CATEGORY = {
    "Elementy Analogowe": "a",
}

DEFAULT_PREFIX = "x"  # everything else: constants, system signals, buttons, LEDs, ...

_SHORT_ID_RE = re.compile(r"^([a-z]+)(\d+)$")


def prefix_for_block(block) -> str:
    """The single category letter this block's short_id should use."""
    prefix = _PREFIX_BY_TYPE_ID.get(block.type_id)
    if prefix:
        return prefix
    return _PREFIX_BY_CATEGORY.get(block.category, DEFAULT_PREFIX)


def assign_short_id(project, block) -> str:
    """Assigns a new, never-before-used short_id to `block` and returns it.
    Advances project's persistent per-prefix counter — always forward,
    never derived from a scan of what's currently in use (see module
    docstring: a deleted block's number must never be reissued)."""
    prefix = prefix_for_block(block)
    counters = project.settings.setdefault("short_id_counters", {})
    next_n = counters.get(prefix, 1)
    counters[prefix] = next_n + 1
    block.short_id = f"{prefix}{next_n}"
    return block.short_id


def resync_counters_with_existing_ids(project, short_ids):
    """Fast-forwards every per-prefix counter past whatever short_ids are
    already present, so a freshly assigned id can never collide with one
    that's about to be restored from the same file. `short_ids` is any
    iterable of short_id strings (e.g. read straight off the raw per-block
    JSON dicts before blocks are even constructed — see
    Project.deserialize()). Malformed/empty entries are ignored."""
    counters = project.settings.setdefault("short_id_counters", {})
    for sid in short_ids:
        if not sid:
            continue
        m = _SHORT_ID_RE.match(sid)
        if not m:
            continue
        prefix, n = m.group(1), int(m.group(2))
        counters[prefix] = max(counters.get(prefix, 1), n + 1)
