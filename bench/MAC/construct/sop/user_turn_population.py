#!/usr/bin/env python3
"""Populate SOPBench user turn histories from step4 semantic dependency deltas.

Per task:
- **warmup** (LLM): 3–4 user turns establishing g0 baseline SOP from the first turn in the
  composed temporal sequence (not the eval anchor)
- **normal**: per delta after g0 — LLM introduce + 1–10 heuristic carryover turns (truncated
  normal) sampled from a domain action request pool (one pool per visible tool/action with
  SOPBench user_goal templates)
- **actual_evaluation**: original ``mac_task_summary`` from step2

The final temporal turn realigns all mutated actions back to anchor before evaluation.

Reads ``eval_step4_temporal_delta.json`` + ``eval_step2_anchors.json``;
writes ``eval_step5_task_histories.json``.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib
import json
import os
import random
import re
import string
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[4]
SOP_ROOT = Path(__file__).resolve().parent
DEFAULT_ENV_FILE = Path("bench/.env")
DEFAULT_DELTA = Path("bench/MAC/sopbench/mid_data/eval_step4_temporal_delta.json")
DEFAULT_STEP2 = Path("bench/MAC/sopbench/mid_data/eval_step2_anchors.json")
DEFAULT_OUTPUT = Path("bench/MAC/sopbench/mid_data/eval_step5_task_histories.json")
DEFAULT_CACHE = Path("bench/MAC/sopbench/mid_data/user_turn_population_cache.json")
DEFAULT_POOL_SOURCE = Path("bench/SOPBench/data")
CACHE_VERSION = 4

SOPBENCH_DOMAIN_FILES = (
    "bank_tasks.json",
    "dmv_tasks.json",
    "healthcare_tasks.json",
    "hotel_tasks.json",
    "library_tasks.json",
    "online_market_tasks.json",
    "university_tasks.json",
)

sys.path.insert(0, str(SOP_ROOT))
from temporal_noise import get_action_dependency, sample_truncated_normal_int  # noqa: E402

DEFAULT_CARRYOVER_MIN = 1
DEFAULT_CARRYOVER_MAX = 10
DEFAULT_CARRYOVER_MEAN = 5.5
DEFAULT_CARRYOVER_STD = 2.0

INTRODUCE_SYSTEM_PROMPT = """
You generate user-only messages for a benchmark where the user is revising a domain SOP specification.

The user is NOT the end customer performing the action. They are updating procedural rules for an
assistant that enforces constraints before tool actions.

Return valid JSON only: {"content": "...", "scope_expression": "one sentence on which action/SOP is revised"}.

Requirements:
- Write exactly one user message.
- Naturally incorporate ALL added and removed constraint requirements from constraint_changes.
- Do NOT invent constraints beyond constraint_changes.
- Name the action under revision when helpful.
- Do not write assistant responses.
- Do not use greetings (Hello, Hi, Hey) or filler (just following up, quick check-in).
- Keep the message concise (2-6 sentences).
""".strip()

WARMUP_SYSTEM_PROMPT = """
You generate user-only messages for a benchmark where the user is authoring the baseline SOP for one action.

The user is a specification author, NOT the end customer. They are writing the initial procedural
rules (g0) that an assistant must enforce before executing the user_goal action.

Return valid JSON only:
{
  "turns": [
    {
      "content": "...",
      "scope_expression": "...",
      "constraint_uids": ["mac_constraint_uid", ...]
    }
  ]
}

