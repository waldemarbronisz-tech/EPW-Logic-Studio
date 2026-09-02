import json
import hashlib
from datetime import datetime, timezone

from logic_studio import __version__
from logic_studio.core.device_model import DeviceModel
from logic_studio.core import system_signals

# Bump when the EPW_RUNTIME_LOGIC structure changes in a way a consumer
# (EPW-OS) needs to know about. See AUDIT_REPORT.md §2.2.
RUNTIME_SCHEMA_VERSION = 4

# The closed set of fields that make up the EPW_RUNTIME_LOGIC schema and are
# covered by the checksum. Compiler.compile() attaches a non-serializable
# "program" (CompiledProgram) key, and a "cycle_delayed_reads" list (feat/
# internal-bits §5/§8.1 — diagnostic data DERIVED from the fields already
# covered below, not independent data), on top of Exporter.export()'s
# return value for the ExecutionEngine's/EPW-OS's own use — those keys (and
# anything else outside this set) are deliberately ignored by both
# checksumming and verification, so handing verify_checksum() a compile()
# result instead of an export() result degrades to "checksum still valid"
# rather than a TypeError.
CHECKSUM_FIELDS = (
    "format", "schema_version", "source_version", "cycle_time_ms",
    "execution_order", "blocks", "generated_at", "generated_by",
    "project_name", "block_count", "contains_forced_io", "analog_points",
    "internal_bits", "system_catalog_version", "io_labels",
)


