from collections import defaultdict, deque

class GraphBuilder:
    def __init__(self, project):
        self.project = project

    def build_and_sort(self, errors: list) -> list:
        """
        Builds a directed dependency graph and returns a topologically sorted list of block UUIDs.
        If a cycle is detected, adds to errors and returns empty list.
        """
        # Map pin UUID to block UUID
        pin_to_block = {}
        for block in self.project.blocks:
            for pin in block.inputs + block.outputs:
                pin_to_block[pin.uuid] = block.uuid

        # Adjacency list: block_uuid -> list of dependent block_uuids
        graph = defaultdict(list)
        in_degree = {block.uuid: 0 for block in self.project.blocks}

        # Build edges based on Output -> Input connections
        for block in self.project.blocks:
            for out_pin in block.outputs:
                for conn_uuid in out_pin.connections:
                    if conn_uuid in pin_to_block:
                        target_block_uuid = pin_to_block[conn_uuid]
                        # Verify the connection is actually going to an input
                        # (Connection logic shouldn't allow Out-Out, but we verify here)
                        graph[block.uuid].append(target_block_uuid)
                        in_degree[target_block_uuid] += 1

        # Kahn's Algorithm for Topological Sorting
        queue = deque([u for u in in_degree if in_degree[u] == 0])
        execution_order = []

        while queue:
            u = queue.popleft()
            execution_order.append(u)
            for v in graph[u]:
                in_degree[v] -= 1
                if in_degree[v] == 0:
                    queue.append(v)

        if len(execution_order) != len(self.project.blocks):
            # Identify which blocks are in the loop
            missing = [block for block in self.project.blocks if block.uuid not in execution_order]
            names = [b.display_name for b in missing]
            errors.append(f"Execution Loop Detected. Combinational cyclic logic is not supported. Affected blocks: {', '.join(names)}")
            return []

        return execution_order
