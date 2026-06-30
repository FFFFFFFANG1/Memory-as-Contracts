def evaluate(trace):
    trajectory = trace.get('trajectory') or []
    tool_calls = trace.get('tool_calls') or []
    if not trajectory and not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no trajectory data', 'evidence_refs': []}
    # count assistant turns
    assistant_turns = [s for s in trajectory if (s.get('role') == 'assistant') or s.get('tool_calls') or s.get('content')]
    turn_count = len(assistant_turns) if assistant_turns else len(trajectory)
    # find turns containing tool calls
    tool_turn_indices = set()
    for i, s in enumerate(trajectory):
        tcs = s.get('tool_calls') or []
        if tcs:
            tool_turn_indices.add(i)
    # fallback via flattened tool_calls using iteration field
    iterations = set()
    for tc in tool_calls:
        it = tc.get('iteration')
        if it is not None:
            iterations.add(it)
    distinct_tool_turns = len(tool_turn_indices) if tool_turn_indices else len(iterations)
    followed = True
    reasons = []
    if distinct_tool_turns > 1:
        followed = False
        reasons.append(f'tool calls span {distinct_tool_turns} turns, not batched into one')
    if turn_count > 2:
        followed = False
        reasons.append(f'interaction used {turn_count} assistant turns, exceeds 2')
    if not tool_calls:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'no tool calls observed', 'evidence_refs': []}
    reason = '; '.join(reasons) if reasons else f'all tool calls in single turn; total turns={turn_count}'
    return {'observed_followed': followed, 'confidence': 'high' if (tool_turn_indices or iterations) else 'medium', 'reason': reason, 'evidence_refs': []}
