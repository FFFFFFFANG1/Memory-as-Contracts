#!/usr/bin/env python3
"""Audit and patch exception introduce turns missing clear occasion boundaries.

Joins step-3 constraint metadata (trigger_condition.occasion) with step-4 task
histories, flags introduce turns whose content does not clearly state when the
exception applies, and optionally inserts boundary phrases into the turn text.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_STEP3 = Path("bench/MAC/cctu/mid_data/eval_step3_base.json")
DEFAULT_STEP4 = Path("bench/MAC/cctu/mid_data/eval_step4_task_histories.json")

STOPWORDS = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "but",
    "in",
    "on",
    "at",
    "to",
    "for",
    "of",
    "with",
    "by",
    "from",
    "as",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "this",
    "that",
    "these",
    "those",
    "when",
    "while",
    "during",
    "only",
    "any",
    "all",
    "must",
    "not",
    "into",
    "about",
    "under",
    "across",
    "within",
    "after",
    "before",
    "than",
    "more",
    "most",
    "other",
    "some",
    "such",
    "each",
    "every",
    "both",
    "between",
    "through",
    "where",
    "which",
    "what",
    "who",
    "how",
    "has",
    "have",
    "had",
    "does",
    "did",
    "will",
    "would",
    "should",
    "could",
    "can",
    "may",
    "might",
    "also",
    "just",
    "need",
    "your",
    "you",
    "our",
    "their",
    "its",
    "his",
    "her",
    "they",
    "them",
    "we",
    "me",
    "my",
    "i",
}

CCTU_PREFIX_RE = re.compile(
    r"^(?:Please call given tools to answer the question\. Please note that all your information must be obtained by calling tools(?: and not by answering the question directly)?\.(?:\s*If the call fails, you need to try to correct it and continue until you arrive at an answer\.?)?\s*)+",
    re.IGNORECASE,
)

BOUNDARY_MARKERS = (
    r"\bfor this (?:phase|project|run|request|comparison|audit|report|lookup|query|task|section|workstream|chat|session)\b",
    r"\bwhen (?:we|you|i|the agent|you're|i'm|we're)\b",
    r"\bwhile (?:we|you|i|we're|you're)\b",
    r"\bbefore (?:we|you|i|you issue|any)\b",
    r"\bduring (?:the|this)\b",
    r"\bfor .{5,120} only\b",
    r"\bfrom now on\b",
    r"\bas a (?:standing|general|hard) rule\b",
    r"\bunder (?:the|these) (?:phase|project) rules\b",
    r"\bfor the current\b",
    r"\bwhen resolving\b",
    r"\bwhen (?:producing|delivering|formatting|auditing|comparing|handling|reporting|preparing|mapping|cross-checking|exporting|delivering)\b",
    r"\bonly when\b",
    r"\bspecifically when\b",
    r"\bflagging (?:this|these)\b",
    r"\btreat that as a (?:standing|blanket|hard) rule\b",
    r"\b(?:one )?standing ground rule\b",
    r"\bquick (?:policy|ground|formatting|procedural|tooling|setup|housekeeping) note\b",
)

# Occasion themes that are often paraphrased without sharing tokens.
PARAPHRASE_HINTS: dict[str, tuple[str, ...]] = {
    "election outcome": ("election", "vote", "runoff", "candidate", "turnout"),
    "auditing electoral": ("audit", "election", "cross-validate", "tally"),
    "consecutive tool failures": ("three times in a row", "three consecutive", "failure-log", "failure log"),
    "machine-readable json": ("json object", "json envelope", "strict json", "keys 'answer'"),
    "public release": ("public release", "flagging this", "disclaimer paragraph"),
    "source provenance": ("provenance", "citation", "where the fact came from", "defend these answers"),
    "single-hop": ("single-hop", "single fact", "quickanswer", "one specialized tool", "fast single"),
    "first turn after task intake": ("tool inventory", "enumerate every tool", "before issuing any tool call"),
    "first reasoning turn": ("initial_parallel", "opening turn", "first turn"),
    "cross-checking tool outputs": ("cross-check", "cross-verify", "cross-validate", "evidence verification"),
    "exporting traces": ("audit log", "audit trail", "json audit", "tool invocation"),
    "pricing queries": ("price", "pricing", "retail price", "commodity"),
    "peer review": ("peer-review", "latex manuscript", "apa style", "musicology journal"),
    "quick-fact lookup": ("single declarative sentence", "quickfacts", "compress the entire answer"),
    "initial scoping": ("initialscoping", "initial scoping", "scoping phase"),
    "highland folklore": ("highland", "exclude any coastal", "maritime regions"),
    "apollo-era": ("apollo", "space-related", "space_mission"),
    "biography summaries": ("biography", "biographical", "briefing"),
    "attributing bridges": ("bridge attribution", "designer identified", "infrastructure_engineer"),
    "conflicting waterfall": ("waterfall height", "disclaimer", "vary by source"),
    "speed-optimized": ("rapid discovery", "maximum throughput", "at most 3 interaction turns"),
    "disambiguation": ("disambiguation", "similarly named", "cross-check it with both"),
    "post-computation verification": ("citation hardening", "re-verified", "second time"),
    "laureate-centered": ("nobel_laureate_finder", "nobel laureate"),
    "regulator-facing": ("dual-source", "compliance", "cross-check every numerical"),
    "wellness participant": ("wellness", "consent", "omit any numeric bmi"),
    "casualty enumeration": ("casualty", "military_event_search"),
    "healthcare merger": ("merger", "acquisition", "healthcare"),
    "philanthropic disbursements": ("philanthropy", "donor", "fy2023", "disbursement"),
    "delivering the daily stand-up": ("stand-up", "morning operations", "verbal stand-up"),
    "wingspan-related lookup": ("wingspan", "gate clearance", "infrastructure_info_retriever"),
    "fleet evaluation": ("regionaljet", "regional jet", "fleet eval"),
    "anatomy-related": ("anatomy", "anatomy_information_provider"),
    "distance summaries": ("european rail", "convert all reported distances to kilometers"),
    "infrastructure assets": ("infrastructureauditing", "yaml asset inventory"),
    "comparative anatomy": ("dental comparison", "cross-species"),
    "aviation-related historical": ("aviation", "airport_info_retriever", "chronology"),
    "heritage landmarks": ("heritage audit", "historical_landmark_data_retriever"),
    "compliance review pass": ("verification trace", "terrain profiling", "call-by-call"),
    "diagnostic runs": ("single-hop verification drill", "exactly one tool call"),
    "multi-hop interdisciplinary": ("multi-hop", "cross-domain knowledge synthesis"),
    "travel and vendor logistics": ("tulip festival", "festival-anchored", "event_locator"),
    "beach features": ("protected_area_info", "island feature", "protected zones"),
    "transport and sports trivia": ("transportandsportstrivia", "airport_info_retriever", "sports_event_info"),
    "aviation safety records": ("aviation safety", "aviation_incident_database"),
    "geographic terms at intake": ("intakeclarification", "canonical names", "normalize"),
    "retrieval tool invocation": ("before any and every retrieval", "every single time you're about to use a retrieval"),
    "species-versus-species": ("comparative genomics", "comprehensive_biological_info_retriever"),
    "delivering the single-fact answer": ("concise-answer-delivery", "at most 200 characters"),
    "compound historical-date": ("historical milestones sum", "date retrieval phase"),
    "mapping intangible heritage": ("national symbol", "national_symbol_finder"),
    "geological provenance": ("geological", "stone_origin_locator"),
    "award-winning chef": ("chef finding", "landmarkcrosscheck", "award_winner_finder"),
    "alpine geographer": ("alpine", "geographer_identifier", "cartographic index"),
    "deep research phase": ("deepresearchphase", "cross-verify every retrieved fact", "two independent tool"),
    "any factual research": ("historicalfactlookup", "twenty tool calls"),
    "standard multi-hop": ("multi-hop", "twenty-five tool calls"),
    "user-facing answer delivery": ("under 280 characters", "final country or traditional music genre name"),
    "manuscript for external": ("peer_review_preparation", "apa style"),
    "musicology journal pipeline": ("musicologyjournalsubmission", "latex manuscript"),
    "geographic scoping rule": ("highland districts", "exclude any coastal"),
    "operating inside the deep research": ("deepresearchphase", "source-by-source comparison"),
    "linking facts from more than one source": ("multi-hop cross-referencing", "chain at least two distinct"),
    "complex multi-hop research": ("multi-step plan", "at least four interaction turns"),
    "question requires linking facts": ("chain at least two distinct retrieval tools", "intermediate evidence trail"),
    "reporting on apollo-era": ("apollo mission", "space-related fact"),
    "drafting a biographical briefing": ("polymath biography", "polymath_identifier"),
    "kickoff stylistic directive": ("stylistic preference", "kickoff briefing", "single-sentence reply"),
}


# Hand-tuned boundary phrases for introduce turns that still read too open-ended.
MANUAL_BOUNDARY_OVERRIDES: dict[str, str] = {
    "mac-cctu-t-00018-c0005-g7": (
        "For this multi-source lookup only, when the question requires linking facts from more than one source, "
    ),
    "mac-cctu-t-00038-c0002-g4": (
        "For the Military Conflict Casualty Project only, and only when handling casualty enumeration for armed conflicts, "
    ),
    "mac-cctu-t-00044-c0001-g3": (
        "For the HistoricalFactLookup project during QuickAnswerPhase only, and only when the user asks a single-hop factual question answerable from one specialized tool, "
    ),
    "mac-cctu-t-00044-c0003-g4": (
        "For the HistoricalFactLookup project during DeepResearchPhase only, and only when operating inside the deep research phase that requires corroboration, "
    ),
    "mac-cctu-t-00055-c0005-g7": (
        "From now on in this chat, and only after three or more consecutive tool failures in the current trajectory, "
    ),
    "mac-cctu-t-00061-c0003-g6": (
        "For the AwardWinnerProfileBuild project during LandmarkCrossCheck only, and only for this award-winning chef profile validation pass, "
    ),
    "mac-cctu-t-00070-c0006-g4": (
        "For the Philanthropy Impact Review 2023 project during Donor Financial Audit only, and only when auditing philanthropic disbursements for the FY2023 cycle, "
    ),
    "mac-cctu-t-00072-c0004-g4": (
        "For the CulturalBioInterdisciplinaryReport project during initial_parallel_dispatch only, and only on the first reasoning turn after task intake, "
    ),
    "mac-cctu-t-00075-c0002-g5": (
        "For the HighlandFolkloreSurvey project only, and only under the geographic scoping rule for the highland folklore study, "
    ),
    "mac-cctu-t-00082-c0003-g3": (
        "For the MultiHopGeoFactResolution project during EvidenceVerification only, and only when cross-checking tool outputs against each other, "
    ),
    "mac-cctu-t-00082-c0003-g4": (
        "For the MultiHopGeoFactResolution project during AuditTrailExport only, and only when exporting traces after a task is closed, "
    ),
    "mac-cctu-t-00086-c0001-g5": (
        "From now on in this chat, and only when I explicitly request a machine-readable JSON envelope, "
    ),
    "mac-cctu-t-00091-c0001-g3": (
        "For the GeoFactsQA project during concise-answer-delivery only, and only when delivering the single-fact answer to the user's multi-hop geography query, "
    ),
    "mac-cctu-t-00109-c0002-g2": (
        "For the Primate Comparative Genomics project only, and only for any species-versus-species comparison handled inside this project, "
    ),
    "mac-cctu-t-00118-c0002-g5": (
        "For the GlobalTransportAndSportsTriviaAudit project only, and only during transport and sports trivia auditing, "
    ),
    "mac-cctu-t-00127-c0007-g4": (
        "For the WideBody-Spec-Comparison project during morning operations stand-up reporting only, and only when delivering the daily stand-up summary, "
    ),
    "mac-cctu-t-00132-c0003-c1": (
        "For the HumanAnatomyFactLookup project only, and only for any anatomy-related fact resolution inside the project, "
    ),
    "mac-cctu-t-00148-c0006-g6": (
        "For the AviationMilestones-Chronology project only, and only when validating aviation-related historical event dates, "
    ),
    "mac-cctu-t-00156-c0001-g3": (
        "For the Polymath Biography Briefings project only, and only when producing public-facing biography summaries, "
    ),
    "mac-cctu-t-00165-c0001-g2": (
        "For the Cross-Domain Knowledge Synthesis Initiative only, and only for the standard end-to-end resolution of a multi-hop interdisciplinary query, "
    ),
    "mac-cctu-t-00172-c0002-g7": (
        "For the Cultural Cross-Reference Synthesis project during Music Branch Disambiguation only, and only when resolving ambiguity between two bands with similar names, "
    ),
    "mac-cctu-t-00186-c0003-g5": (
        "For the Nobel Laureate Atlas project only, and only for any laureate-centered multi-hop resolution, "
    ),
}


@dataclass(frozen=True)
class AuditFinding:
    task_uid: str
    local_id: str
    occasion: str
    project: str | None
    phase: str | None
    scope: str | None
    introduce_mode: str | None
    coverage: float
    status: str
    reason: str
    content: str
    suggested_boundary: str | None = None


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def load_json(path: Path) -> Any:
    return json.loads(resolve_path(path).read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    target = resolve_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")


def tokenize(text: str) -> list[str]:
    return [
        word.lower()
        for word in re.findall(r"[A-Za-z0-9']+", text or "")
        if len(word) > 2 and word.lower() not in STOPWORDS
    ]


def occasion_token_coverage(content: str, occasion: str) -> float:
    occasion_tokens = tokenize(occasion)
    if not occasion_tokens:
        return 1.0
    content_tokens = set(tokenize(content))
    hits = sum(1 for token in occasion_tokens if token in content_tokens)
    return hits / len(occasion_tokens)


def has_boundary_marker(content: str) -> bool:
    lowered = content.lower()
    return any(re.search(pattern, lowered) for pattern in BOUNDARY_MARKERS)


def paraphrase_matches(content: str, occasion: str) -> bool:
    lowered = content.lower()
    occasion_lower = occasion.lower()
    for theme, hints in PARAPHRASE_HINTS.items():
        if theme in occasion_lower and any(hint in lowered for hint in hints):
            return True
    return False


def assess_boundary_clarity(
    *,
    content: str,
    occasion: str,
    project: str | None,
    phase: str | None,
    coverage: float,
) -> tuple[str, str]:
    if coverage >= 0.35:
        return "clear", "occasion keywords present in introduce turn"

    lowered = content.lower()
    occasion_lower = occasion.lower()

    if occasion_lower in lowered:
        return "clear", "occasion text appears verbatim in introduce turn"

    if "only when" in lowered or "specifically when" in lowered:
        if coverage >= 0.2:
            return "clear", "explicit only-when boundary with partial occasion overlap"

    if paraphrase_matches(content, occasion) and has_boundary_marker(content):
        return "clear", "occasion paraphrased with scoped boundary wording"

    if has_boundary_marker(content):
        if project and project.lower() in lowered and phase and phase.lower() in lowered:
            if coverage >= 0.25:
                return "clear", "project/phase boundary with moderate occasion overlap"
        if coverage >= 0.28 and (
            (project and project.lower() in lowered) or (phase and phase.lower() in lowered)
        ):
            return "clear", "scoped boundary with moderate occasion overlap"

    return "needs_fix", "occasion or effective timing not clearly stated"


def build_boundary_phrase(
    *,
    local_id: str,
    project: str | None,
    phase: str | None,
    occasion: str,
    scope: str | None,
) -> str:
    override = MANUAL_BOUNDARY_OVERRIDES.get(local_id)
    if override:
        return override

    occasion_text = occasion.strip().rstrip(".")
    if scope == "global" or (not project and not phase):
        return (
            f"From now on in this chat, and only when {occasion_text}, "
            "please follow this rule: "
        )
    if project and phase:
        return (
            f"For the {project} project during the {phase} phase only, "
            f"and specifically when {occasion_text}, "
        )
    if project:
        return (
            f"For the {project} project only, and only when {occasion_text}, "
        )
    if phase:
        return (
            f"During the {phase} phase only, and specifically when {occasion_text}, "
        )
    return f"Only when {occasion_text}, the following applies: "


def boundary_already_present(content: str, boundary_phrase: str, occasion: str) -> bool:
    lowered = content.lower()
    if boundary_phrase.lower() in lowered:
        return True
    occasion_text = occasion.strip().rstrip(".").lower()
    if occasion_text and occasion_text in lowered:
        return True
    return False


def insert_boundary_phrase(content: str, boundary_phrase: str, *, occasion: str) -> str:
    text = content.strip()
    if not text:
        return boundary_phrase.strip()

    if boundary_already_present(text, boundary_phrase, occasion):
        return text

    prefix_match = CCTU_PREFIX_RE.match(text)
    if prefix_match:
        prefix = prefix_match.group(0)
        body = text[len(prefix) :].lstrip()
        return f"{prefix}{boundary_phrase}{body}"

    return f"{boundary_phrase}{text}"


def index_step3_items(step3: dict[str, Any]) -> dict[str, dict[str, Any]]:
    items: dict[str, dict[str, Any]] = {}
    for task in step3.get("task_sequences", []):
        for item in task.get("constraint_sequence", []):
            local_id = item.get("local_id")
            if isinstance(local_id, str):
                items[local_id] = item
    return items


def audit_exception_introduces(
    step3: dict[str, Any],
    step4: dict[str, Any],
) -> list[AuditFinding]:
    items = index_step3_items(step3)
    findings: list[AuditFinding] = []

    for history in step4.get("task_histories", []):
        task_uid = history.get("task_uid")
        for turn in history.get("turns", []):
            if turn.get("source_anchor_role") != "exception":
                continue
            if turn.get("kind") != "introduce":
                continue

            local_id = turn.get("source_constraint_local_id")
            if not isinstance(local_id, str):
                continue
            item = items.get(local_id)
            if not item:
                continue

            trigger = item.get("trigger_condition") or {}
            occasion = trigger.get("occasion")
            if not isinstance(occasion, str) or not occasion.strip():
                continue

            content = str(turn.get("content") or "")
            project = trigger.get("project") if isinstance(trigger.get("project"), str) else None
            phase = trigger.get("phase") if isinstance(trigger.get("phase"), str) else None
            coverage = occasion_token_coverage(content, occasion)
            if coverage >= 0.35:
                continue

            status, reason = assess_boundary_clarity(
                content=content,
                occasion=occasion.strip(),
                project=project,
                phase=phase,
                coverage=coverage,
            )
            suggested = None
            if status == "needs_fix":
                suggested = build_boundary_phrase(
                    local_id=local_id,
                    project=project,
                    phase=phase,
                    occasion=occasion.strip(),
                    scope=turn.get("scope") if isinstance(turn.get("scope"), str) else None,
                )

            findings.append(
                AuditFinding(
                    task_uid=str(task_uid),
                    local_id=local_id,
                    occasion=occasion.strip(),
                    project=project,
                    phase=phase,
                    scope=turn.get("scope") if isinstance(turn.get("scope"), str) else None,
                    introduce_mode=turn.get("introduce_mode") if isinstance(turn.get("introduce_mode"), str) else None,
                    coverage=round(coverage, 3),
                    status=status,
                    reason=reason,
                    content=content,
                    suggested_boundary=suggested,
                )
            )

    return findings


def apply_fixes(
    step4: dict[str, Any],
    findings: list[AuditFinding],
    *,
    dry_run: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    fix_by_local_id = {
        finding.local_id: finding
        for finding in findings
        if finding.status == "needs_fix" and finding.suggested_boundary
    }
    applied: list[dict[str, Any]] = []

    for history in step4.get("task_histories", []):
        for turn in history.get("turns", []):
            if turn.get("kind") != "introduce":
                continue
            local_id = turn.get("source_constraint_local_id")
            finding = fix_by_local_id.get(local_id)
            if not finding:
                continue

            original = str(turn.get("content") or "")
            patched = insert_boundary_phrase(
                original,
                finding.suggested_boundary or "",
                occasion=finding.occasion,
            )
            if patched == original:
                continue

            applied.append(
                {
                    "task_uid": history.get("task_uid"),
                    "local_id": local_id,
                    "occasion": finding.occasion,
                    "boundary_phrase": finding.suggested_boundary,
                    "before": original,
                    "after": patched,
                }
            )
            if not dry_run:
                turn["content"] = patched
                scope_expression = str(turn.get("scope_expression") or "").strip()
                suffix = f"Boundary phrase added for occasion: {finding.occasion}."
                turn["scope_expression"] = f"{scope_expression} {suffix}".strip()

    return step4, applied


def findings_to_json(findings: list[AuditFinding]) -> list[dict[str, Any]]:
    return [
        {
            "task_uid": finding.task_uid,
            "local_id": finding.local_id,
            "occasion": finding.occasion,
            "project": finding.project,
            "phase": finding.phase,
            "scope": finding.scope,
            "introduce_mode": finding.introduce_mode,
            "coverage": finding.coverage,
            "status": finding.status,
            "reason": finding.reason,
            "suggested_boundary": finding.suggested_boundary,
            "content_preview": finding.content[:500],
        }
        for finding in findings
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--step3", type=Path, default=DEFAULT_STEP3)
    parser.add_argument("--step4", type=Path, default=DEFAULT_STEP4)
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("bench/MAC/cctu/mid_data/eval_step4_exception_occasion_audit.json"),
        help="Write audit findings JSON here.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Patch step-4 introduce turns that still need clearer occasion boundaries.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="With --apply, show patches without writing step-4 output.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Patched step-4 output path (defaults to in-place update of --step4).",
    )
    parser.add_argument(
        "--only-needs-fix",
        action="store_true",
        help="Report only findings with status=needs_fix.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    step3 = load_json(args.step3)
    step4 = load_json(args.step4)
    findings = audit_exception_introduces(step3, step4)

    if args.only_needs_fix:
        findings = [finding for finding in findings if finding.status == "needs_fix"]

    report_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "step3": str(resolve_path(args.step3)),
        "step4": str(resolve_path(args.step4)),
        "summary": {
            "low_coverage_exception_introduce_turns": len(findings),
            "clear_after_review": sum(1 for finding in findings if finding.status == "clear"),
            "needs_fix": sum(1 for finding in findings if finding.status == "needs_fix"),
        },
        "findings": findings_to_json(findings),
    }
    write_json(args.report, report_payload)

    print(f"Audit report: {resolve_path(args.report)}")
    print(
        "Summary: "
        f"low_coverage={report_payload['summary']['low_coverage_exception_introduce_turns']} "
        f"clear_after_review={report_payload['summary']['clear_after_review']} "
        f"needs_fix={report_payload['summary']['needs_fix']}"
    )

    if args.apply:
        all_findings = audit_exception_introduces(step3, step4)
        patched_step4, applied = apply_fixes(step4, all_findings, dry_run=args.dry_run)
        apply_report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "dry_run": args.dry_run,
            "patched_count": len(applied),
            "applied": applied,
        }
        apply_path = resolve_path(args.report).with_name(
            "eval_step4_exception_occasion_patches.json"
        )
        write_json(apply_path, apply_report)
        print(f"Patch report: {apply_path}")
        print(f"Patched introduce turns: {len(applied)}")

        if not args.dry_run:
            output_path = resolve_path(args.output or args.step4)
            write_json(output_path, patched_step4)
            print(f"Updated step-4 histories: {output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
