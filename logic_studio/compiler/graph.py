from collections import defaultdict


class GraphBuilder:
    """
    Builds the block dependency graph from pin connections and produces a
    deterministic execution order via Kahn's algorithm.

    Documentation-only blocks are excluded. Pure combinational feedback loops
    are rejected; a loop that passes through at least one stateful block
    (`is_stateful = True`, e.g. a timer or latch) is legal, because that block
    supplies the value it held at the end of the previous scan instead of a
    live same-scan dependency — that is broken into the graph by forcing the
    stateful block into the ready queue before its dependency is otherwise
    satisfied, and continuing Kahn's algorithm from there.

    Ties among simultaneously-ready blocks — and the choice of which stateful
    block breaks a given cycle — are resolved by (execution_priority, uuid),
    so recompiling the same project always yields the same execution order,
    regardless of the order blocks were added to it.
    """

    def __init__(self, project):
        self.project = project

    @staticmethod
    def _sort_key(block):
        return (block.execution_priority, block.uuid)

    def build_and_sort(self, errors: list) -> list:
        # feat/clipboard-and-align §4.2: a disabled block never enters
        # execution_order, exactly like a Documentation block — it's
        # simply absent from the graph, so it can neither be waited on
        # (its outputs are forced to a safe default value every scan
        # instead, see ExecutionEngine.step()) nor gate anything else
        # (an edge FROM it is never created below, so a downstream block
        # that only depended on a disabled one becomes ready immediately).
        executable_blocks = [
            b for b in self.project.blocks
            if b.category != "Dokumentacja" and b.enabled
        ]
        block_by_uuid = {b.uuid: b for b in executable_blocks}

        pin_to_block = {}
        for block in self.project.blocks:
            for pin in block.inputs + block.outputs:
                pin_to_block[pin.uuid] = block.uuid

        graph = defaultdict(list)
        in_degree = {uuid: 0 for uuid in block_by_uuid}

        for block in executable_blocks:
            for out_pin in block.outputs:
                for conn_uuid in out_pin.connections:
                    target_uuid = pin_to_block.get(conn_uuid)
                    if target_uuid in in_degree:
                        graph[block.uuid].append(target_uuid)
                        in_degree[target_uuid] += 1

        execution_order = []
        ready = sorted(
            (uuid for uuid, degree in in_degree.items() if degree == 0),
            key=lambda u: self._sort_key(block_by_uuid[u])
        )

        while ready:
            u = ready.pop(0)
            execution_order.append(u)
            newly_ready = []
            for v in graph[u]:
                in_degree[v] -= 1
                if in_degree[v] == 0:
                    newly_ready.append(v)
            if newly_ready:
                ready.extend(newly_ready)
                ready.sort(key=lambda u: self._sort_key(block_by_uuid[u]))

        if len(execution_order) == len(executable_blocks):
            return execution_order

        # Stuck: whatever is left forms one or more cycles. Repeatedly force the
        # lowest-keyed still-stuck stateful block into the graph (its feedback
        # edge is satisfied by its previous-scan output) and drain Kahn's
        # algorithm again from there, until nothing is left or no stateful block
        # remains to break the next cycle.
        missing = set(block_by_uuid) - set(execution_order)

        while missing:
            stateful_candidates = sorted(
                (u for u in missing if getattr(block_by_uuid[u], 'is_stateful', False)),
                key=lambda u: self._sort_key(block_by_uuid[u])
            )
            if not stateful_candidates:
                # feat/io-labels-and-ids §4.3: short_id, not display_name —
                # several untitled blocks of the same type would otherwise
                # name themselves identically in this list.
                names = [
                    block_by_uuid[u].short_id or block_by_uuid[u].display_name
                    for u in sorted(missing, key=lambda u: self._sort_key(block_by_uuid[u]))
                ]
                errors.append(f"Execution Loop Detected. Combinational cyclic logic is not supported. Affected blocks: {', '.join(names)}")
                return []

            ready = [stateful_candidates[0]]
            missing.discard(stateful_candidates[0])

            while ready:
                ready.sort(key=lambda u: self._sort_key(block_by_uuid[u]))
                u = ready.pop(0)
                execution_order.append(u)
                for v in graph[u]:
                    in_degree[v] -= 1
                    # Discard from `missing` at the moment v becomes ready (not when
                    # popped) so a v with several relaxed incoming edges within this
                    # pass can only ever be queued once.
                    if v in missing and in_degree[v] <= 0:
                        missing.discard(v)
                        ready.append(v)

        return execution_order
