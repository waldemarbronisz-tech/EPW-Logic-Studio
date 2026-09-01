import json
import hashlib
from datetime import datetime, timezone

from logic_studio import __version__


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
            inputs = [{"pin_uuid": pin.uuid, "name": pin.name, "type": pin.data_type, "connections": pin.connections} for pin in block.inputs]
            outputs = [{"pin_uuid": pin.uuid, "name": pin.name, "type": pin.data_type, "connections": pin.connections} for pin in block.outputs]

            runtime_blocks[block.uuid] = {
                "type_id": block.type_id,
                "category": block.category,
                "inputs": inputs,
                "outputs": outputs,
                "properties": block.properties
            }

            force_state = block.simulation_state.get("force_state")
            if force_state and force_state != "NO FORCE":
                forced_block_names.append(block.display_name)

        contains_forced_io = len(forced_block_names) > 0
        if contains_forced_io:
            # Surfaced both in the exported metadata (for EPW-OS) and as a compiler
            # warning (for the engineer exporting), see AUDIT_REPORT.md §5.1.
            self.warnings.append(
                "Eksport zawiera aktywne wymuszenia wejść: " + ", ".join(forced_block_names)
            )

        payload = {
            "format": "EPW_RUNTIME_LOGIC",
            "schema_version": 1,
            "source_version": self.project.settings.get("version", "1.0"),
            "cycle_time_ms": self.project.settings.get("cycle_time_ms", 100),
            "execution_order": self.execution_order,
            "blocks": runtime_blocks,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "generated_by": f"EPW Logic Studio {__version__}",
            "project_name": self.project.settings.get("name", "New Project"),
            "block_count": len(self.execution_order),
            "contains_forced_io": contains_forced_io,
        }

        # Checksum covers the canonical serialization of everything ABOVE, computed
        # before the checksum field itself is added. EPW-OS re-derives this before
        # trusting a runtime file (see verify_checksum below).
        payload["checksum"] = self._compute_checksum(payload)
        return payload

    @staticmethod
    def _compute_checksum(payload: dict) -> str:
        canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
        return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def verify_checksum(data: dict) -> bool:
    """Recomputes the SHA-256 checksum of an EPW_RUNTIME_LOGIC payload and compares
    it against the "checksum" field. Returns False if the field is missing, or if
    anything in the payload was altered after export."""
    if "checksum" not in data:
        return False

    payload = {k: v for k, v in data.items() if k != "checksum"}
    canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    expected = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
    return expected == data["checksum"]
