import json
import re

def _parse_json_object(text):
    text = (text or '').strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    for match in re.findall(r'\{.*?\}', text, flags=re.DOTALL):
        try:
            parsed = json.loads(match)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            continue
    # try greedy
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1 and end > start:
        try:
            parsed = json.loads(text[start:end+1])
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
    return None

def evaluate(trace):
    trace = trace or {}
    final = trace.get('final_response')
    tool_calls = trace.get('tool_calls') or []
    failures = []
    evidence = []

    if final is None:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'missing final response', 'evidence_refs': []}

    final_str = str(final)

    # Check 1: tools were called
    n_calls = len(tool_calls)
    evidence.append({'tool_call_count': n_calls})
    if n_calls == 0:
        failures.append('no tool calls made; constraint requires answering via tools')

    # Check 2: total tool calls <= 3
    if n_calls > 3:
        failures.append(f'tool calls {n_calls} exceed maximum 3')

    # Check 3: final response is valid JSON object with key 'location'
    parsed = _parse_json_object(final_str)
    if parsed is None:
        failures.append('expected a valid JSON object in final response')
    else:
        keys = list(parsed.keys())
        evidence.append({'json_keys': keys})
        if 'location' not in parsed:
            failures.append("JSON object missing key 'location'")
        else:
            value = parsed.get('location')
            if not isinstance(value, str) or not value.strip():
                failures.append("'location' value is empty or not a string")
            else:
                evidence.append({'location': value})

    if failures:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(failures[:6]), 'evidence_refs': evidence}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'tools used (<=3 calls) and final response is JSON with location key', 'evidence_refs': evidence}
