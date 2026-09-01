"""Internal signal registry (feat/internal-bits §1) — project-defined BOOL/
REAL signals (project.settings["internal_bits"]) that replace free-text
"Tag" on virtual.input/virtual.output with a validated, unique, typed
registry entry. Kept dependency-free (no PySide6 import) so core/project.py
stays importable headlessly, same reasoning as core/grid.py.

An entry:
    {
      "name": "BLOKADA_ZS",
      "type": "BOOL",              # "BOOL" or "REAL"
      "retentive": False,          # survives a controller restart — but see
                                    # note below, Logic Studio never simulates
                                    # this itself
      "description": "Blokada załączenia od zabezpieczenia szyn",
      "label": "BLOK ZS",          # short HMI/schematic text, optional
      "category": "Blokady"        # grouping in the signal picker, optional
    }

Retentiveness note: Logic Studio only STORES and EXPORTS the `retentive`
flag. Whether/how a value actually survives a controller restart (where
it's persisted, how often, what happens on power loss) is EPW-OS's
responsibility entirely — see ARCHITECTURE.md "Przestrzenie nazw sygnałów".
Nothing in this module or the simulation engine makes retentive values
survive anything.
"""
import re

VALID_TYPES = ("BOOL", "REAL")

# Disallowed in a signal NAME (the identifier, not the description/label):
# whitespace, the path-ish separators / and \, quote characters, and Polish
# diacritics (both cases) — the identifier must be safe to embed verbatim in
# an M./MR./MW./MWR.-prefixed id and in file paths/JSON keys elsewhere.
_FORBIDDEN_CHARS_PATTERN = re.compile(r'[\s/\\\'"ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]')


def internal_bit_id(entry: dict) -> str:
    """The one, derived (never stored) identifier for a registry entry —
    §1.2. Changing `type` or `retentive` on an entry changes this; callers
    that persist an id (blocks referencing a signal by name+type+retentive
    combination, the exporter) must be kept in sync when an entry is
    edited — see ProjectSettingsDialog's registry editor (§7.3), which
    re-points every block using a changed entry."""
    name = entry.get("name", "")
    type_ = entry.get("type", "BOOL")
    retentive = bool(entry.get("retentive", False))

    if type_ == "REAL":
        prefix = "MWR" if retentive else "MW"
    else:
        prefix = "MR" if retentive else "M"

    return f"{prefix}.{name}"


def validate_internal_bit_name(name: str):
    """Format-only validation of a single name (§1.3) — doesn't check
    uniqueness, which needs the full registry. Returns an error message
    string, or None if the name is valid on its own."""
    if not name:
        return "Nazwa nie może być pusta."
    if _FORBIDDEN_CHARS_PATTERN.search(name):
        return ("Nazwa nie może zawierać spacji, znaków / \\ \" ' "
                "ani polskich znaków diakrytycznych.")
    return None


def validate_internal_bits_registry(entries: list) -> list:
    """Validates the WHOLE registry (§1.3) — uniqueness needs the full
    list, so this can't be done entry-by-entry. Returns a list of
    human-readable error message strings; empty means the registry is
    valid. Comparison for uniqueness is case-insensitive (BLOKADA_ZS and
    blokada_zs are the same conflict, not two signals)."""
    errors = []
    seen_lower = {}

    for entry in entries:
        name = entry.get("name", "")
        name_error = validate_internal_bit_name(name)
        if name_error:
            errors.append(f"{name!r}: {name_error}")
        else:
            lname = name.lower()
            if lname in seen_lower:
                errors.append(
                    f"Nazwa sygnału {name!r} koliduje z już istniejącą "
                    f"{seen_lower[lname]!r} (porównanie bez uwzględniania "
                    f"wielkości liter)."
                )
            else:
                seen_lower[lname] = name

        if entry.get("type") not in VALID_TYPES:
            errors.append(f"{name!r}: nieprawidłowy typ {entry.get('type')!r} (musi być BOOL albo REAL).")

    return errors