Requirements:
- Return exactly the requested turn count.
- Together, the turns must cover ALL baseline_constraints without omitting any.
- Each constraint should appear in exactly one turn; split constraints across turns logically.
- SOP designer voice: state requirements, preconditions, and validation rules clearly.
- Do NOT write assistant responses.
- Do NOT use greetings (Hello, Hi, Hey) or conversational filler.
- Each turn: 1-4 sentences.
""".strip()

GREETING_PATTERN = re.compile(
    r"^(?:Hello!|Hello,|Hi!|Hi,|Hey,|Hey!|Good morning,|Good afternoon,)\s*",
    re.IGNORECASE,
)

THANKS_PATTERN = re.compile(
    r"\s*(?:Thank you!|Thank you\.|Thanks!|Thanks\.|Thanks in advance!)\s*$",
    re.IGNORECASE,
)

CARRYOVER_VARIANTS: tuple[tuple[tuple[str, str], ...], ...] = (
    (("I'd like to", "I need to"), ("Can you help me", "Please help me")),
    (("I would like to", "I'm looking to"), ("Could you", "Can you")),
    (("I'd like to", "I want to"), ("please", "")),
    (("Can you help me", "Help me"), ("set this up", "handle this")),
    (("I need to", "I want to"), ("Could you assist me", "Please assist me")),
    (("I am looking to", "I'm trying to"), ("Could you", "Can you")),
)

CARRYOVER_FIRST_NAMES = (
    "Alex",
    "Blake",
    "Casey",
    "Dana",
    "Elliot",
    "Finley",
    "Grace",
    "Harper",
    "Jordan",
    "Kelly",
    "Logan",
    "Morgan",
    "Quinn",
    "Riley",
    "Taylor",
)
CARRYOVER_LAST_NAMES = (
    "Adams",
    "Brooks",
    "Chen",
    "Diaz",
    "Evans",
    "Foster",
    "Garcia",
    "Hayes",
    "Ivanov",
    "Kim",
    "Lopez",
    "Nguyen",
    "Patel",
    "Reed",
    "Wright",
)
CARRYOVER_PRODUCTS = ("Laptop", "Mouse", "Headphones", "Smartphone", "Keyboard", "Monitor", "Tablet")
CARRYOVER_BOOK_TITLES = (
    "The Great Gatsby",
    "One Hundred Years of Solitude",
    "Pride and Prejudice",
    "The Silent Patient",
    "Project Hail Mary",
)
CARRYOVER_ROOM_TYPES = ("single", "double", "suite", "king", "deluxe")
CARRYOVER_POLICY_TYPES = ("Health", "Dental", "Pharmacy", "Vision")
CARRYOVER_PAYMENT_METHODS = ("credit card", "debit card", "cash", "loyalty points", "bank transfer")
CARRYOVER_TEST_TYPES = ("knowledge", "vision", "road", "written", "standard", "regular")
CARRYOVER_IDENTIFICATIONS = (
    "xk9mQ2pL7nR4",
    "bT6vH8wJ3sF1",
    "mN4cY7dK2pW9",
    "qR8fL5hG6jX3",
    "vB2nM9tC4wP7",
)

ENTITY_VARIATION_POOL: dict[str, tuple[str, ...]] = {
    "person_name": tuple(
        f"{first} {last}"
        for first in CARRYOVER_FIRST_NAMES
        for last in CARRYOVER_LAST_NAMES[:8]
    ),
    "username": tuple(
        [
            "alex_chen",
            "jordan_lee",
            "sam_patel",
            "casey_wright",
            "riley_kim",
            "morgan_diaz",
            "taylor_brooks",
            "quinn_adams",
            "user_4821",
            "user_7394",
        ]
    ),
    "provider_id": (
        "north_clinic_412",
        "south_hub_887",
        "east_center_203",
        "west_office_591",
        "metro_health_764",
    ),
    "product": CARRYOVER_PRODUCTS,
    "book_title": CARRYOVER_BOOK_TITLES,
    "room_type": CARRYOVER_ROOM_TYPES,
    "policy_type": CARRYOVER_POLICY_TYPES,
    "payment_method": CARRYOVER_PAYMENT_METHODS,
    "test_type": CARRYOVER_TEST_TYPES,
    "token": CARRYOVER_IDENTIFICATIONS,
    "code": ("SAVE15", "PROMO20", "DEAL25", "OFFER10", "GIFT30"),
    "comment": (
        "Works well for daily use.",
        "Good quality and fast delivery.",
        "Solid experience overall.",
        "Met my expectations.",
    ),
    "order_items": (
        "1 coffee and 1 salad",
        "2 sandwiches",
        "1 cheesecake and 1 tea",
        "1 soup and 1 bread",
    ),
    "plate_num": ("ABC1234", "XYZ9876", "QRS4567", "LMN8901", "DEF5678"),
    "room_id": ("101", "204", "305", "412", "518"),
    "order_id": ("ORD-4821", "ORD-7394", "ORD-1052", "ORD-8830"),
}

WARMUP_MATCH_STOPWORDS = frozenset(
    {
        "must",
        "have",
        "user",
        "with",
        "that",
        "this",
        "action",
        "perform",
        "previous",
        "correct",
        "credentials",
        "before",
        "within",
        "section",
        "database",
        "order",
        "conditions",
        "condition",
        "these",
        "their",
        "only",
        "when",
        "after",
        "than",
        "been",
        "from",
        "into",
        "will",
        "should",
        "would",
        "could",
        "also",
        "please",
        "being",
        "marked",
    }
)

UNQUOTED_EVAL_PATTERNS: tuple[tuple[str, str | None], ...] = (
    (r"(?:(?:Username|username))\s*:\s*([^\n,]+)", "username"),
    (r"(?:(?:Password|password|Identification|identification|admin password))\s*:\s*([^\n,]+)", "token"),
    (r"(?:(?:Order ID|order id|product_id|Product ID|Old Product ID|New Product ID))\s*:\s*([^\n,]+)", None),
    (r"(?:(?:guest named|reservation for|under the name|for the guest named))\s+([A-Z][a-z]+(?: [A-Z][a-z]+)?)", "guest_name"),
    (r"(?:(?:provider ID, which is|plate number))\s+\"?([^\".,\n]+)\"?", None),
)


@dataclass(frozen=True)
class TaskJob:
    ordinal: int
    total: int
    delta_task: dict[str, Any]
    step2_task: dict[str, Any]


@dataclass(frozen=True)
class G0Baseline:
    user_goal: str
    dependency_signature: str
    constraints: list[dict[str, Any]]


@dataclass(frozen=True)
class ActionRequestTemplate:
    prompt: str
    user_known: dict[str, Any]


@dataclass(frozen=True)
class ActionRequestPool:
    """Customer-style request templates keyed by (domain, action)."""

    templates: dict[tuple[str, str], tuple[ActionRequestTemplate, ...]]

    @classmethod
    def from_sopbench_data(cls, data_dir: Path) -> ActionRequestPool:
        grouped: dict[tuple[str, str], list[ActionRequestTemplate]] = {}
        root = resolve_path(data_dir)
        for filename in SOPBENCH_DOMAIN_FILES:
            path = root / filename
            if not path.is_file():
                raise FileNotFoundError(path)
            domain = filename.removesuffix("_tasks.json")
            raw = load_json(path)
            if not isinstance(raw, dict):
                raise ValueError(f"Expected top-level object in {path}")
            for action, tasks in raw.items():
                if not isinstance(tasks, list):
                    continue
                key = (domain, str(action))
                seen_prompt_keys: set[str] = set()
                for task in tasks:
                    if not isinstance(task, dict):
                        continue
                    prompt = str(task.get("user_prompt") or task.get("user_instruction") or "").strip()
                    if not prompt:
                        continue
                    prompt_key = normalize_carryover_dedupe_key(prompt)
                    if not prompt_key or prompt_key in seen_prompt_keys:
                        continue
                    seen_prompt_keys.add(prompt_key)
                    grouped.setdefault(key, []).append(
                        ActionRequestTemplate(
                            prompt=prompt,
                            user_known=copy.deepcopy(task.get("user_known") or {}),
                        )
                    )
        frozen = {key: tuple(values) for key, values in grouped.items() if values}
        return cls(templates=frozen)

    def actions_for_domain(self, domain: str) -> set[str]:
        return {action for domain_name, action in self.templates if domain_name == domain}

    def summary(self) -> dict[str, Any]:
        by_domain: dict[str, int] = {}
        template_counts: dict[str, int] = {}
        for (domain, action), entries in self.templates.items():
            by_domain[domain] = by_domain.get(domain, 0) + 1
            template_counts[f"{domain}:{action}"] = len(entries)
        return {
            "action_count": len(self.templates),
            "actions_by_domain": by_domain,
            "template_count": sum(template_counts.values()),
        }


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def load_json(path: Path, *, default: Any | None = None) -> Any:
    target = resolve_path(path)
    if not target.exists():
        if default is not None:
            return copy.deepcopy(default)
        raise FileNotFoundError(target)
    return json.loads(target.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    target = resolve_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def dependency_signature(dep: Any) -> str:
    if dep is None:
        return ""
    return json.dumps(dep, sort_keys=True, ensure_ascii=False)


def load_env(env_file: Path | None = None) -> None:
    if env_file:
        load_dotenv(resolve_path(env_file), override=False)
        return
    for candidate in (DEFAULT_ENV_FILE, Path(".env")):
        path = resolve_path(candidate)
        if path.exists():
            load_dotenv(path, override=False)
            return
    load_dotenv(override=False)


def resolve_llm_config(args: argparse.Namespace) -> None:
    if not args.model:
        args.model = os.getenv("MAC_LLM_MODEL") or os.getenv("LLM_MODEL")
    if not args.base_url:
        args.base_url = (
            os.getenv("OPENAI_BASE_URL")
            or os.getenv("MAC_LLM_BASE_URL")
            or os.getenv("LLM_BASE_URL")
        )
    if not args.api_key:
        args.api_key = os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY")


def call_llm(
    *,
    model: str,
    base_url: str | None,
    api_key: str | None,
    system_prompt: str,
    prompt: str,
    max_tokens: int,
    timeout: float,
    retries: int,
    sleep: float,
) -> str:
    try:
        openai_module = importlib.import_module("openai")
    except ImportError as exc:
        raise RuntimeError("openai package is required for live generation") from exc
    if not model:
        raise ValueError("Missing model. Pass --model or set MAC_LLM_MODEL.")
    if not api_key:
        raise ValueError("Missing API key. Pass --api-key or set OPENAI_API_KEY.")

    client = openai_module.OpenAI(
        api_key=api_key,
        base_url=base_url or None,
        timeout=timeout,
        max_retries=0,
    )
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                temperature=0.4,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
            )
            return response.choices[0].message.content or ""
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt == retries:
                break
            time.sleep(sleep * (2 ** (attempt - 1)))
    raise RuntimeError(f"LLM request failed after {retries} attempts: {last_error}") from last_error


def parse_llm_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", stripped, flags=re.DOTALL)
        if match:
            stripped = match.group(1).strip()
    payload = json.loads(stripped)
    if not isinstance(payload, dict):
        raise ValueError("LLM JSON root must be an object")
    return payload


def empty_cache() -> dict[str, Any]:
    return {
        "version": CACHE_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": None,
        "items": {},
    }


def load_cache(path: Path) -> dict[str, Any]:
    cache = load_json(path, default=empty_cache())
    if cache.get("version") != CACHE_VERSION:
        raise ValueError(f"Unsupported cache version: {cache.get('version')}")
    if not isinstance(cache.get("items"), dict):
        cache["items"] = {}
    return cache


def cache_get(cache: dict[str, Any], key: str, lock: threading.Lock) -> Any | None:
    with lock:
        item = cache.get("items", {}).get(key)
        if isinstance(item, dict) and "payload" in item:
            return copy.deepcopy(item["payload"])
    return None


def cache_record(
    cache: dict[str, Any],
    key: str,
    lock: threading.Lock,
    *,
    payload: Any,
) -> None:
    with lock:
        cache.setdefault("items", {})[key] = {
            "payload": payload,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        cache["updated_at"] = datetime.now(timezone.utc).isoformat()


def index_step2_tasks(tasks: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for task in tasks:
        if not isinstance(task, dict):
            continue
        uid = str(task.get("mac_task_uid") or "").strip()
        if uid:
            indexed[uid] = task
    return indexed


def collect_g0_baseline(
    step2_task: dict[str, Any],
    g0_payload: dict[str, Any] | None = None,
) -> G0Baseline:
    payload = g0_payload if isinstance(g0_payload, dict) else {}
    user_goal = str(payload.get("user_goal") or step2_task.get("user_goal") or "")
    constraints = payload.get("constraints") if isinstance(payload.get("constraints"), list) else []
    normalized_constraints: list[dict[str, Any]] = []
    seen_text: set[str] = set()
    for constraint in constraints:
        if not isinstance(constraint, dict):
            continue
        text = str(constraint.get("text") or "").strip()
        if not text or text in seen_text:
            continue
        seen_text.add(text)
        normalized_constraints.append(
            {
                "mac_constraint_uid": str(constraint.get("mac_constraint_uid") or ""),
                "text": text,
                "constraint_id": constraint.get("constraint_id"),
            }
        )
    if normalized_constraints:
        dep_sig = str(payload.get("dependency_signature") or "")
        if not dep_sig and payload.get("user_goal_dependency") is not None:
            dep_sig = dependency_signature(payload.get("user_goal_dependency"))
        return G0Baseline(
            user_goal=user_goal,
            dependency_signature=dep_sig,
            constraints=normalized_constraints,
        )

    # Legacy fallback: step2 anchor dependency (pre g0-from-sequence fix).
    dep = get_action_dependency(step2_task, user_goal)
    seen: set[str] = set()
    fallback_constraints: list[dict[str, Any]] = []
    for constraint in step2_task.get("constraints") or []:
        if not isinstance(constraint, dict):
            continue
        if str(constraint.get("action") or "") != user_goal:
            continue
        uid = str(constraint.get("mac_constraint_uid") or "")
        text = str(constraint.get("text") or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        fallback_constraints.append(
            {
                "mac_constraint_uid": uid,
                "text": text,
                "constraint_id": (constraint.get("metadata") or {}).get("constraint_id"),
            }
        )
    return G0Baseline(
        user_goal=user_goal,
        dependency_signature=dependency_signature(dep),
        constraints=fallback_constraints,
    )


def g0_graph_record(g0: G0Baseline) -> dict[str, Any]:
    return {
        "graph_id": "g0",
        "user_goal": g0.user_goal,
        "dependency_signature": g0.dependency_signature,
        "constraint_count": len(g0.constraints),
    }


def graph_delta_record(delta_turn: dict[str, Any]) -> dict[str, Any]:
    return {
        "from_local_id": delta_turn.get("from_local_id"),
        "to_local_id": delta_turn.get("to_local_id"),
        "from_dependency_signature": delta_turn.get("before_signature"),
        "to_dependency_signature": delta_turn.get("after_signature"),
        "dependency_changed": delta_turn.get("dependency_changed"),
        "sequence_order": delta_turn.get("sequence_order"),
        "action": delta_turn.get("action"),
        "mutation": delta_turn.get("mutation"),
    }


def constraint_diff_record(delta_turn: dict[str, Any]) -> dict[str, Any]:
    diff = delta_turn.get("diff") or {}
    return {
        "unchanged": bool(diff.get("unchanged")),
        "added": list(diff.get("added") or []),
        "removed": list(diff.get("removed") or []),
    }


def forbidden_constraint_texts(delta_turn: dict[str, Any]) -> set[str]:
    diff = constraint_diff_record(delta_turn)
    return {str(item).strip() for item in diff["added"] + diff["removed"] if str(item).strip()}


def build_introduce_prompt(
    *,
    step2_task: dict[str, Any],
    delta_turn: dict[str, Any],
) -> str:
    payload = {
        "domain": step2_task.get("domain"),
        "user_goal": step2_task.get("user_goal"),
        "action_under_revision": delta_turn.get("action"),
        "mutation": delta_turn.get("mutation"),
        "graph_delta": graph_delta_record(delta_turn),
        "constraint_changes": constraint_diff_record(delta_turn),
        "delta_summary": delta_turn.get("summary"),
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def build_warmup_prompt(*, step2_task: dict[str, Any], g0: G0Baseline, turn_count: int) -> str:
    payload = {
        "domain": step2_task.get("domain"),
        "user_goal": g0.user_goal,
        "g0_graph": g0_graph_record(g0),
        "baseline_constraints": g0.constraints,
        "requested_turn_count": turn_count,
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def dry_run_introduce(delta_turn: dict[str, Any]) -> dict[str, str]:
    if str(delta_turn.get("kind") or "") == "anchor_alignment":
        return {
            "content": (
                "Realign all previously revised SOP actions back to the current anchor "
                "specification so every constraint matches the approved final version."
            ),
            "scope_expression": "Task-wide SOP realignment to anchor.",
        }
    action = str(delta_turn.get("action") or "the action")
    diff = constraint_diff_record(delta_turn)
    parts = [f"Revise SOP dependency rules for `{action}`."]
    if diff["removed"]:
        parts.append("Remove:")
        parts.extend(f"- {item}" for item in diff["removed"][:4])
    if diff["added"]:
        parts.append("Add:")
        parts.extend(f"- {item}" for item in diff["added"][:4])
    return {
        "content": "\n".join(parts),
        "scope_expression": f"SOP revision for `{action}` ({delta_turn.get('from_local_id')} -> {delta_turn.get('to_local_id')}).",
    }


def dry_run_warmup(g0: G0Baseline, turn_count: int) -> list[dict[str, Any]]:
    if not g0.constraints:
        return [
            {
                "content": f"Define the baseline SOP dependency rules for `{g0.user_goal}`.",
                "scope_expression": f"Baseline g0 setup for `{g0.user_goal}`.",
                "constraint_uids": [],
            }
            for _ in range(turn_count)
        ]
    turns: list[dict[str, Any]] = []
    for index in range(turn_count):
        assigned = [
            g0.constraints[j]
            for j in range(len(g0.constraints))
            if j % turn_count == index
        ]
        lines = [f"Baseline SOP for `{g0.user_goal}` — establish:"]
        lines.extend(f"- {item['text']}" for item in assigned)
        turns.append(
            {
                "content": "\n".join(lines),
                "scope_expression": f"g0 baseline chunk {index + 1}/{turn_count} for `{g0.user_goal}`.",
                "constraint_uids": [item["mac_constraint_uid"] for item in assigned if item["mac_constraint_uid"]],
            }
        )
    return turns


def validate_warmup_turns(
    turns: list[dict[str, Any]],
    *,
    expected_count: int,
    g0: G0Baseline,
) -> tuple[list[dict[str, Any]], list[str]]:
    if len(turns) != expected_count:
        raise ValueError(f"warmup expected {expected_count} turns, got {len(turns)}")
    valid_uids = {c["mac_constraint_uid"] for c in g0.constraints if c.get("mac_constraint_uid")}
    covered: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for index, turn in enumerate(turns):
        content = str(turn.get("content") or "").strip()
        if not content:
            raise ValueError(f"warmup turn {index} has empty content")
        uids = [str(uid) for uid in (turn.get("constraint_uids") or []) if str(uid)]
        for uid in uids:
            if uid not in valid_uids:
                raise ValueError(f"warmup turn {index} references unknown constraint uid {uid}")
            covered.add(uid)
        normalized.append(
            {
                "content": content,
                "scope_expression": str(turn.get("scope_expression") or "").strip(),
                "constraint_uids": uids,
            }
        )
    if g0.constraints and covered != valid_uids:
        missing = sorted(valid_uids - covered)
        raise ValueError(f"warmup turns did not cover constraint uids: {missing[:5]}")
    return supplement_warmup_constraint_uids(normalized, g0=g0)


def normalize_match_text(text: str) -> str:
    cleaned = str(text or "").lower()
    cleaned = cleaned.replace("'", "'")
    cleaned = re.sub(r"\*\*", " ", cleaned)
    cleaned = re.sub(r"[^\w\s\"]", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def constraint_keywords(text: str) -> set[str]:
    words = set(re.findall(r"[a-z0-9_]{4,}", normalize_match_text(text)))
    for match in re.finditer(r'"(\w+)"', text):
        words.add(match.group(1).lower())
    return {word for word in words if word not in WARMUP_MATCH_STOPWORDS}


def score_constraint_in_turn(constraint_text: str, turn_content: str) -> float:
    constraint_keys = constraint_keywords(constraint_text)
    turn_keys = constraint_keywords(turn_content)
    if not constraint_keys:
        return 0.0
    overlap = constraint_keys & turn_keys
    score = len(overlap) / len(constraint_keys)
    normalized_constraint = normalize_match_text(constraint_text)
    normalized_turn = normalize_match_text(turn_content)
    words = normalized_constraint.split()
    for phrase_len in (8, 6, 5):
        for index in range(max(0, len(words) - phrase_len + 1)):
            phrase = " ".join(words[index : index + phrase_len])
            if len(phrase) >= 24 and phrase in normalized_turn:
                score = max(score, 0.9)
    return score


def supplement_warmup_constraint_uids(
    turns: list[dict[str, Any]],
    *,
    g0: G0Baseline,
    min_score: float = 0.34,
) -> tuple[list[dict[str, Any]], list[str]]:
    valid_uids = {
        str(item["mac_constraint_uid"]): item
        for item in g0.constraints
        if item.get("mac_constraint_uid")
    }
    if not valid_uids:
        return turns, []

    assigned: dict[str, int] = {}
    for index, turn in enumerate(turns):
        for uid in turn.get("constraint_uids") or []:
            uid = str(uid)
            if uid in valid_uids and uid not in assigned:
                assigned[uid] = index

    unassigned = [uid for uid in valid_uids if uid not in assigned]
    candidates: list[tuple[float, str, int]] = []
    for uid in unassigned:
        constraint_text = str(valid_uids[uid].get("text") or "")
        for index, turn in enumerate(turns):
            score = score_constraint_in_turn(constraint_text, str(turn.get("content") or ""))
            if score >= min_score:
                candidates.append((score, uid, index))
    candidates.sort(key=lambda item: item[0], reverse=True)
    for _score, uid, index in candidates:
        if uid not in assigned:
            assigned[uid] = index

    turn_uids: list[list[str]] = [[] for _ in turns]
    for uid, index in assigned.items():
        turn_uids[index].append(uid)

    updated: list[dict[str, Any]] = []
    warnings: list[str] = []
    for index, turn in enumerate(turns):
        patched = dict(turn)
        patched["constraint_uids"] = sorted(turn_uids[index])
        updated.append(patched)

    for uid in sorted(valid_uids):
        if uid not in assigned:
            warnings.append(
                f"warmup uid unmatched: {uid} :: {str(valid_uids[uid].get('text') or '')[:120]}"
            )
    return updated, warnings


def generate_warmup_turns(
    *,
    step2_task: dict[str, Any],
    g0: G0Baseline,
    turn_count: int,
    args: argparse.Namespace,
    cache: dict[str, Any],
    cache_lock: threading.Lock,
) -> tuple[list[dict[str, Any]], str, list[str]]:
    cache_payload = {
        "mac_task_uid": step2_task.get("mac_task_uid"),
        "dependency_signature": g0.dependency_signature,
        "constraints": g0.constraints,
        "turn_count": turn_count,
    }
    cache_key = sha256_text(stable_json({"kind": "warmup", "model": args.model, "payload": cache_payload}))
    cached = None if args.dry_run else cache_get(cache, cache_key, cache_lock)
    if cached is not None:
        turns, uid_warnings = validate_warmup_turns(cached, expected_count=turn_count, g0=g0)
        return turns, "hit", uid_warnings

    if args.dry_run:
        turns = dry_run_warmup(g0, turn_count)
        turns, uid_warnings = supplement_warmup_constraint_uids(turns, g0=g0)
        return turns, "dry_run", uid_warnings

    raw = call_llm(
        model=args.model,
        base_url=args.base_url,
        api_key=args.api_key,
        system_prompt=WARMUP_SYSTEM_PROMPT,
        prompt=build_warmup_prompt(step2_task=step2_task, g0=g0, turn_count=turn_count),
        max_tokens=args.max_tokens,
        timeout=args.timeout,
        retries=args.retries,
        sleep=args.sleep,
    )
    payload = parse_llm_json(raw)
    turns_raw = payload.get("turns")
    if not isinstance(turns_raw, list):
        raise ValueError("warmup LLM response must contain turns[]")
    turns, uid_warnings = validate_warmup_turns(turns_raw, expected_count=turn_count, g0=g0)
    cache_record(cache, cache_key, cache_lock, payload=turns)
    return turns, "miss", uid_warnings


def generate_introduce_turn(
    *,
    step2_task: dict[str, Any],
    delta_turn: dict[str, Any],
    args: argparse.Namespace,
    cache: dict[str, Any],
    cache_lock: threading.Lock,
) -> tuple[dict[str, str], str]:
    cache_payload = {
        "mac_task_uid": step2_task.get("mac_task_uid"),
        "to_local_id": delta_turn.get("to_local_id"),
        "before_signature": delta_turn.get("before_signature"),
        "after_signature": delta_turn.get("after_signature"),
        "diff": constraint_diff_record(delta_turn),
    }
    cache_key = sha256_text(stable_json({"kind": "introduce", "model": args.model, "payload": cache_payload}))
    cached = None if args.dry_run else cache_get(cache, cache_key, cache_lock)
    if cached:
        return cached, "hit"

    if args.dry_run:
        return dry_run_introduce(delta_turn), "dry_run"

    raw = call_llm(
        model=args.model,
        base_url=args.base_url,
        api_key=args.api_key,
        system_prompt=INTRODUCE_SYSTEM_PROMPT,
        prompt=build_introduce_prompt(step2_task=step2_task, delta_turn=delta_turn),
        max_tokens=args.max_tokens,
        timeout=args.timeout,
        retries=args.retries,
        sleep=args.sleep,
    )
    payload = parse_llm_json(raw)
    content = str(payload.get("content") or "").strip()
    if not content:
        raise ValueError("introduce LLM returned empty content")
    result = {
        "content": content,
        "scope_expression": str(payload.get("scope_expression") or "").strip(),
    }
    cache_record(cache, cache_key, cache_lock, payload=result)
    return result, "miss"


def strip_carryover_filler(text: str) -> str:
    text = GREETING_PATTERN.sub("", text.strip())
    text = THANKS_PATTERN.sub("", text.strip())
    return re.sub(r"\s+", " ", text).strip()


def infer_carryover_value_kind(key: str | None, value: str) -> str:
    key_l = (key or "").lower()
    if key_l in {"guest_name", "destination_username"} or key_l.endswith("_name"):
        return "person_name"
    if key_l == "username":
        if " " in value:
            return "person_name"
        return "username"
    if "date" in key_l or re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return "date"
    if key_l in {
        "amount",
        "coverage_amount",
        "annual_income",
        "total_assets",
        "monthly_income",
        "pay_owed_amount_request",
        "quantity",
        "rating",
    }:
        return "number"
    if key_l in {"password", "identification", "admin_password", "card_number"}:
        return "token"
    if key_l in {"room_type", "policy_type", "payment_method", "order_type", "test_type", "unit"}:
        return "category"
    if key_l in {"comment", "order_items", "book_title", "address_new", "safety_box_new"}:
        return "text"
    if key_l in {"product_id", "old_product_id", "new_product_id"}:
        return "product"
    if key_l in {"coupon_code"}:
        return "code"
    if key_l in {"plate_num", "room_id", "provider_id", "order_id"} or key_l.endswith("_id"):
        return "identifier"
    if key_l == "key_returned":
        return "boolean"
    if value.startswith("$") and re.fullmatch(r"\$\d+(?:\.\d+)?", value):
        return "dollar_amount"
    if re.fullmatch(r"\d+\.?\d*", value):
        return "number"
    if re.fullmatch(r"[A-Z0-9-]+", value) and any(char.isdigit() for char in value):
        return "identifier"
    return "text"


def collect_eval_grounding_values(eval_prompt: str, step2_task: dict[str, Any]) -> set[str]:
    slots, grounding = collect_eval_field_slots(eval_prompt, step2_task)
    del slots
    return grounding


def collect_eval_field_slots(
    eval_prompt: str,
    step2_task: dict[str, Any],
) -> tuple[list[dict[str, Any]], set[str]]:
    user_known = (step2_task.get("original_sopbench") or {}).get("user_known") or {}
    slots: list[dict[str, Any]] = []
    seen: set[str] = set()
    grounding: set[str] = set()

    def add_slot(original: str, key: str | None, kind: str | None = None) -> None:
        value = str(original or "").strip()
        if len(value) < 2:
            return
        canonical = value.casefold()
        if canonical in seen:
            return
        slot_kind = kind or infer_carryover_value_kind(key, value)
        slots.append({"original": value, "kind": slot_kind, "key": key})
        seen.add(canonical)
        grounding.add(value)

    for key, raw in user_known.items():
        value = str(raw)
        if value in eval_prompt:
            add_slot(value, str(key))
            continue
        pattern = re.compile(re.escape(value), re.IGNORECASE)
        match = pattern.search(eval_prompt)
        if match:
            add_slot(match.group(0), str(key))

    for match in re.finditer(r'"([^"]{2,})"', eval_prompt):
        add_slot(match.group(1), None)

    for pattern, key_hint in UNQUOTED_EVAL_PATTERNS:
        for match in re.finditer(pattern, eval_prompt, flags=re.IGNORECASE):
            add_slot(match.group(1).strip(), key_hint)

    for match in re.finditer(r"\b\d{4}-\d{2}-\d{2}\b", eval_prompt):
        add_slot(match.group(0), "date", "date")
    for match in re.finditer(r"\$\d+(?:\.\d+)?", eval_prompt):
        add_slot(match.group(0), "amount", "dollar_amount")

    slots.sort(key=lambda item: len(str(item["original"])), reverse=True)
    return slots, grounding


def pick_entity_variation(
    rng: random.Random,
    *,
    kind: str,
    original: str,
    key: str | None,
) -> str:
    pool = ENTITY_VARIATION_POOL.get(kind)
    if pool:
        choices = [item for item in pool if item != original]
        if choices:
            return rng.choice(choices)
    return random_carryover_value(rng, kind=kind, original=original, key=key)


def replace_grounding_value(text: str, original: str, replacement: str) -> str:
    return re.sub(re.escape(original), lambda _match: replacement, text, flags=re.IGNORECASE)


def sanitize_carryover_text(text: str) -> str:
    cleaned = re.sub(r",\s*\?", "?", text)
    cleaned = re.sub(r"\?\s*\?", "?", cleaned)
    cleaned = re.sub(r"\s+,", ",", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.")
    return cleaned


def normalize_carryover_dedupe_key(content: str) -> str:
    cleaned = sanitize_carryover_text(str(content or ""))
    cleaned = cleaned.replace("'", "'")
    cleaned = re.sub(r"[^\w\s$]", " ", cleaned.casefold())
    return re.sub(r"\s+", " ", cleaned).strip()


def register_carryover_dedupe_key(seen_keys: set[str], content: str) -> str | None:
    key = normalize_carryover_dedupe_key(content)
    if not key or key in seen_keys:
        return None
    seen_keys.add(key)
    return key


def content_has_eval_grounding(content: str, grounding: set[str]) -> bool:
    lowered = content.casefold()
    for value in grounding:
        if len(value) < 4:
            continue
        if value.casefold() in lowered:
            return True
    return False


def random_carryover_person_name(rng: random.Random) -> str:
    return f"{rng.choice(CARRYOVER_FIRST_NAMES)} {rng.choice(CARRYOVER_LAST_NAMES)}"


def random_carryover_token(rng: random.Random, *, min_len: int = 8, max_len: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits
    length = rng.randint(min_len, max_len)
    return "".join(rng.choice(alphabet) for _ in range(length))


def random_carryover_date(rng: random.Random) -> str:
    start = datetime(2024, 1, 1)
    end = datetime(2026, 12, 31)
    offset = rng.randint(0, (end - start).days)
    return (start + timedelta(days=offset)).strftime("%Y-%m-%d")


def random_carryover_number(rng: random.Random, original: str) -> str:
    if "." in original or original.startswith("$"):
        bare = original.lstrip("$")
        return str(round(rng.uniform(10, max(100, float(bare or 100) * 1.5)), 1))
    return str(rng.randint(50, 9999))


def random_carryover_identifier(rng: random.Random, original: str, key: str | None) -> str:
    key_l = (key or "").lower()
    if key_l == "provider_id" or "_" in original:
        return f"{rng.choice(['north', 'south', 'east', 'west', 'metro'])}_{rng.choice(['clinic', 'hub', 'center'])}_{rng.randint(100, 999)}"
    if original.startswith("ORD-"):
        return f"ORD-{rng.randint(100, 9999)}"
    if key_l == "plate_num":
        return "".join(rng.choice(string.ascii_uppercase + string.digits) for _ in range(max(6, len(original))))
    if key_l == "room_id":
        return str(rng.randint(100, 999))
    if re.fullmatch(r"[A-Z0-9-]+", original):
        alphabet = string.ascii_uppercase + string.digits
        return "".join(rng.choice(alphabet) for _ in range(max(4, len(original))))
    return random_carryover_token(rng)


def random_carryover_category(rng: random.Random, key: str | None) -> str:
    key_l = (key or "").lower()
    if key_l == "room_type":
        return rng.choice(CARRYOVER_ROOM_TYPES)
    if key_l == "policy_type":
        return rng.choice(CARRYOVER_POLICY_TYPES)
    if key_l == "payment_method":
        return rng.choice(CARRYOVER_PAYMENT_METHODS)
    return rng.choice(["standard", "premium", "express", "regular"])


def random_carryover_value(
    rng: random.Random,
    *,
    kind: str,
    original: str,
    key: str | None,
) -> str:
    for _ in range(10):
        if kind == "date":
            candidate = random_carryover_date(rng)
        elif kind == "person_name":
            candidate = random_carryover_person_name(rng)
        elif kind == "username":
            candidate = rng.choice(
                [
                    random_carryover_person_name(rng).lower().replace(" ", "_"),
                    f"user_{rng.randint(1000, 9999)}",
                    f"{rng.choice(CARRYOVER_FIRST_NAMES).lower()}_{rng.randint(10, 99)}",
                ]
            )
        elif kind == "number":
            candidate = random_carryover_number(rng, original)
        elif kind == "dollar_amount":
            candidate = f"${random_carryover_number(rng, original)}"
        elif kind == "token":
            candidate = random_carryover_token(rng)
        elif kind == "category":
            candidate = random_carryover_category(rng, key)
        elif kind == "product":
            candidate = rng.choice(CARRYOVER_PRODUCTS)
        elif kind == "code":
            candidate = "".join(rng.choice(string.ascii_uppercase + string.digits) for _ in range(6))
        elif kind == "boolean":
            candidate = rng.choice(["true", "false"])
        elif kind == "text":
            if (key or "").lower() == "book_title":
                candidate = rng.choice(CARRYOVER_BOOK_TITLES)
            elif (key or "").lower() == "comment":
                candidate = rng.choice(ENTITY_VARIATION_POOL["comment"])
            elif (key or "").lower() == "order_items":
                candidate = rng.choice(ENTITY_VARIATION_POOL["order_items"])
            elif (key or "").lower() in {"address_new", "safety_box_new"}:
                candidate = rng.choice(
                    [
                        "123 Main Street",
                        "456 Oak Avenue",
                        "789 Pine Road",
                        "Suite 12B",
                    ]
                )
            else:
                candidate = random_carryover_token(rng)
        elif kind == "identifier":
            candidate = random_carryover_identifier(rng, original, key)
        else:
            candidate = random_carryover_token(rng)
        if candidate != original:
            return candidate
    return f"sample_{rng.randint(1000, 9999)}"


def apply_carryover_field_randomization(
    text: str,
    field_slots: list[dict[str, Any]],
    rng: random.Random,
) -> str:
    updated = text
    for slot in field_slots:
        replacement = pick_entity_variation(
            rng,
            kind=str(slot["kind"]),
            original=str(slot["original"]),
            key=slot.get("key"),
        )
        updated = replace_grounding_value(updated, str(slot["original"]), replacement)
    return sanitize_carryover_text(updated)


def apply_carryover_variant(base_text: str, variant: int) -> str:
    text = strip_carryover_filler(base_text)
    replacements = CARRYOVER_VARIANTS[variant % len(CARRYOVER_VARIANTS)]
    for pattern, repl in replacements:
        text = re.sub(pattern, repl, text, count=1, flags=re.IGNORECASE)
    return sanitize_carryover_text(text)


def heuristic_carryover_turn(
    *,
    eval_prompt: str,
    variant: int,
    forbidden: set[str],
    field_slots: list[dict[str, Any]],
    eval_grounding: set[str],
    rng: random.Random,
) -> str | None:
    content = apply_carryover_variant(eval_prompt, variant)
    content = apply_carryover_field_randomization(content, field_slots, rng)
    if not content or content == sanitize_carryover_text(strip_carryover_filler(eval_prompt)):
        return None
    lowered = content.lower()
    for phrase in forbidden:
        snippet = phrase[:60].lower()
        if snippet and snippet in lowered:
            return None
    if GREETING_PATTERN.match(content):
        return None
    if content_has_eval_grounding(content, eval_grounding):
        return None
    return content


def generate_carryover_block(
    *,
    eval_prompt: str,
    field_slots: list[dict[str, Any]],
    eval_grounding: set[str],
    forbidden: set[str],
    carryover_count: int,
    rng: random.Random,
    seen_keys: set[str] | None = None,
) -> list[str]:
    dedupe_keys = seen_keys if seen_keys is not None else set()
    generated: list[str] = []
    attempt = 0
    max_attempts = max(carryover_count * 16, 64)
    while len(generated) < carryover_count and attempt < max_attempts:
        attempt += 1
        content = heuristic_carryover_turn(
            eval_prompt=eval_prompt,
            variant=attempt + rng.randint(0, 3),
            forbidden=forbidden,
            field_slots=field_slots,
            eval_grounding=eval_grounding,
            rng=rng,
        )
        if not content or register_carryover_dedupe_key(dedupe_keys, content) is None:
            continue
        generated.append(content)
    return generated


def visible_tool_actions(step2_task: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for tool in step2_task.get("tools") or []:
        if not isinstance(tool, dict):
            continue
        fn = tool.get("function") if tool.get("type") == "function" else tool
        if not isinstance(fn, dict):
            continue
        name = str(fn.get("name") or "").strip()
        if name and name != "send_message":
            names.add(name)
    return names


def eligible_carryover_actions(
    *,
    domain: str,
    visible_actions: set[str],
    action_pool: ActionRequestPool,
) -> list[str]:
    return sorted(
        action
        for action in visible_actions
        if action_pool.templates.get((domain, action))
    )


def template_task_stub(template: ActionRequestTemplate) -> dict[str, Any]:
    return {"original_sopbench": {"user_known": copy.deepcopy(template.user_known)}}


def generate_carryover_block_from_pool(
    *,
    domain: str,
    visible_actions: set[str],
    action_pool: ActionRequestPool,
    eval_prompt: str,
    eval_grounding: set[str],
    forbidden: set[str],
    carryover_count: int,
    rng: random.Random,
    seen_keys: set[str],
) -> list[dict[str, Any]]:
    eligible_actions = eligible_carryover_actions(
        domain=domain,
        visible_actions=visible_actions,
        action_pool=action_pool,
    )
    if not eligible_actions:
        return []

    generated: list[dict[str, Any]] = []
    attempt = 0
    max_attempts = max(carryover_count * 24, len(seen_keys) + carryover_count * 12, 96)
    while len(generated) < carryover_count and attempt < max_attempts:
        attempt += 1
        action = rng.choice(eligible_actions)
        templates = action_pool.templates[(domain, action)]
        template = rng.choice(templates)
        field_slots, _ = collect_eval_field_slots(template.prompt, template_task_stub(template))
        content = heuristic_carryover_turn(
            eval_prompt=template.prompt,
            variant=attempt + rng.randint(0, max(len(CARRYOVER_VARIANTS) - 1, 0)),
            forbidden=forbidden,
            field_slots=field_slots,
            eval_grounding=eval_grounding,
            rng=rng,
        )
        if not content or register_carryover_dedupe_key(seen_keys, content) is None:
            continue
        generated.append({"content": content, "source_action": action})
    return generated


def seed_carryover_seen_keys(
    *,
    eval_prompt: str,
    output_turns: list[dict[str, Any]],
) -> set[str]:
    seen_keys: set[str] = set()
    if eval_prompt.strip():
        eval_key = normalize_carryover_dedupe_key(eval_prompt)
        if eval_key:
            seen_keys.add(eval_key)
    for turn in output_turns:
        if turn.get("kind") != "carryover":
            continue
        content = str(turn.get("content") or "")
        key = normalize_carryover_dedupe_key(content)
        if key:
            seen_keys.add(key)
    return seen_keys


CARRYOVER_POLICY = (
    "domain action request pool sampled from visible tools with SOPBench user_goal templates; "
    "entity_variation_pool with eval-grounding scrub; normalized task-level dedupe; no greetings/filler"
)


def plan_carryover_count(rng: random.Random, args: argparse.Namespace) -> int:
    return sample_truncated_normal_int(
        rng,
        value_min=args.carryover_min,
        value_max=args.carryover_max,
        mean=args.carryover_mean,
        std=args.carryover_std,
    )


def plan_warmup_count(rng: random.Random, args: argparse.Namespace) -> int:
    return rng.randint(args.warmup_min, args.warmup_max)


def reindex_turns(turns: list[dict[str, Any]]) -> None:
    for index, turn in enumerate(turns):
        turn["turn_index"] = index


def append_actual_evaluation_turn(
    *,
    eval_prompt: str,
    output_turns: list[dict[str, Any]],
) -> bool:
    content = eval_prompt.strip()
    if not content:
        return False
    output_turns.append(
        {
            "role": "user",
            "phase": "evaluation",
            "kind": "actual_evaluation",
            "content": content,
            "scope_expression": "Original SOPBench user_goal eval prompt (unchanged).",
            "mentions_constraint": False,
        }
    )
    return True


def process_task(
    job: TaskJob,
    *,
    args: argparse.Namespace,
    cache: dict[str, Any],
    cache_lock: threading.Lock,
) -> dict[str, Any]:
    delta_task = job.delta_task
    step2_task = job.step2_task
    task_uid = str(delta_task.get("mac_task_uid") or step2_task.get("mac_task_uid") or "")
    print(f"populating user turns {job.ordinal}/{job.total} task={task_uid}", flush=True)

    eval_prompt = str(step2_task.get("mac_task_summary") or "").strip()
    _, eval_grounding = collect_eval_field_slots(eval_prompt, step2_task)
    domain = str(step2_task.get("domain") or "")
    visible_actions = visible_tool_actions(step2_task)
    action_pool: ActionRequestPool = args.action_pool
    g0_payload = delta_task.get("g0") if isinstance(delta_task.get("g0"), dict) else {}
    g0 = collect_g0_baseline(step2_task, g0_payload)
    g0_sequence_order = int(
        g0_payload.get("sequence_order")
        or delta_task.get("g0_sequence_order")
        or 1
    )
    turns_delta = sorted(
        [
            t
            for t in (delta_task.get("turns") or [])
            if isinstance(t, dict)
            and int(t.get("sequence_order") or 0) > g0_sequence_order
        ],
        key=lambda item: int(item.get("sequence_order") or 0),
    )
    rng = random.Random(args.seed + int(sha256_text(task_uid)[:8], 16))
    output_turns: list[dict[str, Any]] = []
    task_carryover_seen = seed_carryover_seen_keys(eval_prompt=eval_prompt, output_turns=[])
    warnings: list[str] = []
    errors: list[str] = []
    introduce_generations: list[dict[str, Any]] = []
    cache_counts: Counter[str] = Counter()

    warmup_count = plan_warmup_count(rng, args)
    try:
        warmup_turns, warmup_cache, warmup_uid_warnings = generate_warmup_turns(
            step2_task=step2_task,
            g0=g0,
            turn_count=warmup_count,
            args=args,
            cache=cache,
            cache_lock=cache_lock,
        )
        cache_counts[f"warmup_{warmup_cache}"] += 1
        warnings.extend(warmup_uid_warnings)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"warmup failed: {exc}")
        if args.allow_placeholder:
            warmup_turns = dry_run_warmup(g0, warmup_count)
            cache_counts["warmup_placeholder"] += 1
            warnings.append(f"warmup placeholder used: {exc}")
        else:
            warmup_turns = []

    for warmup_index, warmup in enumerate(warmup_turns):
        output_turns.append(
            {
                "role": "user",
                "phase": "warmup",
                "kind": "warmup",
                "warmup_index": warmup_index,
                "content": warmup["content"],
                "scope_expression": warmup.get("scope_expression", ""),
                "mentions_constraint": True,
                "g0_graph": g0_graph_record(g0),
                "constraint_uids": warmup.get("constraint_uids") or [],
            }
        )

    for delta_turn in turns_delta:
        local_id = str(delta_turn.get("local_id") or "")
        try:
            introduce_payload, cache_status = generate_introduce_turn(
                step2_task=step2_task,
                delta_turn=delta_turn,
                args=args,
                cache=cache,
                cache_lock=cache_lock,
            )
            cache_counts[f"introduce_{cache_status}"] += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(f"introduce failed for {local_id}: {exc}")
            if args.allow_placeholder:
                introduce_payload = dry_run_introduce(delta_turn)
                cache_counts["introduce_placeholder"] += 1
                warnings.append(f"introduce placeholder used for {local_id}: {exc}")
            else:
                continue

        introduce_index = len(output_turns)
        output_turns.append(
            {
                "role": "user",
                "phase": "normal",
                "kind": "introduce",
                "content": introduce_payload["content"],
                "scope_expression": introduce_payload.get("scope_expression", ""),
                "mentions_constraint": True,
                "source_delta_local_id": local_id,
                "source_delta_sequence_order": delta_turn.get("sequence_order"),
                "action": delta_turn.get("action"),
                "mutation": delta_turn.get("mutation"),
                "source_mac_constraint_uid": delta_turn.get("source_mac_constraint_uid"),
                "graph_delta": graph_delta_record(delta_turn),
                "constraint_diff": constraint_diff_record(delta_turn),
            }
        )
        introduce_generations.append(
            {
                "source_delta_local_id": local_id,
                "carryover_planned": 0,
            }
        )

        forbidden = forbidden_constraint_texts(delta_turn)
        carryover_count = plan_carryover_count(rng, args)
        introduce_generations[-1]["carryover_planned"] = carryover_count
        if args.skip_carryover:
            continue
        carryover_entries = generate_carryover_block_from_pool(
            domain=domain,
            visible_actions=visible_actions,
            action_pool=action_pool,
            eval_prompt=eval_prompt,
            eval_grounding=eval_grounding,
            forbidden=forbidden,
            carryover_count=carryover_count,
            rng=rng,
            seen_keys=task_carryover_seen,
        )
        generated_carryover = len(carryover_entries)
        for entry in carryover_entries:
            content = str(entry.get("content") or "")
            source_action = str(entry.get("source_action") or "")
            output_turns.append(
                {
                    "role": "user",
                    "phase": "normal",
                    "kind": "carryover",
                    "content": content,
                    "scope_expression": (
                        f"Synthetic `{source_action}` customer request filler with randomized "
                        "field values; no constraint restatement."
                    ),
                    "mentions_constraint": False,
                    "source_introduce_turn_index": introduce_index,
                    "source_delta_local_id": local_id,
                    "source_action": source_action,
                }
            )
        if generated_carryover < carryover_count:
            warnings.append(
                f"carryover under-filled for {local_id}: {generated_carryover}/{carryover_count} "
                f"(eligible_actions={len(eligible_carryover_actions(domain=domain, visible_actions=visible_actions, action_pool=action_pool))})"
            )

    has_eval = append_actual_evaluation_turn(eval_prompt=eval_prompt, output_turns=output_turns)
    if not has_eval:
        errors.append("missing mac_task_summary for actual_evaluation turn")

    reindex_turns(output_turns)

    warmup_turn_count = sum(1 for t in output_turns if t.get("phase") == "warmup")
    normal_turn_count = sum(1 for t in output_turns if t.get("phase") == "normal")
    expected_normal = sum(1 + int(e.get("carryover_planned", 0)) for e in introduce_generations)

    return {
        "mac_task_uid": task_uid,
        "domain": delta_task.get("domain") or step2_task.get("domain"),
        "user_goal": delta_task.get("user_goal") or step2_task.get("user_goal"),
        "agent_name": step2_task.get("agent_name"),
        "g0_baseline": g0_graph_record(g0),
        "warmup_turn_count": warmup_turn_count,
        "normal_turn_count": normal_turn_count,
        "delta_turn_count": len(turns_delta),
        "expected_normal_turn_count": expected_normal,
        "evaluation_user_turn_count": 1 if has_eval else 0,
        "actual_user_turn_count": len(output_turns),
        "turns": output_turns,
        "generation": {
            "model": None if args.dry_run else args.model,
            "cache": dict(cache_counts),
            "warmup_planned": warmup_count,
            "introduce_generations": introduce_generations,
            "carryover_policy": CARRYOVER_POLICY,
            "carryover_eligible_actions": eligible_carryover_actions(
                domain=domain,
                visible_actions=visible_actions,
                action_pool=action_pool,
            ),
            "carryover_unique_count": len(task_carryover_seen),
            "warnings": warnings,
            "errors": errors,
        },
    }


def repair_task_history(
    history: dict[str, Any],
    *,
    step2_task: dict[str, Any],
    action_pool: ActionRequestPool,
    seed: int,
) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    task_uid = str(history.get("mac_task_uid") or step2_task.get("mac_task_uid") or "")
    eval_prompt = str(step2_task.get("mac_task_summary") or "").strip()
    _, eval_grounding = collect_eval_field_slots(eval_prompt, step2_task)
    domain = str(step2_task.get("domain") or "")
    visible_actions = visible_tool_actions(step2_task)
    g0 = collect_g0_baseline(step2_task)
    rng = random.Random(seed + int(sha256_text(task_uid)[:8], 16))
    task_carryover_seen = seed_carryover_seen_keys(eval_prompt=eval_prompt, output_turns=[])

    turns = history.get("turns") or []
    warmup_turns: list[dict[str, Any]] = []

    for turn in turns:
        if turn.get("kind") == "warmup":
            warmup_turns.append(
                {
                    "content": turn.get("content", ""),
                    "scope_expression": turn.get("scope_expression", ""),
                    "constraint_uids": turn.get("constraint_uids") or [],
                }
            )

    if warmup_turns:
        patched_warmup, warmup_uid_warnings = supplement_warmup_constraint_uids(warmup_turns, g0=g0)
        warnings.extend(warmup_uid_warnings)
        warmup_by_index = {index: item for index, item in enumerate(patched_warmup)}
        warmup_cursor = 0
        final_turns: list[dict[str, Any]] = []
        for turn in turns:
            if turn.get("kind") != "warmup":
                final_turns.append(copy.deepcopy(turn))
                continue
            patched = warmup_by_index.get(warmup_cursor)
            warmup_cursor += 1
            updated = copy.deepcopy(turn)
            if patched:
                updated["constraint_uids"] = patched.get("constraint_uids") or []
            final_turns.append(updated)
        turns = final_turns

    output_turns: list[dict[str, Any]] = []
    index = 0
    while index < len(turns):
        turn = turns[index]
        if turn.get("kind") != "introduce":
            output_turns.append(copy.deepcopy(turn))
            index += 1
            continue

        introduce_turn = copy.deepcopy(turn)
        output_turns.append(introduce_turn)
        introduce_index = len(output_turns) - 1
        index += 1

        carryover_block: list[dict[str, Any]] = []
        while index < len(turns) and turns[index].get("kind") == "carryover":
            carryover_block.append(turns[index])
            index += 1
        carryover_count = len(carryover_block)
        if carryover_count == 0:
            continue

        local_id = str(introduce_turn.get("source_delta_local_id") or "")
        forbidden = set()
        diff = introduce_turn.get("constraint_diff") or {}
        for item in (diff.get("added") or []) + (diff.get("removed") or []):
            text = str(item).strip()
            if text:
                forbidden.add(text)

        carryover_entries = generate_carryover_block_from_pool(
            domain=domain,
            visible_actions=visible_actions,
            action_pool=action_pool,
            eval_prompt=eval_prompt,
            eval_grounding=eval_grounding,
            forbidden=forbidden,
            carryover_count=carryover_count,
            rng=rng,
            seen_keys=task_carryover_seen,
        )
        if len(carryover_entries) < carryover_count:
            warnings.append(
                f"carryover repair under-filled for {local_id}: {len(carryover_entries)}/{carryover_count}"
            )
        for carry_index, old_turn in enumerate(carryover_block):
            entry = (
                carryover_entries[carry_index]
                if carry_index < len(carryover_entries)
                else {"content": old_turn.get("content", ""), "source_action": old_turn.get("source_action", "")}
            )
            content = str(entry.get("content") or "")
            source_action = str(entry.get("source_action") or old_turn.get("source_action") or "")
            updated = copy.deepcopy(old_turn)
            updated["content"] = content
            updated["source_introduce_turn_index"] = introduce_index
            if source_action:
                updated["source_action"] = source_action
                updated["scope_expression"] = (
                    f"Synthetic `{source_action}` customer request filler with randomized "
                    "field values; no constraint restatement."
                )
            output_turns.append(updated)

    reindex_turns(output_turns)
    repaired = copy.deepcopy(history)
    repaired["turns"] = output_turns
    repaired["actual_user_turn_count"] = len(output_turns)
    repaired["warmup_turn_count"] = sum(1 for item in output_turns if item.get("phase") == "warmup")
    repaired["normal_turn_count"] = sum(1 for item in output_turns if item.get("phase") == "normal")
    generation = dict(repaired.get("generation") or {})
    generation["carryover_policy"] = CARRYOVER_POLICY
    generation["carryover_eligible_actions"] = eligible_carryover_actions(
        domain=domain,
        visible_actions=visible_actions,
        action_pool=action_pool,
    )
    generation["carryover_unique_count"] = len(task_carryover_seen)
    generation["repair_warnings"] = warnings
    repaired["generation"] = generation
    return repaired, warnings


def process_carryover_only(
    job: TaskJob,
    existing_history: dict[str, Any],
    *,
    args: argparse.Namespace,
) -> dict[str, Any]:
    step2_task = job.step2_task
    task_uid = str(existing_history.get("mac_task_uid") or step2_task.get("mac_task_uid") or "")
    print(f"populating carryover {job.ordinal}/{job.total} task={task_uid}", flush=True)

    eval_prompt = str(step2_task.get("mac_task_summary") or "").strip()
    _, eval_grounding = collect_eval_field_slots(eval_prompt, step2_task)
    domain = str(step2_task.get("domain") or "")
    visible_actions = visible_tool_actions(step2_task)
    action_pool: ActionRequestPool = args.action_pool
    rng = random.Random(args.seed + int(sha256_text(task_uid)[:8], 16))
    task_carryover_seen = seed_carryover_seen_keys(eval_prompt=eval_prompt, output_turns=[])
    warnings: list[str] = []

    output_turns: list[dict[str, Any]] = []
    introduce_generations: list[dict[str, Any]] = []
    index = 0
    source_turns = existing_history.get("turns") or []
    while index < len(source_turns):
        turn = source_turns[index]
        if not isinstance(turn, dict):
            index += 1
            continue
        kind = str(turn.get("kind") or "")
        if kind == "carryover":
            index += 1
            continue
        output_turns.append(copy.deepcopy(turn))
        if kind != "introduce":
            index += 1
            continue

        introduce_turn = output_turns[-1]
        introduce_index = len(output_turns) - 1
        local_id = str(introduce_turn.get("source_delta_local_id") or "")
        index += 1

        carryover_count = plan_carryover_count(rng, args)
        introduce_generations.append(
            {
                "source_delta_local_id": local_id,
                "carryover_planned": carryover_count,
            }
        )

        forbidden: set[str] = set()
        diff = introduce_turn.get("constraint_diff") or {}
        for item in (diff.get("added") or []) + (diff.get("removed") or []):
            text = str(item).strip()
            if text:
                forbidden.add(text)

        carryover_entries = generate_carryover_block_from_pool(
            domain=domain,
            visible_actions=visible_actions,
            action_pool=action_pool,
            eval_prompt=eval_prompt,
            eval_grounding=eval_grounding,
            forbidden=forbidden,
            carryover_count=carryover_count,
            rng=rng,
            seen_keys=task_carryover_seen,
        )
        if len(carryover_entries) < carryover_count:
            warnings.append(
                f"carryover under-filled for {local_id}: {len(carryover_entries)}/{carryover_count} "
                f"(eligible_actions={len(eligible_carryover_actions(domain=domain, visible_actions=visible_actions, action_pool=action_pool))})"
            )
        for entry in carryover_entries:
            content = str(entry.get("content") or "")
            source_action = str(entry.get("source_action") or "")
            output_turns.append(
                {
                    "role": "user",
                    "phase": "normal",
                    "kind": "carryover",
                    "content": content,
                    "scope_expression": (
                        f"Synthetic `{source_action}` customer request filler with randomized "
                        "field values; no constraint restatement."
                    ),
                    "mentions_constraint": False,
                    "source_introduce_turn_index": introduce_index,
                    "source_delta_local_id": local_id,
                    "source_action": source_action,
                }
            )

    reindex_turns(output_turns)
    has_eval = any(turn.get("kind") == "actual_evaluation" for turn in output_turns)
    if not has_eval:
        append_actual_evaluation_turn(eval_prompt=eval_prompt, output_turns=output_turns)
        reindex_turns(output_turns)

    generation = dict(existing_history.get("generation") or {})
    generation["carryover_policy"] = CARRYOVER_POLICY
    generation["carryover_eligible_actions"] = eligible_carryover_actions(
        domain=domain,
        visible_actions=visible_actions,
        action_pool=action_pool,
    )
    generation["carryover_unique_count"] = len(task_carryover_seen)
    generation["introduce_generations"] = introduce_generations
    if warnings:
        prior = list(generation.get("warnings") or [])
        generation["warnings"] = prior + warnings

    warmup_turn_count = sum(1 for t in output_turns if t.get("phase") == "warmup")
    normal_turn_count = sum(1 for t in output_turns if t.get("phase") == "normal")
    expected_normal = sum(1 + int(e.get("carryover_planned", 0)) for e in introduce_generations)

    return {
        **copy.deepcopy(existing_history),
        "mac_task_uid": task_uid,
        "warmup_turn_count": warmup_turn_count,
        "normal_turn_count": normal_turn_count,
        "expected_normal_turn_count": expected_normal,
        "evaluation_user_turn_count": 1 if has_eval or eval_prompt else 0,
        "actual_user_turn_count": len(output_turns),
        "turns": output_turns,
        "generation": generation,
    }


def repair_output_histories(
    histories: list[dict[str, Any]],
    *,
    step2_by_uid: dict[str, dict[str, Any]],
    action_pool: ActionRequestPool,
    seed: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    repaired_histories: list[dict[str, Any]] = []
    all_warnings: list[dict[str, Any]] = []
    warmup_unmatched: list[dict[str, Any]] = []

    for history in histories:
        uid = str(history.get("mac_task_uid") or "")
        step2_task = step2_by_uid.get(uid)
        if not step2_task:
            repaired_histories.append(history)
            all_warnings.append({"mac_task_uid": uid, "warning": "missing step2 task"})
            continue
        repaired, warnings = repair_task_history(
            history,
            step2_task=step2_task,
            action_pool=action_pool,
            seed=seed,
        )
        repaired_histories.append(repaired)
        if warnings:
            all_warnings.append({"mac_task_uid": uid, "warnings": warnings})
        for warning in warnings:
            if warning.startswith("warmup uid unmatched:"):
                warmup_unmatched.append({"mac_task_uid": uid, "detail": warning})

    report = {
        "task_count": len(repaired_histories),
        "tasks_with_warnings": len(all_warnings),
        "warmup_unmatched_count": len(warmup_unmatched),
        "warmup_unmatched": warmup_unmatched,
        "warnings": all_warnings[:100],
    }
    return repaired_histories, report


def summarize_histories(histories: list[dict[str, Any]]) -> dict[str, Any]:
    failed = [h.get("mac_task_uid") for h in histories if (h.get("generation") or {}).get("errors")]
    return {
        "task_count": len(histories),
        "total_user_turns": sum(int(h.get("actual_user_turn_count") or 0) for h in histories),
        "total_warmup_turns": sum(int(h.get("warmup_turn_count") or 0) for h in histories),
        "total_normal_turns": sum(int(h.get("normal_turn_count") or 0) for h in histories),
        "total_introduce_turns": sum(int(h.get("delta_turn_count") or 0) for h in histories),
        "failed_tasks": len(failed),
        "failed_task_uids": failed[:50],
        "history_length_distribution": dict(
            Counter(str(h.get("actual_user_turn_count")) for h in histories)
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delta-input", type=Path, default=DEFAULT_DELTA)
    parser.add_argument("--step2-input", type=Path, default=DEFAULT_STEP2)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--model", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--sleep", type=float, default=1.0)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--only-task", action="append", default=[])
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument("--warmup-min", type=int, default=3)
    parser.add_argument("--warmup-max", type=int, default=4)
    parser.add_argument("--carryover-min", type=int, default=DEFAULT_CARRYOVER_MIN)
    parser.add_argument("--carryover-max", type=int, default=DEFAULT_CARRYOVER_MAX)
    parser.add_argument("--carryover-mean", type=float, default=DEFAULT_CARRYOVER_MEAN)
    parser.add_argument("--carryover-std", type=float, default=DEFAULT_CARRYOVER_STD)
    parser.add_argument(
        "--pool-source",
        type=Path,
        default=DEFAULT_POOL_SOURCE,
        help="SOPBench domain task JSON directory used to build action request pools.",
    )
    parser.add_argument(
        "--skip-carryover",
        action="store_true",
        help="Generate warmup + introduce turns only; defer carryover filler to a later pass.",
    )
    parser.add_argument(
        "--carryover-only",
        action="store_true",
        help="Keep existing warmup/introduce turns and only (re)generate carryover blocks.",
    )
    parser.add_argument(
        "--carryover-input",
        type=Path,
        default=None,
        help="Existing step5 JSON to read when --carryover-only is set (defaults to --output).",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-placeholder", action="store_true")
    parser.add_argument("--save-cache-every", type=int, default=10)
    parser.add_argument("--merge-into", type=Path, default=None)
    parser.add_argument(
        "--repair-output",
        action="store_true",
        help="Repair an existing step5 output in place: backfill warmup constraint_uids and regenerate carryover turns.",
    )
    parser.add_argument(
        "--repair-report",
        type=Path,
        default=Path("bench/MAC/sopbench/mid_data/eval_step5_repair_report.json"),
    )
    return parser.parse_args()


def selected_delta_tasks(
    tasks: list[dict[str, Any]],
    *,
    offset: int,
    limit: int | None,
    only_task: set[str],
) -> list[dict[str, Any]]:
    if only_task:
        tasks = [t for t in tasks if str(t.get("mac_task_uid") or "") in only_task]
    if offset:
        tasks = tasks[offset:]
    if limit is not None:
        tasks = tasks[: max(0, limit)]
    return tasks


def merge_histories(existing: list[dict[str, Any]], updates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_uid = {
        str(item.get("mac_task_uid")): item
        for item in updates
        if isinstance(item, dict) and item.get("mac_task_uid")
    }
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in existing:
        uid = str(item.get("mac_task_uid") or "")
        if uid in by_uid:
            merged.append(by_uid[uid])
            seen.add(uid)
        else:
            merged.append(item)
    for uid, item in by_uid.items():
        if uid not in seen:
            merged.append(item)
    return merged


def main() -> int:
    args = parse_args()
    if args.skip_carryover and args.carryover_only:
        raise ValueError("Use only one of --skip-carryover or --carryover-only")
    load_env(args.env_file)
    resolve_llm_config(args)

    action_pool = ActionRequestPool.from_sopbench_data(args.pool_source)
    args.action_pool = action_pool

    step2_by_uid = index_step2_tasks(load_json(args.step2_input))

    if args.carryover_only:
        carryover_input = args.carryover_input or args.output
        payload = load_json(carryover_input)
        existing_histories = payload.get("task_histories") if isinstance(payload, dict) else None
        if not isinstance(existing_histories, list):
            raise ValueError(f"--carryover-only requires task_histories[] in {carryover_input}")
        existing_by_uid = {
            str(item.get("mac_task_uid")): item
            for item in existing_histories
            if isinstance(item, dict) and item.get("mac_task_uid")
        }
        delta_payload = load_json(args.delta_input)
        delta_tasks = delta_payload.get("tasks") if isinstance(delta_payload, dict) else None
        if not isinstance(delta_tasks, list):
            raise ValueError("delta input must contain tasks[]")
        only_task = {str(uid) for uid in args.only_task}
        selected = selected_delta_tasks(
            delta_tasks,
            offset=args.offset,
            limit=args.limit,
            only_task=only_task,
        )
        jobs = [
            TaskJob(
                ordinal=index,
                total=len(selected),
                delta_task=delta_task,
                step2_task=step2_by_uid[str(delta_task.get("mac_task_uid") or "")],
            )
            for index, delta_task in enumerate(selected, start=1)
            if step2_by_uid.get(str(delta_task.get("mac_task_uid") or ""))
            and existing_by_uid.get(str(delta_task.get("mac_task_uid") or ""))
        ]
        if not jobs:
            raise ValueError("no tasks matched delta + step2 + carryover-input histories")

        results: list[dict[str, Any]] = []
        if args.workers <= 1:
            for job in jobs:
                existing = existing_by_uid[str(job.step2_task.get("mac_task_uid") or "")]
                results.append(process_carryover_only(job, existing, args=args))
        else:
            with ThreadPoolExecutor(max_workers=args.workers) as executor:
                futures = [
                    executor.submit(
                        process_carryover_only,
                        job,
                        existing_by_uid[str(job.step2_task.get("mac_task_uid") or "")],
                        args=args,
                    )
                    for job in jobs
                ]
                for future in as_completed(futures):
                    results.append(future.result())

        results.sort(key=lambda item: str(item.get("mac_task_uid") or ""))
        histories = merge_histories(existing_histories, results)
        payload = {
            "schema_version": "MACConstructStep5SOPUserTurnsV2",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "sources": {
                "delta": str(resolve_path(args.delta_input)),
                "step2": str(resolve_path(args.step2_input)),
                "carryover_input": str(resolve_path(carryover_input)),
            },
            "generation_config": {
                "warmup": "existing",
                "introduce": "existing",
                "carryover": "heuristic_action_pool",
                "carryover_range": [args.carryover_min, args.carryover_max],
                "carryover_distribution": {
                    "type": "truncated_normal",
                    "mean": args.carryover_mean,
                    "std": args.carryover_std,
                },
                "carryover_pool_source": str(resolve_path(args.pool_source)),
                "carryover_pool_summary": action_pool.summary(),
                "seed": args.seed,
            },
            "summary": summarize_histories(histories),
            "task_histories": histories,
        }
        write_json(args.output, payload)
        meta_path = resolve_path(args.output).with_suffix(resolve_path(args.output).suffix + ".meta.json")
        write_json(meta_path, {"summary": payload["summary"], "tasks_output": str(resolve_path(args.output))})
        print(
            f"wrote carryover for {len(results)} task histor(ies) to {resolve_path(args.output)}; "
            f"total_user_turns={payload['summary']['total_user_turns']}"
        )
        return 0

    if args.repair_output:
        payload = load_json(args.output)
        histories = payload.get("task_histories") if isinstance(payload, dict) else None
        if not isinstance(histories, list):
            raise ValueError("repair output requires task_histories[]")
        repaired_histories, report = repair_output_histories(
            histories,
            step2_by_uid=step2_by_uid,
            action_pool=action_pool,
            seed=args.seed,
        )
        payload["task_histories"] = repaired_histories
        payload["summary"] = summarize_histories(repaired_histories)
        payload["repaired_at"] = datetime.now(timezone.utc).isoformat()
        write_json(args.output, payload)
        write_json(args.repair_report, report)
        print(
            f"repaired {report['task_count']} task histor(ies) -> {resolve_path(args.output)}; "
            f"warmup_unmatched={report['warmup_unmatched_count']}; "
            f"report={resolve_path(args.repair_report)}",
            flush=True,
        )
        return 0

    delta_payload = load_json(args.delta_input)
    delta_tasks = delta_payload.get("tasks") if isinstance(delta_payload, dict) else None
    if not isinstance(delta_tasks, list):
        raise ValueError("delta input must contain tasks[]")

    step2_by_uid = index_step2_tasks(load_json(args.step2_input))
    only_task = {str(uid) for uid in args.only_task}
    selected = selected_delta_tasks(
        delta_tasks,
        offset=args.offset,
        limit=args.limit,
        only_task=only_task,
    )

    jobs = [
        TaskJob(
            ordinal=index,
            total=len(selected),
            delta_task=delta_task,
            step2_task=step2_by_uid[str(delta_task.get("mac_task_uid") or "")],
        )
        for index, delta_task in enumerate(selected, start=1)
        if step2_by_uid.get(str(delta_task.get("mac_task_uid") or ""))
    ]
    missing = {str(t.get("mac_task_uid")) for t in selected} - {j.step2_task.get("mac_task_uid") for j in jobs}
    if missing:
        raise ValueError(f"missing step2 tasks: {sorted(missing)[:5]}")

    try:
        cache = load_cache(args.cache)
    except (FileNotFoundError, ValueError):
        cache = empty_cache()
    cache_lock = threading.Lock()
    results: list[dict[str, Any]] = []

    if args.workers <= 1:
        for completed, job in enumerate(jobs, start=1):
            results.append(process_task(job, args=args, cache=cache, cache_lock=cache_lock))
            if args.save_cache_every and completed % args.save_cache_every == 0:
                write_json(args.cache, cache)
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = [
                executor.submit(process_task, job, args=args, cache=cache, cache_lock=cache_lock)
                for job in jobs
            ]
            for future in as_completed(futures):
                results.append(future.result())

    write_json(args.cache, cache)
    results.sort(key=lambda item: str(item.get("mac_task_uid") or ""))

    existing: list[dict[str, Any]] = []
    if args.merge_into:
        prior = load_json(args.merge_into)
        existing = [item for item in (prior.get("task_histories") or []) if isinstance(item, dict)]
    histories = merge_histories(existing, results) if existing else results

    payload = {
        "schema_version": "MACConstructStep5SOPUserTurnsV2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": {
            "delta": str(resolve_path(args.delta_input)),
            "step2": str(resolve_path(args.step2_input)),
        },
        "generation_config": {
            "warmup": "llm",
            "warmup_range": [args.warmup_min, args.warmup_max],
            "introduce": "llm",
            "carryover": "skipped" if args.skip_carryover else "heuristic_action_pool",
            "carryover_range": [args.carryover_min, args.carryover_max],
            "carryover_distribution": {
                "type": "truncated_normal",
                "mean": args.carryover_mean,
                "std": args.carryover_std,
            },
            "carryover_pool_source": str(resolve_path(args.pool_source)),
            "carryover_pool_summary": action_pool.summary(),
            "model": None if args.dry_run else args.model,
            "dry_run": args.dry_run,
            "seed": args.seed,
        },
        "summary": summarize_histories(histories),
        "task_histories": histories,
    }
    write_json(args.output, payload)
    meta_path = resolve_path(args.output).with_suffix(resolve_path(args.output).suffix + ".meta.json")
    write_json(meta_path, {"summary": payload["summary"], "tasks_output": str(resolve_path(args.output))})
    print(
        f"wrote {len(histories)} task histor(ies) to {resolve_path(args.output)}; "
        f"total_user_turns={payload['summary']['total_user_turns']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
