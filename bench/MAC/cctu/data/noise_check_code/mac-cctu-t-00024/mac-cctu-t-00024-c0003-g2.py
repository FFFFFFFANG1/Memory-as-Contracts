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
    parsed = None
    stripped = final.strip()
    try:
        parsed = json.loads(stripped)
    except Exception:
        for m in re.findall(r'\{.*?\}', stripped, flags=re.DOTALL):
            try:
                cand = json.loads(m)
                if isinstance(cand, dict):
                    parsed = cand
                    break
            except Exception:
                continue
    if not isinstance(parsed, dict):
        failures.append('final response is not a valid JSON object')
    else:
        evidence.append({'json_keys': sorted(parsed.keys())})
        if 'release_date' not in parsed:
            failures.append("JSON object missing key 'release_date'")
        else:
            value = parsed.get('release_date')
            if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
                failures.append(f'release_date value {value!r} is not YYYY-MM-DD format')
            else:
                try:
                    import datetime as _dt
                    _dt.date.fromisoformat(value)
                except Exception:
                    failures.append(f'release_date value {value!r} is not a valid date')
    turns = len(trajectory)
    evidence.append({'interaction_turns': turns})
    if turns < 1 or turns > 3:
        failures.append(f'interaction turns {turns} not in 1..3')
    tc = len(tool_calls)
    evidence.append({'tool_calls': tc})
    if tc > 2:
        failures.append(f'tool calls {tc} exceed maximum 2')
    if failures:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(failures[:8]), 'evidence_refs': evidence}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'all checks passed', 'evidence_refs': evidence}
