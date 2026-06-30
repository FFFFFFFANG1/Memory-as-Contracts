def evaluate(trace):
    traj = trace.get('trajectory') or []
    steps_with_calls = []
    for i, step in enumerate(traj):
        tcs = step.get('tool_calls') or []
        if tcs:
            steps_with_calls.append((i, len(tcs)))
    if not steps_with_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls found in trajectory.', 'evidence_refs': []}
    if len(steps_with_calls) <= 1:
        n = steps_with_calls[0][1]
        return {'observed_followed': True, 'confidence': 'high', 'reason': f'Single assistant step issued {n} tool call(s); no sequential issuance.', 'evidence_refs': [{'step_index': steps_with_calls[0][0], 'num_calls': n}]}
    # Multiple steps with tool calls => potentially sequential
    singles = sum(1 for _, c in steps_with_calls if c == 1)
    return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Tool calls issued across {len(steps_with_calls)} separate assistant steps ({singles} singletons); independent calls were not batched into one parallel group.', 'evidence_refs': [{'step_index': i, 'num_calls': c} for i, c in steps_with_calls]}
