def evaluate(trace):
    tool_calls = trace.get('tool_calls') or []
    trajectory = trace.get('trajectory') or []
    final_response = str(trace.get('final_response') or '')
    if not tool_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'geospatial comparison work expected but no tool calls observed', 'evidence_refs': []}
    tool_count = len(tool_calls)
    if tool_count > 25:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'tool call count ' + str(tool_count) + ' exceeds cap of 25', 'evidence_refs': []}
    turns = 0
    for step in trajectory:
        if isinstance(step, dict):
            role = str(step.get('role') or '')
            if role in ('assistant', 'user') or step.get('content') is not None or step.get('tool_calls'):
                turns += 1
    if turns == 0:
        turns = len(trajectory)
    if turns > 20:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'interaction turns ' + str(turns) + ' exceeds cap of 20', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'turns=' + str(turns) + ' tool_calls=' + str(tool_count) + ' within caps (20 turns / 25 calls)', 'evidence_refs': []}
