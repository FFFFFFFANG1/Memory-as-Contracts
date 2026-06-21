from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from benchmarks.schemas.models import CanonicalEvent


def write_events_jsonl(path: Path, events: Iterable[CanonicalEvent]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(event.model_dump_json(exclude_none=True) + "\n")


def read_events_jsonl(path: Path) -> list[CanonicalEvent]:
    events: list[CanonicalEvent] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL event at {path}:{line_number}") from exc
            events.append(CanonicalEvent.model_validate(payload))
    ids = [event.event_id for event in events]
    if ids != sorted(ids):
        raise ValueError("JSONL events must be sorted by event_id")
    return events
