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
    text = final.strip()
    parsed = None
    try:
        parsed = json.loads(text)
    except Exception:
        m = re.search(r'\{.*\}', text, flags=re.DOTALL)
        if m:
            try:
                parsed = json.loads(m.group(0))
                text = m.group(0)
            except Exception:
                parsed = None
    if not isinstance(parsed, dict):
        failures.append('final response is not a valid JSON object')
    else:
        keys = list(parsed.keys())
        if keys != ['president']:
            failures.append(f"JSON keys {keys} are not exactly ['president']")
        else:
            val = parsed.get('president')
            if not isinstance(val, str) or not val.strip():
                failures.append('president value is not a non-empty string')
            else:
                if re.search(r'[\.,;:!\?\-]$', val.strip()):
                    failures.append(f'president value {val!r} has trailing punctuation')
        evidence.append({'json_keys': keys})
    length = len(text)
    evidence.append({'json_char_length': length})
    if length < 30 or length > 50:
        failures.append(f'JSON length {length} not within 30-50')
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
    eo_count = sum(1 for c in tool_calls if str(c.get('name') or '') == 'event_outcome_retriever')
    evidence.append({'event_outcome_retriever_calls': eo_count})
    if eo_count > 1:
        failures.append(f'event_outcome_retriever called {eo_count} times, max 1')
    if failures:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(failures[:8]), 'evidence_refs': evidence}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'all constraint checks passed', 'evidence_refs': evidence}
