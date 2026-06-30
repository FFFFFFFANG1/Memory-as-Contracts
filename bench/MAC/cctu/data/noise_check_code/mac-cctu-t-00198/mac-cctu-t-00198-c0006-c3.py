def evaluate(trace):
    traj = trace.get('trajectory') or []
    steps = []
    for s in traj:
        tcs = s.get('tool_calls') or []
        names = [tc.get('name') for tc in tcs if tc.get('name')]
        if names:
            steps.append(names)
    if not steps:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no tool calls','evidence_refs':[]}
    parallel_indices = [i for i,n in enumerate(steps) if len(n)>1]
    if not parallel_indices:
        return {'observed_followed': None, 'confidence':'low','reason':'no parallel multi-tool step found; constraint precondition absent','evidence_refs':[]}
    first_par = parallel_indices[0]
    solo_before = set()
    for i in range(first_par):
        if len(steps[i])==1:
            solo_before.add(steps[i][0])
    missing = []
    for i in parallel_indices:
        for t in set(steps[i]):
            if t not in solo_before:
                missing.append((i,t))
    if missing:
        return {'observed_followed': False, 'confidence':'high','reason':f'tools used in parallel without prior isolated call: {missing}','evidence_refs':[]}
    return {'observed_followed': True, 'confidence':'high','reason':'all parallel-step tools had prior isolated invocation','evidence_refs':[]}
