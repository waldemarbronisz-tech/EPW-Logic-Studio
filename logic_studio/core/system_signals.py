"""Loader for the fixed system-signal catalog (feat/internal-bits §3) —
system_signals_catalog.json. Dependency-free (no PySide6), loaded once and
cached at module import — the catalog is a static platform contract, never
edited at runtime.

feat/multi-device-followups (closes ARCHITECTURE.md §9.2): the "Komunikacja"
category's per-device diagnostics (<dev>.ONLINE/<dev>.FAULT/
<dev>.SAFE_PATH_OK) are no longer hardcoded in the JSON file for ELA01/ADA01
only — they're generated in _device_signals() below, from the SAME
project.settings["ela_devices"]/["ada_devices"] DeviceModel already reads for
everything else device-related (feat/multi-device-io), so a project defining
ELA02/ADA02 gets their diagnostics too, without a second, independently-
maintained device list. Every public function below takes an OPTIONAL
`project` for exactly this reason — omitted (or None), it falls back to the
single-device ELA01/ADA01 default, reproducing the catalog's pre-multi-device
static content byte-for-byte (same ids/descriptions/labels/safety flags),
the same "no project handy yet" degradation pattern DeviceModel itself uses.
"""
import json
import os

_CATALOG_PATH = os.path.join(os.path.dirname(__file__), "system_signals_catalog.json")

_COMMS_CATEGORY_ID = "SYS.COMMS"

# (id suffix, description template, label, safety_relevant) — description
# templates take the device name itself (e.g. "ELA02"), never a fixed
# "ELA01" literal, so the generated text scales to however many devices a
# project defines. Text/flags below are exactly what the catalog's own
# static ELA01/ADA01 entries used to say — this is a mechanical change of
# WHERE they're produced, not a change of what they say for the default
# single-device case.
_ELA_DEVICE_SIGNAL_TEMPLATES = [
    ("ONLINE", "Moduł {dev} komunikuje się poprawnie", "ELA OK", False),
    ("FAULT", "Awaria modułu {dev}", "ELA AW", True),
]
_ADA_DEVICE_SIGNAL_TEMPLATES = [
    ("ONLINE", "Moduł {dev} komunikuje się poprawnie", "ADA OK", False),
    ("FAULT", "Awaria modułu {dev}", "ADA AW", True),
    ("SAFE_PATH_OK", "Sprzętowa droga wyłączenia sprawna", "DROGA OK", True),
]

_catalog = None


def _load():
    global _catalog
    if _catalog is None:
        with open(_CATALOG_PATH, "r", encoding="utf-8") as f:
            _catalog = json.load(f)
    return _catalog


def get_catalog_version() -> str:
    return _load()["catalog_version"]


def _device_signals(project) -> list:
    """Per-device "Komunikacja" signals for every ELA/ADA device `project`
    defines (project=None -> the single-device ELA01/ADA01 default)."""
    from logic_studio.core.device_model import DeviceModel

    signals = []
    for dev in DeviceModel.get_ela_devices(project):
        for suffix, desc_tpl, label, safety in _ELA_DEVICE_SIGNAL_TEMPLATES:
            signals.append({
                "id": f"{dev}.{suffix}", "description": desc_tpl.format(dev=dev),
                "label": label, "type": "BOOL", "source": "runtime", "safety_relevant": safety,
            })
    for dev in DeviceModel.get_ada_devices(project):
        for suffix, desc_tpl, label, safety in _ADA_DEVICE_SIGNAL_TEMPLATES:
            signals.append({
                "id": f"{dev}.{suffix}", "description": desc_tpl.format(dev=dev),
                "label": label, "type": "BOOL", "source": "runtime", "safety_relevant": safety,
            })
    return signals


def get_categories(project=None) -> list:
    """List of {"id", "name", "signals"} dicts, in catalog order (§3.2's
    "Stan systemu" -> "Komunikacja" -> "Poziom dostępu" -> "Generatory
    czasu" — the order the signal picker's top-level sections use). The
    "Komunikacja" category's signal list is extended with this project's own
    per-device diagnostics (_device_signals above); every other category —
    and "Komunikacja"'s own two non-device-specific signals — comes back
    exactly as the static catalog has it. Returns fresh category dicts and a
    fresh signals list each call; the static per-category signal dicts
    themselves are shared, never mutated, with the cached catalog."""
    categories = [dict(cat) for cat in _load()["categories"]]
    for cat in categories:
        if cat["id"] == _COMMS_CATEGORY_ID:
            cat["signals"] = list(cat["signals"]) + _device_signals(project)
    return categories


def get_all_signals(project=None) -> list:
    """Every signal across every category, flattened."""
    return [s for cat in get_categories(project) for s in cat["signals"]]


def get_signal(signal_id: str, project=None):
    """A single signal's catalog entry (id/description/label/type/source/
    safety_relevant), or None if signal_id isn't in the catalog (this
    project's own ELA/ADA device list included) — the "spoza katalogu" case
    §3.4's migration and validator §4 both need to detect."""
    for signal in get_all_signals(project):
        if signal["id"] == signal_id:
            return signal
    return None
