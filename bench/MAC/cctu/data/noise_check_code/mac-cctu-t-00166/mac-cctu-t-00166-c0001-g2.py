import json
import re

def evaluate(trace):
    trace = trace or {}
    final = str(trace.get('final_response') or '')
    trajectory = trace.get('trajectory') or []
    tool_calls = trace.get('tool_calls') or []
    failures = []
    evidence = []

    tc_count = len(tool_calls)
    evidence.append({'tool_call_count': tc_count})
    if tc_count < 8:
        failures.append(f'tool calls {tc_count} below minimum 8')
    if tc_count > 12:
        failures.append(f'tool calls {tc_count} above maximum 12')

    turn_count = len(trajectory)
    evidence.append({'interaction_turns': turn_count})
    if turn_count > 15:
        failures.append(f'interaction turns {turn_count} above maximum 15')

    if not final.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'missing final response', 'evidence_refs': evidence}

    stripped = final.strip()
    parsed = None
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
        keys = list(parsed.keys())
        evidence.append({'json_keys': keys})
        if set(keys) != {'answer'}:
            failures.append(f'JSON keys {sorted(keys)} are not exactly {{"answer"}}')
        else:
            val = parsed.get('answer')
            if val not in ('Yes.', 'No.'):
                failures.append(f'answer value {val!r} is not "Yes." or "No."')

    if not stripped.endswith('.'):
        failures.append("response does not end with '.'")

    if failures:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(failures[:8]), 'evidence_refs': evidence}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'tool count, turn count, and JSON format all satisfied', 'evidence_refs': evidence}
