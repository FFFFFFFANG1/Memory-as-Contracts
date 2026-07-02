"""Compare MAC exported constraint graphs vs bundled CCTU contract graphs."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]

import sys

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.MAC.cctu.bridge import MAC_CCTU_DATA_DIR
from bench.MAC.scripts.run_paths import mac_graph_dir

GRAPHS_PATH = MAC_CCTU_DATA_DIR / "mac-cctu-contract_graphs.json"
DEFAULT_COMPARE_OUTPUT = (
    REPO_ROOT / "bench" / "MAC" / "cctu" / "results" / "mac_vs_cctu_graph_compare.json"
)


def normalize_text(text: str) -> str:
    lowered = re.sub(r"\s+", " ", text.strip().lower())
    lowered = re.sub(r"[^\w\s]", "", lowered)
    return lowered


def best_similarity(left: str, right: str) -> float:
    a = normalize_text(left)
    b = normalize_text(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a in b or b in a:
        return 0.92
    return SequenceMatcher(None, a, b).ratio()


@dataclass
class GraphSide:
    name: str
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    meta: dict[str, Any]


def load_cctu_graph(task_uid: str) -> GraphSide:
    payload = json.loads(GRAPHS_PATH.read_text(encoding="utf-8"))
    graph_entry = next(item for item in payload["graphs"] if item["task_uid"] == task_uid)
    contract_graph = graph_entry["contract_graph"]
    nodes = [
        {
            "id": node["id"],
            "text": node.get("surface_text") or "",
            "modality": node.get("modality"),
            "scope": node.get("scope") or {},
            "lifecycle": node.get("lifecycle") or {},
        }
        for node in contract_graph.get("nodes", [])
    ]
    edges = [
        {
            "from": edge.get("from") or edge.get("source"),
            "to": edge.get("to") or edge.get("target"),
            "relation": edge.get("relation") or edge.get("type") or edge.get("edge_type"),
            "raw": edge,
        }
        for edge in contract_graph.get("edges", [])
    ]
    generated = graph_entry.get("generated_constraints") or []
    except_pairs = [
        (item.get("local_id"), item.get("except_by"))
        for item in generated
        if item.get("except_by")
    ]
    return GraphSide(
        name="cctu_bundled",
        nodes=nodes,
        edges=edges,
        meta={
            "generated_constraint_count": len(generated),
            "constraint_sequence_count": graph_entry.get("constraint_sequence_count"),
            "resolved_active_node_ids": (graph_entry.get("validation") or {}).get("resolved_active_node_ids", []),
            "expected_active_node_ids": (graph_entry.get("oracle") or {}).get("expected_active_node_ids", []),
            "except_by_pairs": except_pairs,
            "anchor_nodes": [item.get("local_id") for item in generated if item.get("is_anchor")],
        },
    )


def load_mac_graph(path: Path) -> GraphSide:
    payload = json.loads(path.read_text(encoding="utf-8"))
    contract_graph = payload.get("contract_graph") or {}
    nodes = contract_graph.get("nodes") or []
    edges = contract_graph.get("edges") or []
    return GraphSide(
        name="mac_export",
        nodes=nodes,
        edges=edges,
        meta=payload.get("metadata") or {},
    )


def resolve_mac_graph_path(
    *,
    bench: str,
    memory_system: str,
    run_id: str,
    task_uid: str,
    mac_graph_root: Path | None = None,
) -> Path:
    root = mac_graph_root or mac_graph_dir(bench)
    safe_task = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in task_uid)
    return root / f"{memory_system}_{bench}_{run_id}__{safe_task}.json"


def match_nodes(left: GraphSide, right: GraphSide, threshold: float = 0.72) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []
    used_right: set[str] = set()
    for left_node in left.nodes:
        best = None
        best_score = 0.0
        for right_node in right.nodes:
            if right_node["id"] in used_right:
                continue
            score = best_similarity(left_node.get("text", ""), right_node.get("text", ""))
            if score > best_score:
                best_score = score
                best = right_node
        if best is not None and best_score >= threshold:
            used_right.add(best["id"])
            matches.append(
                {
                    "left_id": left_node["id"],
                    "right_id": best["id"],
                    "score": round(best_score, 3),
                    "left_text": left_node.get("text", ""),
                    "right_text": best.get("text", ""),
                }
            )
    unmatched_left = [node for node in left.nodes if node["id"] not in {m["left_id"] for m in matches}]
    unmatched_right = [node for node in right.nodes if node["id"] not in used_right]
    return {
        "matched_count": len(matches),
        "left_count": len(left.nodes),
        "right_count": len(right.nodes),
        "left_only_count": len(unmatched_left),
        "right_only_count": len(unmatched_right),
        "jaccard_estimated": round(
            len(matches) / max(len(left.nodes) + len(right.nodes) - len(matches), 1),
            3,
        ),
        "matches": matches[:20],
        "left_only_samples": [{"id": n["id"], "text": n.get("text", "")} for n in unmatched_left[:10]],
        "right_only_samples": [{"id": n["id"], "text": n.get("text", "")} for n in unmatched_right[:10]],
    }


def summarize_side(side: GraphSide) -> dict[str, Any]:
    scope_levels = Counter(
        (node.get("scope") or {}).get("level") for node in side.nodes if isinstance(node.get("scope"), dict)
    )
    edge_relations = Counter(edge.get("relation") for edge in side.edges)
    return {
        "name": side.name,
        "node_count": len(side.nodes),
        "edge_count": len(side.edges),
        "scope_levels": dict(scope_levels),
        "edge_relations": dict(edge_relations),
        "meta": side.meta,
    }


def compare_task(
    task_uid: str,
    *,
    mac_graph_path: Path,
) -> dict[str, Any]:
    cctu = load_cctu_graph(task_uid)
    mac = load_mac_graph(mac_graph_path)
    mac_to_cctu = match_nodes(mac, cctu)
    cctu_to_mac = match_nodes(cctu, mac)
    return {
        "task_uid": task_uid,
        "mac_graph_path": str(mac_graph_path),
        "cctu": summarize_side(cctu),
        "mac": summarize_side(mac),
        "text_overlap_mac_to_cctu": mac_to_cctu,
        "text_overlap_cctu_to_mac": cctu_to_mac,
        "structural_differences": {
            "node_count_ratio_mac_over_cctu": round(len(mac.nodes) / max(len(cctu.nodes), 1), 2),
            "edge_count_delta": len(mac.edges) - len(cctu.edges),
            "mac_edge_relations": dict(Counter(edge.get("relation") for edge in mac.edges)),
            "cctu_resolved_active_nodes": cctu.meta.get("resolved_active_node_ids"),
            "mac_included_in_prompt_count": mac.meta.get("included_contract_count"),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bench", default="cctu")
    parser.add_argument("--memory-system", default="mac")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--task-uids", default="mac-cctu-t-00000,mac-cctu-t-00001")
    parser.add_argument("--mac-graph-root", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_COMPARE_OUTPUT)
    args = parser.parse_args()

    task_uids = [item.strip() for item in args.task_uids.split(",") if item.strip()]
    payload = {
        "run_id": args.run_id,
        "bench": args.bench,
        "memory_system": args.memory_system,
        "tasks": [
            compare_task(
                task_uid,
                mac_graph_path=resolve_mac_graph_path(
                    bench=args.bench,
                    memory_system=args.memory_system,
                    run_id=args.run_id,
                    task_uid=task_uid,
                    mac_graph_root=args.mac_graph_root,
                ),
            )
            for task_uid in task_uids
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
