"""SOPBench adapter for the MAC agent loop.

Integration is not implemented yet; this module defines the MAC-owned boundary.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
MAC_SOPBENCH_DIR = REPO_ROOT / "bench" / "MAC" / "sopbench"
MAC_SOPBENCH_DATA_DIR = MAC_SOPBENCH_DIR / "data"
MAC_SOPBENCH_RESULTS_DIR = MAC_SOPBENCH_DIR / "results"
SOPBENCH_ROOT = REPO_ROOT / "bench" / "SOPBench"


def sopbench_root() -> Path:
    if (SOPBENCH_ROOT / "run_simulation.py").exists():
        return SOPBENCH_ROOT
    raise FileNotFoundError(f"Could not locate SOPBench source tree: {SOPBENCH_ROOT}")


def load_sopbench_eval_tasks(*args, **kwargs):  # noqa: ANN002, ANN003
    raise NotImplementedError("SOPBench is not wired into the MAC runtime yet")
