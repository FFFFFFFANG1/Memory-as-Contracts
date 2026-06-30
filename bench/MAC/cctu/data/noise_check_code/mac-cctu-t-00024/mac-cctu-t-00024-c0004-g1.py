import json
import re

def evaluate(trace):
    trace = trace or {}
    final = str(trace.get('final_response') or '')
    trajectory = trace.get('trajectory') or []
    tool_calls = trace.get('tool_calls') or []
    failures = []
    evidence = []

    if not final:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'missing final response', 'evidence_refs': []}

    prefix = 'The nurses were released on'
    if not final.lstrip().startswith(prefix):
        failures.append(f'response does not start with {prefix!r}')
    evidence.append({'field': 'final_response', 'starts_with_ok': final.lstrip().startswith(prefix)})

    parsed = None
    stripped = final.strip()
    candidates = [stripped] + re.findall(r'\{[^{}]*\}', stripped, flags=re.DOTALL) + re.findall(r'\{.*\}', stripped, flags=re.DOTALL)
    for cand in candidates:
        try:
            obj = json.loads(cand)
            if isinstance(obj, dict):
                parsed = obj
                break
        except Exception:
            continue

    if parsed is None:
        failures.append('expected a valid JSON object in final response')
    else:
        if 'release_date' not in parsed:
            failures.append("JSON object missing key 'release_date'")
        else:
            val = parsed.get('release_date')
            if not isinstance(val, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', val or ''):
                failures.append(f'release_date value {val!r} not in YYYY-MM-DD format')
            else:
                try:
                    import datetime as _dt
                    _dt.date.fromisoformat(val)
                except Exception:
                    failures.append(f'release_date {val!r} is not a valid date')
        evidence.append({'json_keys': sorted(parsed.keys())})

    turns = len(trajectory)
    if turns < 1 or turns > 3:
        failures.append(f'interaction turns {turns} not within 1-3')
    evidence.append({'turns': turns})

    tc = len(tool_calls)
    if tc > 2:
        failures.append(f'tool calls {tc} exceeds maximum 2')
    evidence.append({'tool_calls': tc})

    if failures:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(failures[:8]), 'evidence_refs': evidence}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'prefix, JSON release_date YYYY-MM-DD, turns, and tool-call cap satisfied', 'evidence_refs': evidence}
