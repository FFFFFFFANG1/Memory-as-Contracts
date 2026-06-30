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

    # Check 1: starts with required phrase
    prefix = 'The nurses were released on'
    if not final.lstrip().startswith(prefix):
        failures.append(f'response does not start with {prefix!r}')

    # Check 2: valid JSON object with release_date in YYYY-MM-DD
    parsed = None
    candidates = []
    stripped = final.strip()
    candidates.append(stripped)
    # find JSON object substrings (greedy and non-greedy)
    for m in re.finditer(r'\{[^{}]*\}', final, flags=re.DOTALL):
        candidates.append(m.group(0))
    for m in re.finditer(r'\{.*\}', final, flags=re.DOTALL):
        candidates.append(m.group(0))
    for cand in candidates:
        try:
            p = json.loads(cand)
            if isinstance(p, dict):
                parsed = p
                break
        except Exception:
            continue
    if parsed is None:
        failures.append('expected a valid JSON object in response')
    else:
        evidence.append({'json_keys': sorted(str(k) for k in parsed.keys())})
        if 'release_date' not in parsed:
            failures.append("JSON object missing 'release_date' key")
        else:
            val = parsed.get('release_date')
            if not isinstance(val, str) or not re.match(r'^\d{4}-\d{2}-\d{2}$', val):
                failures.append(f'release_date value {val!r} not in YYYY-MM-DD format')
            else:
                try:
                    import datetime
                    datetime.date.fromisoformat(val)
                except Exception:
                    failures.append(f'release_date value {val!r} is not a valid date')

    # Check 3: interaction turns 1-3
    turns = len(trajectory)
    if turns < 1 or turns > 3:
        failures.append(f'interaction turns {turns} not in [1,3]')
    evidence.append({'turns': turns})

    # Check 4: at most 2 total tool calls
    tc = len(tool_calls)
    if tc > 2:
        failures.append(f'tool calls {tc} exceeds maximum 2')
    evidence.append({'tool_calls': tc})

    if failures:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(failures[:8]), 'evidence_refs': evidence}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'all constraint checks passed', 'evidence_refs': evidence}
