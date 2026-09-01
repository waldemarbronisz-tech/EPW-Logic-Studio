"""Loader for the fixed system-signal catalog (feat/internal-bits §3) —
system_signals_catalog.json. Dependency-free (no PySide6), loaded once and
cached at module import — the catalog is a static platform contract, never
edited at runtime.
"""
import json
import os

_CATALOG_PATH = os.path.join(os.path.dirname(__file__), "system_signals_catalog.json")

_catalog = None


def _load():
    global _catalog
    if _catalog is None:
        with open(_CATALOG_PATH, "r", encoding="utf-8") as f:
            _catalog = json.load(f)
    return _catalog


def get_catalog_version() -> str:
    return _load()["catalog_version"]


def get_categories() -> list:
    """List of {"id", "name", "signals"} dicts, in catalog order (§3.2's
    "Stan systemu" -> "Komunikacja" -> "Poziom dostępu" -> "Generatory
    czasu" — the order the signal picker's top-level sections use)."""
    return _load()["categories"]


def get_all_signals() -> list:
    """Every signal across every category, flattened."""
    return [s for cat in get_categories() for s in cat["signals"]]


def get_signal(signal_id: str):
    """A single signal's catalog entry (id/description/label/type/source/
    safety_relevant), or None if signal_id isn't in the catalog — the
    "spoza katalogu" case §3.4's migration and validator §4 both need to
    detect."""
    for signal in get_all_signals():
        if signal["id"] == signal_id:
            return signal
    return None
