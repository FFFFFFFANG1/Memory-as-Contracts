def evaluate(trace):
    trace = trace or {}
    final = str(trace.get('final_response') or '')
    trajectory = trace.get('trajectory') or []
    tool_calls = trace.get('tool_calls') or []
    failures = []
    evidence = []
    n_calls = len(tool_calls)
    evidence.append({'tool_calls': n_calls})
    if n_calls < 2:
        failures.append(f'tool calls {n_calls} below minimum 2')
    if n_calls > 4:
        failures.append(f'tool calls {n_calls} above maximum 4')
    het = 0
    for call in tool_calls:
        if str(call.get('name') or '') == 'historical_event_tool':
            het += 1
    evidence.append({'historical_event_tool_calls': het})
    if het > 2:
        failures.append(f'historical_event_tool calls {het} above maximum 2')
    rounds = len(trajectory)
    evidence.append({'interaction_rounds': rounds})
    if rounds > 2:
        failures.append(f'interaction rounds {rounds} above maximum 2')
    if not final:
        if failures:
            return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(failures[:8]), 'evidence_refs': evidence}
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'missing final response', 'evidence_refs': evidence}
    char_len = len(final)
    evidence.append({'final_char_length': char_len})
    if char_len < 100:
        failures.append(f'final answer length {char_len} below minimum 100')
    if char_len > 200:
        failures.append(f'final answer length {char_len} above maximum 200')
    if failures:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(failures[:8]), 'evidence_refs': evidence}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'tool usage, counts, rounds, and length within bounds', 'evidence_refs': evidence}
