import json
import re

def evaluate(trace):
    trace = trace or {}
    final = str(trace.get('final_response') or '')
    trajectory = trace.get('trajectory') or []
    tool_calls = trace.get('tool_calls') or []
    failures = []
    evidence = []

    if not final.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'missing final response', 'evidence_refs': []}

    # Tool call count: 8-12
    tc = len(tool_calls)
    evidence.append({'tool_calls': tc})
    if tc < 8:
        failures.append(f'tool calls {tc} below minimum 8')
    if tc > 12:
        failures.append(f'tool calls {tc} above maximum 12')

    # Interaction turns: <= 15
    turns = len(trajectory)
    evidence.append({'turns': turns})
    if turns > 15:
        failures.append(f'interaction turns {turns} above maximum 15')

    # Final response format: JSON object + END
    stripped = final.strip()
    end_match = re.search(r'END\s*$', stripped)
    if not end_match:
        failures.append("response does not end with 'END'")
    else:
        after = stripped[end_match.end():]
        if after.strip():
            failures.append('content after END')
        # Check no trailing punctuation after END
        if re.search(r'END[\.,;:!\?]', stripped):
            failures.append('END has trailing punctuation')

    # Extract JSON portion before END
    json_part = stripped[:end_match.start()].strip() if end_match else stripped
    parsed = None
    try:
        parsed = json.loads(json_part)
    except Exception:
        m = re.search(r'\{.*\}', json_part, flags=re.DOTALL)
        if m:
            try:
                parsed = json.loads(m.group(0))
            except Exception:
                parsed = None

    if not isinstance(parsed, dict):
        failures.append('expected a valid JSON object')
    else:
        keys = list(parsed.keys())
        evidence.append({'json_keys': keys})
        if set(keys) != {'answer'}:
            failures.append(f"JSON keys {sorted(keys)} must be exactly ['answer']")
        else:
            val = parsed.get('answer')
            if val not in ('Yes.', 'No.'):
                failures.append(f"answer value {val!r} must be 'Yes.' or 'No.'")

    if failures:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(failures[:8]), 'evidence_refs': evidence}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'all checks passed', 'evidence_refs': evidence}
