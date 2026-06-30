def evaluate(trace):
    traj = trace.get('trajectory') or []
    turn_sizes = []
    for step in traj:
        tcs = step.get('tool_calls') or []
        if tcs:
            turn_sizes.append(len(tcs))
    if not turn_sizes:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls found in trajectory.', 'evidence_refs': []}
    total_calls = sum(turn_sizes)
    parallel_turns = sum(1 for n in turn_sizes if n > 1)
    single_turns = sum(1 for n in turn_sizes if n == 1)
    if total_calls <= 1:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'Only one tool call; parallelism not testable.', 'evidence_refs': [{'turn_sizes': turn_sizes}]}
    if parallel_turns >= 1 and parallel_turns >= single_turns:
        return {'observed_followed': True, 'confidence': 'high', 'reason': f'Tool calls were grouped into parallel turns ({parallel_turns} parallel vs {single_turns} single).', 'evidence_refs': [{'turn_sizes': turn_sizes}]}
    if parallel_turns == 0:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'All {single_turns} tool-using turns issued a single call; no parallel invocations.', 'evidence_refs': [{'turn_sizes': turn_sizes}]}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Mostly serial: {single_turns} single-call turns vs {parallel_turns} parallel.', 'evidence_refs': [{'turn_sizes': turn_sizes}]}
