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
    evidence.append({'field': 'final_response', 'starts_ok': final.lstrip().startswith(prefix)})

    parsed = None
    candidates = [final]
    candidates.extend(re.findall(r'\{.*?\}', final, flags=re.DOTALL))
    candidates.extend(re.findall(r'\{.*\}', final, flags=re.DOTALL))
    for c in candidates:
        try:
            p = json.loads(c)
            if isinstance(p, dict):
                parsed = p
                break
        except Exception:
            continue
    if parsed is None:
        failures.append('no valid JSON object found in response')
    else:
        if 'release_date' not in parsed:
            failures.append("JSON object missing key 'release_date'")
        else:
            val = parsed.get('release_date')
            if not isinstance(val, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', val):
                failures.append(f"release_date {val!r} not in YYYY-MM-DD format")
            else:
                try:
                    import datetime
                    datetime.date.fromisoformat(val)
                except Exception:
                    failures.append(f'release_date {val!r} not a valid date')
        evidence.append({'json_keys': sorted(str(k) for k in parsed.keys())})

    turns = len(trajectory)
    if turns < 1 or turns > 3:
        failures.append(f'interaction turns {turns} outside 1-3')
    evidence.append({'turns': turns})

    tc = len(tool_calls)
    if tc > 2:
        failures.append(f'tool calls {tc} exceed max 2')
    evidence.append({'tool_calls': tc})

    if failures:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(failures[:8]), 'evidence_refs': evidence}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'all constraint parts satisfied', 'evidence_refs': evidence}
