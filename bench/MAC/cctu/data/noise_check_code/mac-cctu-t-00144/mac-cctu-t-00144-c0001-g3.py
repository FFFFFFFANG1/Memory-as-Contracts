def evaluate(trace):
    trace = trace or {}
    final = str(trace.get('final_response') or '')
    trajectory = trace.get('trajectory') or []
    tool_calls = trace.get('tool_calls') or []
    failures = []
    evidence = []
    # Check 1: merged_event_data_retriever called twice in a single round
    merged_in_step = []
    for idx, step in enumerate(trajectory):
        calls = step.get('tool_calls') or []
        names = [str(c.get('name') or '') for c in calls if isinstance(c, dict)]
        count = sum(1 for n in names if n == 'merged_event_data_retriever')
        merged_in_step.append(count)
        if count >= 2:
            evidence.append({'step': idx, 'merged_calls': count})
    if not any(c >= 2 for c in merged_in_step):
        total_merged = sum(1 for c in tool_calls if str(c.get('name') or '') == 'merged_event_data_retriever')
        failures.append(f"merged_event_data_retriever not called twice in a single round (per-step counts={merged_in_step}, total={total_merged})")
    # Check 2: final response length 50-200 characters
    if not final:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'missing final response', 'evidence_refs': evidence}
    char_len = len(final)
    evidence.append({'final_chars': char_len})
    if char_len < 50:
        failures.append(f'final response length {char_len} below minimum 50')
    if char_len > 200:
        failures.append(f'final response length {char_len} above maximum 200')
    # Check 3: starts with 'Casualty difference: '
    prefix = 'Casualty difference: '
    if not final.startswith(prefix):
        failures.append(f"response does not start with {prefix!r}")
    # Check 4: 1-2 interaction turns
    turns = len(trajectory)
    evidence.append({'turns': turns})
    if turns < 1:
        failures.append(f'interaction turns {turns} below minimum 1')
    if turns > 2:
        failures.append(f'interaction turns {turns} above maximum 2')
    if failures:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(failures[:8]), 'evidence_refs': evidence}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'all constraint checks passed', 'evidence_refs': evidence}
