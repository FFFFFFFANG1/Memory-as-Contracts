import re

def evaluate(trace):
    trace = trace or {}
    final = str(trace.get('final_response') or '')
    trajectory = trace.get('trajectory') or []
    tool_calls = trace.get('tool_calls') or []
    failures = []
    evidence = []
    prefix = 'The annual production in tons is: '
    if not final:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'missing final response', 'evidence_refs': []}
    if not final.startswith(prefix):
        failures.append(f'response does not start with {prefix!r}')
    words = len(re.findall(r'\S+', final))
    evidence.append({'field': 'final_response', 'unit': 'words', 'count': words})
    if words > 200:
        failures.append(f'words length {words} above maximum 200')
    tc_count = len(tool_calls)
    evidence.append({'field': 'tool_calls', 'count': tc_count})
    if tc_count < 5:
        failures.append(f'tool calls {tc_count} below minimum 5')
    if tc_count > 7:
        failures.append(f'tool calls {tc_count} above maximum 7')
    turns = len(trajectory)
    evidence.append({'field': 'trajectory', 'turns': turns})
    if turns < 5:
        failures.append(f'interaction turns {turns} below minimum 5')
    if turns > 8:
        failures.append(f'interaction turns {turns} above maximum 8')
    if failures:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(failures[:8]), 'evidence_refs': evidence}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'all composite checks passed', 'evidence_refs': evidence}
