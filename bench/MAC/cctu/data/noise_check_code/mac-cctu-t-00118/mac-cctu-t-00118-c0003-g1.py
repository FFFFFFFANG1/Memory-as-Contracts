def evaluate(trace):
    trace = trace or {}
    final = str(trace.get('final_response') or '')
    trajectory = trace.get('trajectory') or []
    tool_calls = trace.get('tool_calls') or []
    failures = []
    evidence = []

    # Tool usage required: at least 2, at most 4
    tc_count = len(tool_calls)
    evidence.append({'tool_call_count': tc_count})
    if tc_count < 2:
        failures.append('tool calls ' + str(tc_count) + ' below minimum 2')
    if tc_count > 4:
        failures.append('tool calls ' + str(tc_count) + ' above maximum 4')

    # historical_event_tool at most 2
    het_count = 0
    for call in tool_calls:
        if str(call.get('name') or '') == 'historical_event_tool':
            het_count += 1
    evidence.append({'historical_event_tool_count': het_count})
    if het_count > 2:
        failures.append('historical_event_tool calls ' + str(het_count) + ' above maximum 2')

    # Interaction rounds: max 2
    rounds = len(trajectory)
    evidence.append({'interaction_rounds': rounds})
    if rounds > 2:
        failures.append('interaction rounds ' + str(rounds) + ' above maximum 2')

    # Final answer length: 100-200 characters
    if not final and not trajectory and not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty trace', 'evidence_refs': evidence}
    char_len = len(final)
    evidence.append({'final_char_length': char_len})
    if char_len < 100:
        failures.append('final answer length ' + str(char_len) + ' below minimum 100')
    if char_len > 200:
        failures.append('final answer length ' + str(char_len) + ' above maximum 200')

    if failures:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(failures[:8]), 'evidence_refs': evidence}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'tool use, counts, rounds, and length within bounds', 'evidence_refs': evidence}