class Exporter:
    def __init__(self, project, execution_order):
        self.project = project
        self.execution_order = execution_order
        self.warnings = []

    def export(self) -> dict:
        """Generates the final EPW_RUNTIME_LOGIC structure for the Runtime Engine."""

        # We store the runtime graph structure, discarding UI position/color data
        runtime_blocks = {}
        forced_block_names = []

        for block in self.project.blocks:
            # "disabled" (feat/editor-modes-and-geometry §2.5): EPW-OS must
            # know an input was explicitly excluded from this block's own
            # logic, or it will evaluate the gate differently than the
            # simulation did (default-value semantics instead of exclusion —
            # see Pin.disabled's docstring). Already covered by CHECKSUM_
            # FIELDS: "blocks" (below) carries this whole per-pin dict, so no
            # separate entry is needed in that tuple.
            inputs = [{"pin_uuid": pin.uuid, "name": pin.name, "type": pin.data_type, "connections": pin.connections, "disabled": pin.disabled} for pin in block.inputs]
            outputs = [{"pin_uuid": pin.uuid, "name": pin.name, "type": pin.data_type, "connections": pin.connections} for pin in block.outputs]

            # A block's exported properties may carry compiler-resolved,
            # read-only fields on top of what the user configured (prefixed
            # "_", see the input.ai case below and ARCHITECTURE.md "Kontrakt
            # eksportu runtime"). Never mutate block.properties itself — this
            # is a copy that only ever exists in the exported dict.
            properties = dict(block.properties)

            if block.type_id == "input.ai":
                # A consumer reading this block's entry in isolation (no
                # Project, just this JSON file — see AUDIT_REPORT.md §1.2)
                # must still be able to reconstruct its quality-check range
                # and unit, exactly like the compiler resolves it into the
                # in-memory CompiledProgram via AnalogInputBlock.set_range().
                point = DeviceModel.get_analog_point(self.project, properties.get("Address", ""))
                if point:
                    properties["_resolved_range_min"] = point.get("min")
                    properties["_resolved_range_max"] = point.get("max")
                    properties["_resolved_unit"] = point.get("unit", "")

            runtime_blocks[block.uuid] = {
                "type_id": block.type_id,
                # feat/io-labels-and-ids §4.4: short_id rides along so
                # EPW-OS can use it in its own diagnostic messages instead
                # of this same UUID nobody can read out loud.
                "short_id": block.short_id,
                "category": block.category,
                "inputs": inputs,
                "outputs": outputs,
                "properties": properties
            }

            force_state = block.simulation_state.get("force_state")
            if force_state and force_state != "NO FORCE":
                forced_block_names.append(block.short_id or block.display_name)

        contains_forced_io = len(forced_block_names) > 0
        if contains_forced_io:
            # Surfaced both in the exported metadata (for EPW-OS) and as a compiler
            # warning (for the engineer exporting), see AUDIT_REPORT.md §5.1.
            self.warnings.append(
                "Eksport zawiera aktywne wymuszenia wejść: " + ", ".join(forced_block_names)
            )

        # Full copy of every analog point the project declares — not just the
        # ones a block currently references. A point may be defined for the
        # future, or used only by an HMI layer with no logic block behind it
        # at all, so EPW-OS needs the complete list (AUDIT_REPORT.md §1.1).
        analog_points = [dict(p) for p in self.project.settings.get("analog_points", [])]

        # Full copy of the internal-signal registry (feat/internal-bits
        # §8.1) — same reasoning as analog_points above: a consumer reading
        # this file in isolation, with no live Project, must be able to
        # reconstruct every signal's type/retentive flag (and therefore its
        # M./MR./MW./MWR.<name> id, via core.internal_bits.internal_bit_id())
        # for every block that references one.
        internal_bits = [dict(e) for e in self.project.settings.get("internal_bits", [])]

        # feat/io-labels-and-ids §1.5: full copy of the address -> label
        # registry — EPW-OS uses these as event-register/Historian texts.
        # This is the canonical source of event descriptions; without it
        # EPW-OS would need its own independent copy that immediately
        # drifts out of sync with the logic project (see ARCHITECTURE.md
        # "Etykiety adresów I/O").
        io_labels = dict(DeviceModel.get_labelled_addresses(self.project))

        payload = {
            "format": "EPW_RUNTIME_LOGIC",
            "schema_version": RUNTIME_SCHEMA_VERSION,
            "source_version": self.project.settings.get("version", "1.0"),
            "cycle_time_ms": self.project.settings.get("cycle_time_ms", 100),
            "execution_order": self.execution_order,
            "blocks": runtime_blocks,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "generated_by": f"EPW Logic Studio {__version__}",
            "project_name": self.project.settings.get("name", "New Project"),
            "block_count": len(self.execution_order),
            "contains_forced_io": contains_forced_io,
            "analog_points": analog_points,
            "internal_bits": internal_bits,
            # §8.1: the system-signal catalog version this logic was
            # compiled against — EPW-OS can refuse to run logic compiled
            # on a catalog newer than it understands.
            "system_catalog_version": system_signals.get_catalog_version(),
            "io_labels": io_labels,
        }

        # Checksum covers the canonical serialization of everything ABOVE, computed
        # before the checksum field itself is added. EPW-OS re-derives this before
        # trusting a runtime file (see verify_checksum below).
        payload["checksum"] = self._compute_checksum(payload)
        return payload

    @staticmethod
    def _compute_checksum(payload: dict) -> str:
        subset = {k: payload[k] for k in CHECKSUM_FIELDS if k in payload}
        canonical = json.dumps(subset, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
        return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def verify_checksum(data: dict) -> bool:
    """Recomputes the SHA-256 checksum over CHECKSUM_FIELDS only and compares
    it against the "checksum" field. Returns False (never raises) if the
    checksum is missing, if any covered field was altered after export, or if
    the payload can't be serialized at all — a dict that also carries
    unrelated, non-serializable keys (e.g. a compile() result's "program")
    is handled the same as a clean export() result, since those keys are
    outside CHECKSUM_FIELDS and are simply ignored."""
    if "checksum" not in data:
        return False

    try:
        subset = {k: data[k] for k in CHECKSUM_FIELDS if k in data}
        canonical = json.dumps(subset, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    except TypeError:
        return False

    expected = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
    return expected == data["checksum"]
