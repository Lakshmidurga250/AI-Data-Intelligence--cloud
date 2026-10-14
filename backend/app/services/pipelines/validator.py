"""Graph validation and cycle detection algorithms for visual ETL pipelines."""

from collections import defaultdict, deque
from typing import Dict, List, Set, Tuple

from app.schemas.pipeline import PipelineGraph, PipelineValidationResult


def validate_pipeline_dag(graph: PipelineGraph) -> PipelineValidationResult:
    """Validate pipeline structure, check node constraints, and verify DAG acyclicity."""
    errors: List[str] = []
    warnings: List[str] = []
    execution_order: List[str] = []

    if not graph.nodes:
        return PipelineValidationResult(
            is_valid=False,
            errors=["Pipeline graph contains no nodes. Add at least a Source and a Sink node."],
            warnings=[],
            execution_order=[],
        )

    node_ids: Set[str] = {n.id for n in graph.nodes}
    node_types: Dict[str, str] = {n.id: n.type for n in graph.nodes}
    node_configs: Dict[str, dict] = {n.id: n.config for n in graph.nodes}

    # Verify unique node IDs
    if len(node_ids) != len(graph.nodes):
        errors.append("Duplicate node IDs detected in pipeline definition.")

    # 1. Edge reference validation
    adj: Dict[str, List[str]] = defaultdict(list)
    in_degree: Dict[str, int] = {nid: 0 for nid in node_ids}
    out_degree: Dict[str, int] = {nid: 0 for nid in node_ids}

    for edge in graph.edges:
        if edge.source not in node_ids:
            errors.append(f"Edge '{edge.id}' references non-existent source node '{edge.source}'.")
            continue
        if edge.target not in node_ids:
            errors.append(f"Edge '{edge.id}' references non-existent target node '{edge.target}'.")
            continue
        if edge.source == edge.target:
            errors.append(f"Edge '{edge.id}' is a self-loop on node '{edge.source}'.")
            continue

        adj[edge.source].append(edge.target)
        in_degree[edge.target] += 1
        out_degree[edge.source] += 1

    # 2. Check for required Source and Sink nodes
    source_nodes = [nid for nid, ntype in node_types.items() if ntype == "source"]
    sink_nodes = [nid for nid, ntype in node_types.items() if ntype == "sink"]

    if not source_nodes:
        errors.append("Pipeline must contain at least one 'source' node.")
    if not sink_nodes:
        errors.append("Pipeline must contain at least one 'sink' node.")

    # 3. Individual node connectivity & configuration constraints
    for n in graph.nodes:
        cfg = n.config or {}
        if n.type == "source":
            if in_degree[n.id] > 0:
                warnings.append(f"Source node '{n.label or n.id}' has incoming edges, which are ignored.")
            if not cfg.get("dataset_id"):
                errors.append(f"Source node '{n.label or n.id}' is missing required 'dataset_id'.")
        elif n.type == "sink":
            if in_degree[n.id] == 0:
                errors.append(f"Sink node '{n.label or n.id}' is disconnected (has no upstream input).")
            if out_degree[n.id] > 0:
                warnings.append(f"Sink node '{n.label or n.id}' has outgoing edges, which is not standard.")
            if not cfg.get("output_name"):
                warnings.append(f"Sink node '{n.label or n.id}' has no custom 'output_name' (default will be used).")
        elif n.type == "join":
            if in_degree[n.id] != 2:
                errors.append(
                    f"Join node '{n.label or n.id}' requires exactly 2 incoming data inputs, but received {in_degree[n.id]}."
                )
        else:  # transform, filter, aggregate
            if in_degree[n.id] == 0:
                errors.append(f"Processing node '{n.label or n.id}' ({n.type}) is disconnected with no input data.")

    # 4. Cycle Detection using Kahn's Algorithm
    queue = deque([nid for nid in node_ids if in_degree[nid] == 0])
    in_degree_copy = in_degree.copy()

    while queue:
        curr = queue.popleft()
        execution_order.append(curr)

        for neighbor in adj[curr]:
            in_degree_copy[neighbor] -= 1
            if in_degree_copy[neighbor] == 0:
                queue.append(neighbor)

    if len(execution_order) < len(node_ids):
        unvisited = [nid for nid in node_ids if nid not in execution_order]
        errors.append(
            f"Cyclic dependency detected! Circular reference involves nodes: {', '.join(unvisited)}. Visual ETL graphs must be strictly acyclic."
        )
        is_valid = False
    else:
        is_valid = len(errors) == 0

    return PipelineValidationResult(
        is_valid=is_valid,
        errors=errors,
        warnings=warnings,
        execution_order=execution_order if is_valid else [],
    )
