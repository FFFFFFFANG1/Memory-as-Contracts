def evaluate(trace):
    tool_calls = trace.get('tool_calls') or []
    trajectory = trace.get('trajectory') or []
    response = str(trace.get('final_response') or '')
    if not response.strip() and not tool_calls and not trajectory:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no observable behavior', 'evidence_refs': []}
    tool_count = len([c for c in tool_calls if c.get('name')])
    if tool_count == 0:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no tool calls observed; investigation requires using the tool budget', 'evidence_refs': []}
    if tool_count > 8:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'tool call count ' + str(tool_count) + ' exceeds budget of 8', 'evidence_refs': []}
    rounds = set()
    for c in tool_calls:
        it = c.get('iteration')
        if it is not None:
            rounds.add(it)
    if not rounds:
        assistant_rounds = 0
        for step in trajectory:
            role = step.get('role') if isinstance(step, dict) else None
            if role == 'assistant' and (step.get('tool_calls') or []):
                assistant_rounds += 1
        round_count = assistant_rounds if assistant_rounds else None
    else:
        round_count = len(rounds)
    if round_count is not None and round_count > 4:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'interaction rounds ' + str(round_count) + ' exceeds 4', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'tool calls=' + str(tool_count) + ', rounds=' + str(round_count) + ' within 8/4 budget', 'evidence_refs': []}
