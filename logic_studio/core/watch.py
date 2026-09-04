"""Signal watch list (feat/signal-watch) — project.settings["watched_signals"],
a list of {"kind", "signal_id"} entries an engineer pins for continuous
monitoring during simulation, independent of canvas selection. Pure logic,
no Qt dependency — see ui/panels/watch.py for the panel built on top of this,
the same split as core/crossref.py vs. ui/panels/signals.py.

`kind` reuses core/crossref.py's KIND_* constants for consistency with the
Signals panel's own classification of the same four signal namespaces
(ARCHITECTURE.md §10/§14) — but a watch entry's `signal_id` is always the
same identifier an engineer would type/pick for that kind elsewhere in the
app: a physical/analog address for KIND_PHYSICAL_DI/_DO/KIND_ANALOG_IN/_OUT,
the bare internal-signal NAME (not the derived M./MR./MW./MWR.<name> id) for
KIND_INTERNAL_BIT/_REG — exactly what SignalPickerDialog returns and what a
block's own "Bit" property stores — and the catalog id for KIND_SYSTEM.
Keeping the bare name (not the derived id) for internal signals means a
watch survives a retentive-flag or type change to that registry entry; only
a rename or deletion invalidates it, exactly like a block's own "Bit"
property would be affected by the same edit.
"""
from logic_studio.core.crossref import (
    KIND_PHYSICAL_DI, KIND_PHYSICAL_DO, KIND_ANALOG_IN, KIND_ANALOG_OUT,
    KIND_INTERNAL_BIT, KIND_INTERNAL_REG, KIND_SYSTEM,
)

_SETTINGS_KEY = "watched_signals"


def get_watches(project) -> list:
    """A copy of the watch list, in stored order — callers must go through
    add_watch()/remove_watch() to write, the same discipline as
    io_labels/analog_points/internal_bits elsewhere in DeviceModel."""
    return [dict(w) for w in project.settings.get(_SETTINGS_KEY, [])]


def is_watched(project, kind: str, signal_id: str) -> bool:
    return any(
        w.get("kind") == kind and w.get("signal_id") == signal_id
        for w in project.settings.get(_SETTINGS_KEY, [])
    )


def add_watch(project, kind: str, signal_id: str) -> bool:
    """Appends (kind, signal_id) if not already watched. Returns True if it
    was actually added (False for a no-op: empty signal_id, or an existing
    duplicate) — so a caller can decide whether a push_state()/set_dirty()
    is warranted."""
    if not signal_id or is_watched(project, kind, signal_id):
        return False
    project.settings.setdefault(_SETTINGS_KEY, []).append(
        {"kind": kind, "signal_id": signal_id}
    )
    return True


def remove_watch(project, kind: str, signal_id: str) -> bool:
    """Returns True if an entry was actually removed."""
    watches = project.settings.get(_SETTINGS_KEY, [])
    kept = [w for w in watches if not (w.get("kind") == kind and w.get("signal_id") == signal_id)]
    if len(kept) == len(watches):
        return False
    project.settings[_SETTINGS_KEY] = kept
    return True


def describe_watch(project, kind: str, signal_id: str) -> str:
    """Human-readable description for a watch entry — the same text an
    engineer would see picking this signal elsewhere in the app: an I/O
    label for a physical/analog address, an internal signal's own
    description, or the system catalog's description. "" if unresolvable
    (e.g. the address/name/signal no longer exists)."""
    from logic_studio.core.device_model import DeviceModel

    if kind in (KIND_PHYSICAL_DI, KIND_PHYSICAL_DO):
        return DeviceModel.get_io_label(project, signal_id)
    if kind in (KIND_ANALOG_IN, KIND_ANALOG_OUT):
        label = DeviceModel.get_io_label(project, signal_id)
        if label:
            return label
        point = DeviceModel.get_analog_point(project, signal_id)
        return point.get("name", "") if point else ""
    if kind in (KIND_INTERNAL_BIT, KIND_INTERNAL_REG):
        entry = DeviceModel.get_internal_bit(project, signal_id)
        return entry.get("description", "") if entry else ""
    if kind == KIND_SYSTEM:
        from logic_studio.core import system_signals
        entry = system_signals.get_signal(signal_id, project)
        return entry.get("description", "") if entry else ""
    return ""


def is_boolean_kind(project, kind: str, signal_id: str) -> bool:
    """Whether this watch entry's value is boolean-shaped — physical DI/DO
    always are; analog points never are; internal/system signals depend on
    their own declared type. Used by the panel to decide between a 0/1 step
    trace and a scaled analog trace."""
    if kind in (KIND_PHYSICAL_DI, KIND_PHYSICAL_DO):
        return True
    if kind in (KIND_ANALOG_IN, KIND_ANALOG_OUT):
        return False
    if kind in (KIND_INTERNAL_BIT, KIND_INTERNAL_REG):
        from logic_studio.core.device_model import DeviceModel
        entry = DeviceModel.get_internal_bit(project, signal_id)
        return not entry or entry.get("type") != "REAL"
    if kind == KIND_SYSTEM:
        from logic_studio.core import system_signals
        entry = system_signals.get_signal(signal_id, project)
        return not entry or entry.get("type") != "REAL"
    return True


def read_value(project, io_provider, kind: str, signal_id: str, now_ms: int = 0):
    """Resolves a watch entry's CURRENT live value via the right
    IOProvider method for its kind — the one place that knows how to map a
    watch entry back to an actual read, so ui/panels/watch.py never has to
    branch on `kind` itself. None if the entry no longer resolves to
    anything real (e.g. an internal signal deleted from the registry since
    being watched) — the panel shows that as a dash, never a crash."""
    if kind == KIND_PHYSICAL_DI:
        return io_provider.read_digital_input(signal_id)
    if kind == KIND_PHYSICAL_DO:
        return io_provider.read_digital_output(signal_id)
    if kind == KIND_ANALOG_IN:
        return io_provider.read_analog_input(signal_id)
    if kind == KIND_ANALOG_OUT:
        return io_provider.read_analog_output(signal_id)
    if kind in (KIND_INTERNAL_BIT, KIND_INTERNAL_REG):
        from logic_studio.core.device_model import DeviceModel
        from logic_studio.core.internal_bits import internal_bit_id

        entry = DeviceModel.get_internal_bit(project, signal_id)
        if entry is None:
            return None
        default = 0.0 if entry.get("type") == "REAL" else False
        return io_provider.read_internal(internal_bit_id(entry), default)
    if kind == KIND_SYSTEM:
        return io_provider.read_system_signal(signal_id, now_ms)
    return None
