"""feat/help-system §2.3/§7.4 — the block catalog is GENERATED from
BlockRegistry, so its own correctness is only as good as the metadata
every registered block type actually carries. This is the guardian:
every registered type has a non-empty description, and every pin it
produces (by name, from a fresh instance) has a non-empty description
too. A block added without filling these in fails here immediately,
per §2.3's own instruction, instead of shipping a catalog page with a
silent gap.
"""
import pytest

from logic_studio.blocks import register_builtin_blocks
from logic_studio.blocks.registry import BlockRegistry
from logic_studio.core import block_catalog

register_builtin_blocks()


def _all_type_ids():
    return sorted(BlockRegistry._type_id_map.keys())


@pytest.mark.parametrize("type_id", _all_type_ids())
def test_every_registered_block_has_a_non_empty_description(type_id):
    entry = block_catalog.describe_block_type(type_id)
    if entry is None:
        pytest.skip(f"{type_id} is not a cataloguable fixed type (e.g. a macro instance)")
    assert entry["description"].strip(), f"{type_id} has an empty description"


@pytest.mark.parametrize("type_id", _all_type_ids())
def test_every_pin_of_every_registered_block_has_a_non_empty_description(type_id):
    entry = block_catalog.describe_block_type(type_id)
    if entry is None:
        pytest.skip(f"{type_id} is not a cataloguable fixed type")
    for pin in entry["pins"]:
        assert pin["description"].strip(), (
            f"{type_id}: pin {pin['name']!r} has no description -- add it to "
            f"the block's PIN_DESCRIPTIONS (see logic_studio/blocks/base.py)"
        )


def test_generator_returns_a_complete_entry_for_every_registered_type_without_raising():
    """§7.4: the generator itself must never raise for any registered
    type, and must always come back with every section §2.1 lists."""
    catalog = block_catalog.generate_catalog()
    seen_type_ids = set()
    for category, entries in catalog.items():
        assert entries, f"category {category!r} listed with zero entries"
        for entry in entries:
            for key in ("type_id", "display_name", "category", "description", "pins", "properties", "aliases"):
                assert key in entry, f"{entry.get('type_id')}: missing catalog field {key!r}"
            seen_type_ids.add(entry["type_id"])

    # every registered, cataloguable type actually appears somewhere
    from logic_studio.blocks.macro_instance import MacroInstanceBlock
    for type_id in _all_type_ids():
        if BlockRegistry.get_block_class(type_id) is MacroInstanceBlock:
            continue
        assert type_id in seen_type_ids, f"{type_id} registered but missing from generate_catalog()"


def test_generator_groups_by_category_using_the_blocks_own_category():
    catalog = block_catalog.generate_catalog()
    for category, entries in catalog.items():
        for entry in entries:
            assert entry["category"] == category


def test_block_entry_markdown_renders_without_raising_for_every_type():
    for type_id in block_catalog.all_type_ids():
        entry = block_catalog.describe_block_type(type_id)
        md = block_catalog.block_entry_markdown(entry)
        assert entry["type_id"] in md
        assert entry["display_name"] in md

def test_export_catalog_markdown_includes_every_category_and_type():
    md = block_catalog.export_catalog_markdown()
    catalog = block_catalog.generate_catalog()
    for category, entries in catalog.items():
        assert category in md
        for entry in entries:
            assert entry["type_id"] in md

def test_unknown_type_id_returns_none_not_an_exception():
    assert block_catalog.describe_block_type("not.a.real.type") is None

def test_macro_instance_type_is_not_in_the_fixed_catalog():
    """Macro pins vary per PROJECT (per macro definition), not per fixed
    registered type -- macro_instance.py deliberately isn't decorated
    with @BlockRegistry.register (see its own module comment), so it
    must never appear here even if looked up directly by class."""
    from logic_studio.blocks.macro_instance import MacroInstanceBlock
    assert block_catalog.describe_block_type("macro.anything") is None
    for type_id in _all_type_ids():
        assert BlockRegistry.get_block_class(type_id) is not MacroInstanceBlock
