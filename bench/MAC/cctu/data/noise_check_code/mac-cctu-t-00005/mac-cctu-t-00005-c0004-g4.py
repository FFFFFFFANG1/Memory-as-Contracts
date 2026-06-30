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
    stripped = final.strip()
    length = len(stripped)
    evidence.append({'final_length': length})
    if length < 30 or length > 50:
        failures.append(f'JSON length {length} not in [30,50]')
    parsed = None
    try:
        parsed = json.loads(stripped)
    except Exception:
        failures.append('final response is not valid JSON')
    if isinstance(parsed, dict):
        keys = list(parsed.keys())
        evidence.append({'json_keys': keys})
        if keys != ['president']:
            failures.append(f"JSON keys {keys} must be exactly ['president']")
        else:
            name = parsed.get('president')
            if not isinstance(name, str):
                failures.append('president value must be a string')
            else:
                if name != name.rstrip() or re.search(r'[\.,;:!\?]$', name):
                    failures.append(f'president value has trailing punctuation: {name!r}')
    elif parsed is not None:
        failures.append('JSON root is not an object')
    rounds = len(trajectory)
    evidence.append({'interaction_rounds': rounds})
    if rounds > 3:
        failures.append(f'interaction rounds {rounds} above maximum 3')
    total_calls = len(tool_calls)
    evidence.append({'total_tool_calls': total_calls})
    if total_calls < 1:
        failures.append(f'tool calls {total_calls} below minimum 1')
    if total_calls > 3:
        failures.append(f'tool calls {total_calls} above maximum 3')
    eor = sum(1 for c in tool_calls if str(c.get('name') or '') == 'event_outcome_retriever')
    evidence.append({'event_outcome_retriever_calls': eor})
    if eor > 1:
        failures.append(f'event_outcome_retriever called {eor} times, max 1')
    if failures:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(failures[:8]), 'evidence_refs': evidence}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'all constraint checks passed', 'evidence_refs': evidence}
