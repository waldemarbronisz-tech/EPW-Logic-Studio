"""feat/help-system §2 — generates the block catalog straight from
BlockRegistry, at the moment help is opened, not from a file saved to
disk. This project has a documented history of documentation drifting
from the code it describes (REPORT.md stalling at phase 8 with 18
branches already merged; a stale test count in AUDIT_REPORT.md off by
almost 30x; a library-category claim contradicted 120 lines later in
the same document) — a hand-maintained "69 block types" reference would
rot the same way after two PRs. Generating it live from BlockRegistry
means adding a block automatically adds it to help; nothing to remember.

Headless (no PySide6 import) — same core/UI split as core/crossref.py
vs. ui/panels/signals.py, and core/help_content.py below: this module
is testable without a QApplication, and reusable for the "Eksportuj
katalog bloków..." menu action (§2.4) with no UI dependency at all.
"""
from logic_studio.blocks.registry import BlockRegistry

# feat/help-system §5.5-adjacent convenience: a category label -> a short
# blurb, shown as the intro line of that category's page in the "Katalog
# bloków" chapter. Not required for any individual block's own page.
_CATEGORY_INTROS = {}


def _direction_label(pin) -> str:
    from logic_studio.blocks.pin import Pin
    return "Wejście" if pin.direction == Pin.DIR_INPUT else "Wyjście"


def describe_block_type(type_id: str) -> dict:
    """A single registered block type's full catalog entry, built from a
    throwaway instance (BlockRegistry.create_block()) exactly like
    ui/panels/element_preview.py's own show_type_id() already does for
    a library-tree selection — never a live, placed instance, since a
    type can be described before any exists on a canvas.

    Returns None for an unknown/unregistered type_id (a macro instance
    type_id included — macros are catalogued separately, see
    macro_catalog_entries() below, since their pins vary per PROJECT,
    not per fixed registered type)."""
    block_class = BlockRegistry.get_block_class(type_id)
    if block_class is None:
        return None
    from logic_studio.blocks.macro_instance import MacroInstanceBlock
    if block_class is MacroInstanceBlock:
        return None

    block = block_class()
    pins = []
    for pin in block.inputs + block.outputs:
        pins.append({
            "name": pin.name,
            "direction": _direction_label(pin),
            "data_type": pin.data_type,
            "description": block.pin_description(pin.name),
            "safety_relevant": bool(getattr(pin, "safety_relevant", False)),
        })

    properties = []
    for key, value in block.properties.items():
        properties.append({
            "key": key,
            "type": type(value).__name__,
            "default": value,
            "unit": block.property_unit(key),
            "description": block.property_description(key),
        })

    return {
        "type_id": type_id,
        "display_name": block.display_name,
        "category": block.category,
        "description": block.description,
        "pins": pins,
        "properties": properties,
        "aliases": list(block.aliases),
    }


def generate_catalog() -> dict:
    """{category: [entry, ...]}, entries sorted by type_id within each
    category, categories in BlockRegistry's own registration order
    (get_categories() — first-registered-category-first, matching the
    order the Library panel's own tree already presents them in, so the
    help catalog's chapter order looks familiar rather than arbitrarily
    re-sorted alphabetically)."""
    catalog = {}
    for category in BlockRegistry.get_categories():
        entries = []
        for type_id in sorted(BlockRegistry.get_blocks_in_category(category)):
            entry = describe_block_type(type_id)
            if entry is not None:
                entries.append(entry)
        if entries:
            catalog[category] = entries
    return catalog


def all_type_ids() -> list:
    """Every registered, cataloguable type_id (macro instances excluded,
    see describe_block_type()'s own note) — used by the guardian test
    and by help_content.py to enumerate "block:<type_id>" topics."""
    ids = []
    for category, entries in generate_catalog().items():
        ids.extend(e["type_id"] for e in entries)
    return ids


# ---- Markdown rendering (feat/help-system §2.1/§4) -------------------------

def _escape_pipe(text: str) -> str:
    """A literal "|" inside a Markdown table cell breaks the table -
    property/pin descriptions are free text and could contain one."""
    return str(text).replace("|", "\\|").replace("\n", " ")


def block_entry_markdown(entry: dict) -> str:
    """One block type's full catalog page, as Markdown -
    core/help_content.py's HelpContentStore treats a "block:<type_id>"
    topic id as a request to call this instead of reading a .md file
    (§4: the catalog is generated, not hand-written, right down to the
    page a viewer actually reads)."""
    lines = [
        f"# {entry['display_name']}",
        "",
        f"`{entry['type_id']}` — {entry['category']}",
        "",
        entry["description"] or "*(brak opisu)*",
        "",
    ]

    if entry["pins"]:
        lines.append("## Piny")
        lines.append("")
        lines.append("| Nazwa | Kierunek | Typ | Opis |")
        lines.append("|---|---|---|---|")
        for pin in entry["pins"]:
            desc = _escape_pipe(pin["description"] or "")
            if pin["safety_relevant"]:
                desc = f"**{desc}** ⚠ istotne dla bezpieczeństwa"
            lines.append(
                f"| {_escape_pipe(pin['name'])} | {pin['direction']} | "
                f"{_escape_pipe(pin['data_type'])} | {desc} |"
            )
        lines.append("")

    if entry["properties"]:
        lines.append("## Właściwości")
        lines.append("")
        lines.append("| Nazwa | Typ | Domyślna | Jednostka | Opis |")
        lines.append("|---|---|---|---|---|")
        for prop in entry["properties"]:
            lines.append(
                f"| {_escape_pipe(prop['key'])} | {_escape_pipe(prop['type'])} | "
                f"{_escape_pipe(prop['default'])} | {_escape_pipe(prop['unit'] or '—')} | "
                f"{_escape_pipe(prop['description'] or '')} |"
            )
        lines.append("")

    if entry["aliases"]:
        lines.append("**Aliasy wyszukiwania:** " + ", ".join(entry["aliases"]))
        lines.append("")

    return "\n".join(lines)


def category_index_markdown(category: str, entries: list) -> str:
    """The category's own landing page — a plain list of its block
    types, each linking to its own "block:<type_id>" topic."""
    lines = [f"# {category}", ""]
    for entry in entries:
        lines.append(f"- [{entry['display_name']}](help://block:{entry['type_id']}) — {entry['description']}")
    return "\n".join(lines) + "\n"


def export_catalog_markdown() -> str:
    """§2.4: the whole catalog as one standalone Markdown document — used
    by Help > "Eksportuj katalog bloków..." to save a file for
    coordination meetings/project documentation, independent of the
    interactive help window."""
    catalog = generate_catalog()
    parts = ["# Katalog bloków EPW Logic Studio", ""]
    for category, entries in catalog.items():
        parts.append(f"## {category}")
        parts.append("")
        for entry in entries:
            parts.append(block_entry_markdown(entry).replace("# ", "### ", 1))
    return "\n".join(parts)
