"""feat/macro-library-import-export — sharing a macro definition between
projects as a standalone `.epwmacro` file, so an engineer can build a
reusable block once and drop it into a different project (or hand it to a
colleague) instead of recreating it. Pure logic, no Qt — see
ui/panels/library.py for the export/import actions built on this, the
same core/*.py vs. ui/panels/*.py split as core/watch.py, core/crossref.py.

**File shape** (JSON):
    {"format": "EPW_MACRO_LIBRARY", "schema_version": 1,
     "root_def_id": "<the exported definition's ORIGINAL def_id — purely
                      informational, never reused as-is on import>",
     "definitions": {"<def_id>": {...a macro_definitions entry, exactly
                                  core/macros.py's own shape...}, ...}}

A single export bundles the requested definition PLUS every OTHER
definition it transitively depends on (a nested macro instance anywhere
inside its own — or a dependency's own — `"blocks"`) — importing just one
piece of a multi-macro hierarchy would otherwise land in the target
project with dangling `"macro.<def_id>"` references the moment the target
project tries to compile it.
"""
import copy
import json

from logic_studio.core import macros as macros_module

FORMAT = "EPW_MACRO_LIBRARY"
SCHEMA_VERSION = 1


def collect_dependencies(project, def_id: str) -> dict:
    """Returns `{def_id: definition}` for `def_id` itself PLUS every OTHER
    macro definition it transitively depends on. A dangling reference (a
    nested `"macro.<def_id>"` pointing at a definition that no longer
    exists in `project`) is silently skipped here — that's
    expand_project()'s job to catch as a real compile error, not this
    function's; it only ever collects what actually exists."""
    collected = {}
    _collect_recursive(project, def_id, collected)
    return collected


def _collect_recursive(project, def_id, collected):
    if def_id in collected:
        return
    definition = macros_module.get_definition(project, def_id)
    if definition is None:
        return
    collected[def_id] = definition
    for b_data in definition.get("blocks", []):
        nested_def_id = macros_module.macro_def_id(b_data.get("type_id"))
        if nested_def_id is not None:
            _collect_recursive(project, nested_def_id, collected)


def export_definition(project, def_id: str) -> dict:
    """Returns the portable bundle dict for `def_id` — itself plus every
    transitive dependency (collect_dependencies()) — ready for
    `json.dump()` to a `.epwmacro` file. Raises ValueError if `def_id`
    doesn't exist in `project` at all."""
    if macros_module.get_definition(project, def_id) is None:
        raise ValueError(f"Nieznana definicja makrobloku: {def_id}")
    return {
        "format": FORMAT,
        "schema_version": SCHEMA_VERSION,
        "root_def_id": def_id,
        "definitions": collect_dependencies(project, def_id),
    }


def save_to_file(project, def_id: str, path: str) -> None:
    bundle = export_definition(project, def_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(bundle, f, indent=2, ensure_ascii=False)


def load_from_file(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_bundle(bundle: dict) -> None:
    """Raises ValueError with an actionable message for anything that
    isn't a genuine `.epwmacro` bundle this build can read — the same
    fail-loudly-on-unrecognized-data discipline as
    Project.deserialize()'s own unknown-type_id/unknown-schema-version
    handling. A no-op (returns None) for a bundle this build can import."""
    if not isinstance(bundle, dict) or bundle.get("format") != FORMAT:
        raise ValueError("To nie jest plik biblioteki makrobloków EPW Logic Studio.")
    if bundle.get("schema_version", 0) > SCHEMA_VERSION:
        raise ValueError(
            "Plik zapisany nowszą wersją EPW Logic Studio, której ten program jeszcze nie obsługuje."
        )


def import_bundle(project, bundle: dict) -> str:
    """Imports every definition in `bundle` into `project`, each under a
    FRESH def_id — never reusing or colliding with one already in
    `project`, even if its content is identical to something already
    there (every import is independent; this app doesn't silently
    deduplicate elsewhere either — a duplicate address is a legitimate,
    common pattern too, see ARCHITECTURE.md §21). Every
    `"macro.<old_def_id>"` reference INSIDE any imported definition's own
    `"blocks"` is rewritten to that dependency's own NEW id, so nested
    dependencies still resolve correctly after import — a reference to
    something NOT included in this bundle (already dangling in the
    SOURCE project) is left exactly as it was, so it surfaces as the
    same "missing definition" compile error in the target project that
    it would have in the source.

    Returns the NEW def_id corresponding to the bundle's own
    `root_def_id` — the one the caller should offer to place an instance
    of right away. Raises ValueError (via validate_bundle()) for a
    malformed or unrecognized bundle; never partially imports one it's
    about to reject."""
    validate_bundle(bundle)

    old_definitions = bundle.get("definitions", {})
    id_map = {old_id: macros_module.new_def_id() for old_id in old_definitions}

    for old_id, definition in old_definitions.items():
        macros_module.set_definition(project, id_map[old_id], _rewrite_nested_references(definition, id_map))

    return id_map.get(bundle.get("root_def_id"))


def _rewrite_nested_references(definition: dict, id_map: dict) -> dict:
    """A COPY of `definition` with every `"macro.<old_def_id>"` type_id
    inside its own `"blocks"` rewritten to `"macro.<new_def_id>"` per
    `id_map`. The definition's OWN identity is never part of the dict
    itself (a def_id lives only as its dict KEY in
    project.settings["macro_definitions"]), so nothing about `definition`
    beyond its internal references ever needs changing here."""
    new_definition = copy.deepcopy(definition)
    for b_data in new_definition.get("blocks", []):
        old_nested_id = macros_module.macro_def_id(b_data.get("type_id"))
        if old_nested_id is not None and old_nested_id in id_map:
            b_data["type_id"] = macros_module.MACRO_TYPE_PREFIX + id_map[old_nested_id]
    return new_definition
