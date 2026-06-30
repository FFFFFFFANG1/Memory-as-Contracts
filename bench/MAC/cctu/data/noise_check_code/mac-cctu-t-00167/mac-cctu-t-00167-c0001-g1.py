def evaluate(trace):
    traj = trace.get('trajectory') or []
    if not traj:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no trajectory', 'evidence_refs': []}
    offenders = []
    saw_any_tool = False
    for i, step in enumerate(traj):
        tcs = step.get('tool_calls') or []
        if not tcs:
            continue
        saw_any_tool = True
        # initial_research phase is not explicitly labeled; treat early turns with tool use as initial research
        if len(tcs) > 1:
            offenders.append({'turn_index': i, 'tool_call_count': len(tcs)})
    if not saw_any_tool:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls observed in trajectory', 'evidence_refs': []}
    if offenders:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'{len(offenders)} turn(s) invoked more than one tool, violating one-tool-per-turn during initial research', 'evidence_refs': offenders}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'every assistant turn that called tools issued exactly one tool call', 'evidence_refs': []}
