def evaluate(trace):
    traj = trace.get('trajectory') or []
    if not traj:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no trajectory','evidence_refs':[]}
    violations = []
    steps_with_tools = []
    for i, step in enumerate(traj):
        tcs = step.get('tool_calls') or []
        if tcs:
            steps_with_tools.append((i, len(tcs)))
            if len(tcs) > 1:
                violations.append({'step_index': i, 'tool_call_count': len(tcs), 'tools': [t.get('name') for t in tcs]})
    if not steps_with_tools:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no tool calls found','evidence_refs':[]}
    # InitialDiscovery is typically the early information-gathering portion.
    # Without explicit phase markers, treat the first half of tool-using steps as discovery.
    discovery_cutoff = max(1, len(steps_with_tools) // 2)
    discovery_step_indices = {steps_with_tools[i][0] for i in range(discovery_cutoff)}
    discovery_violations = [v for v in violations if v['step_index'] in discovery_step_indices]
    if discovery_violations:
        return {'observed_followed': False, 'confidence':'high','reason': f'{len(discovery_violations)} early turn(s) issued parallel tool calls','evidence_refs': discovery_violations}
    if violations:
        return {'observed_followed': True, 'confidence':'low','reason':'parallel calls exist only in later turns (likely post-discovery)','evidence_refs': violations}
    return {'observed_followed': True, 'confidence':'high','reason':'all turns used single tool call','evidence_refs': []}
