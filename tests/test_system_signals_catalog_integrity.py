"""audit/systematic-sweep §5.1 — the fixed system-signal catalog
(core/system_signals_catalog.json) had no dedicated integrity test at
all before this audit, despite being a "closed platform contract"
(its own _comment) that EPW-OS depends on. Checks every entry has the
complete field set, every id is unique, type/source come from the
actual allowed sets this codebase's own loader (core/system_signals.py)
understands, and the catalog's own format/schema_version are the ones
that loader expects.
"""
import json
from pathlib import Path

CATALOG_PATH = Path("logic_studio/core/system_signals_catalog.json")
REQUIRED_FIELDS = {"id", "description", "label", "type", "source", "safety_relevant"}
# core/system_signals.py's own _device_signals() and every static entry
# in the catalog today only ever use these values -- an entry using
# anything else would silently not be handled the way the rest of the
# codebase (Exporter, AnalogInputBlock-style REAL/BOOL branching,
# compiler/validator.py's own source=="runtime"/"logic" branching for
# system.signal_out) expects. "logic" (feat/sswin-signals, catalog
# 1.1.0) is the first source writable BY logic instead of only ever
# produced by a device/runtime -- see ARCHITECTURE.md §33.5.
VALID_TYPES = {"BOOL", "REAL"}
VALID_SOURCES = {"runtime", "logic"}


def _load_catalog():
    with open(CATALOG_PATH, encoding="utf-8") as f:
        return json.load(f)


def _all_signals(catalog):
    for category in catalog["categories"]:
        yield from category["signals"]


def test_catalog_format_and_schema_version_match_the_loader():
    from logic_studio.core import system_signals
    catalog = _load_catalog()
    assert catalog["format"] == "EPW_SIGNAL_CATALOG"
    assert catalog["schema_version"] == 1
    assert catalog["catalog_version"] == system_signals.get_catalog_version()

def test_every_signal_has_the_complete_field_set():
    catalog = _load_catalog()
    for sig in _all_signals(catalog):
        missing = REQUIRED_FIELDS - set(sig.keys())
        assert not missing, f"{sig.get('id', '<no id>')}: missing fields {missing}"

def test_every_signal_id_is_globally_unique():
    catalog = _load_catalog()
    ids = [sig["id"] for sig in _all_signals(catalog)]
    dupes = {x for x in ids if ids.count(x) > 1}
    assert not dupes, f"duplicate signal ids: {dupes}"

def test_every_signal_type_is_in_the_allowed_set():
    catalog = _load_catalog()
    for sig in _all_signals(catalog):
        assert sig["type"] in VALID_TYPES, f"{sig['id']}: unexpected type {sig['type']!r}"

def test_every_signal_source_is_in_the_allowed_set():
    catalog = _load_catalog()
    for sig in _all_signals(catalog):
        assert sig["source"] in VALID_SOURCES, f"{sig['id']}: unexpected source {sig['source']!r}"

def test_every_signal_safety_relevant_is_a_real_boolean():
    """Not "truthy" -- a JSON 1/0 or "true" string would pass an
    isinstance(x, bool) check's INTENT but not the check itself if this
    were written loosely; keeping it strict catches a hand-edited catalog
    entry that typo'd true/false as a string."""
    catalog = _load_catalog()
    for sig in _all_signals(catalog):
        assert isinstance(sig["safety_relevant"], bool), \
            f"{sig['id']}: safety_relevant is {sig['safety_relevant']!r}, not a real bool"

def test_every_signal_has_a_non_empty_description():
    catalog = _load_catalog()
    for sig in _all_signals(catalog):
        assert sig["description"].strip(), f"{sig['id']}: empty description"

def test_every_signal_id_starts_with_its_own_category_prefix():
    """Every category id is "<PREFIX>.<SUBCATEGORY>" ("SYS.STATE",
    "SSWIN.ALARM", ...) and every signal inside it starts with that same
    "<PREFIX>." -- true of both namespaces the catalog has today (SYS,
    and SSWIN since feat/sswin-signals/catalog 1.1.0) and, by
    construction, of any future one: the invariant is "shares its own
    category's namespace prefix", never a single hardcoded literal."""
    catalog = _load_catalog()
    for category in catalog["categories"]:
        prefix = category["id"].split(".")[0] + "."
        for sig in category["signals"]:
            assert sig["id"].startswith(prefix), \
                f"{sig['id']}: does not start with '{prefix}' (its own category {category['id']!r}'s namespace)"
