from collections import defaultdict, deque

class GraphBuilder:
    def __init__(self, project):
        self.project = project

    def build_and_sort(self, errors: list) -> list:
        # Map pin UUID to block UUID
        pin_to_block = {}
        for block in self.project.blocks:
            for pin in block.inputs + block.outputs:
                pin_to_block[pin.uuid] = block.uuid

        graph = defaultdict(list)
        executable_blocks = [b for b in self.project.blocks if b.category != "Dokumentacja"]
        in_degree = {block.uuid: 0 for block in executable_blocks}

        # Build edges based on Output -> Input connections
        for block in executable_blocks:
            for out_pin in block.outputs:
                for conn_uuid in out_pin.connections:
                    if conn_uuid in pin_to_block:
                        target_block_uuid = pin_to_block[conn_uuid]
                        graph[block.uuid].append(target_block_uuid)
                        in_degree[target_block_uuid] += 1

        queue = deque([u for u in in_degree if in_degree[u] == 0])
        execution_order = []

        while queue:
            u = queue.popleft()
            execution_order.append(u)
            for v in graph[u]:
                in_degree[v] -= 1
                if in_degree[v] == 0:
                    queue.append(v)

        if len(execution_order) != len(executable_blocks):
            # We have a cycle. Let's try to break it at stateful blocks.
            # Only drop edges that close loops into stateful blocks.
            missing = [b.uuid for b in executable_blocks if b.uuid not in execution_order]
            stateful_in_cycle = [b.uuid for b in executable_blocks if b.uuid in missing and getattr(b, 'is_stateful', False)]

            if not stateful_in_cycle:
                names = [b.display_name for b in executable_blocks if b.uuid in missing]
                errors.append(f"Execution Loop Detected. Combinational cyclic logic is not supported. Affected blocks: {', '.join(names)}")
                return []

            # If there are stateful blocks in the cycle, we can safely ignore the backwards edges pointing into them.
            # To do this correctly, we could do a DFS to find back-edges, but an easier way for FBD is:
            # Rebuild graph ignoring edges into stateful blocks IF the graph still has a cycle.
            # For simplicity, we just rebuild ignoring ALL edges into stateful blocks.
            # Wait, no, we just did that and it broke forward evaluation.

            # Let's just find ONE stateful block in the loop, break ONE incoming edge, and retry.
            # Actually, standard PLC cycle breaks cycles at explicitly marked Feedback variables or stateful memories.
            # Let's just strip incoming edges to stateful blocks ONLY if they are part of the `missing` loop nodes.
            # In fact, we can just do Kahn's algorithm again, but when we get stuck, we forcefully enqueue a stateful block from `missing`.

            while missing:
                # Find a stateful block in missing
                st_block_uuid = next((u for u in missing if getattr(next(b for b in executable_blocks if b.uuid == u), 'is_stateful', False)), None)
                if not st_block_uuid:
                    names = [b.display_name for b in executable_blocks if b.uuid in missing]
                    errors.append(f"Execution Loop Detected. Combinational cyclic logic is not supported. Affected blocks: {', '.join(names)}")
                    return []

                # Break cycle by pretending the stateful block's remaining dependencies are satisfied
                queue.append(st_block_uuid)
                missing.remove(st_block_uuid)

                while queue:
                    u = queue.popleft()
                    if u not in execution_order:
                        execution_order.append(u)
                        if u in missing:
                            missing.remove(u)
                        for v in graph[u]:
                            in_degree[v] -= 1
                            if in_degree[v] <= 0 and v in missing:
                                queue.append(v)

        return execution_order
