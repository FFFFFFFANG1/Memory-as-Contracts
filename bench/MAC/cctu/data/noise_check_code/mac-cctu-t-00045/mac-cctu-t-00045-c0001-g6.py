def evaluate(trace):
    traj = trace.get('trajectory') or []
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no tool calls','evidence_refs':[]}
    # group calls by assistant step/iteration
    steps = {}
    for c in calls:
        k = c.get('iteration', c.get('index'))
        steps.setdefault(k, []).append(c)
    step_sizes = [len(v) for v in steps.values()]
    n_steps = len(step_sizes)
    total = sum(step_sizes)
    max_batch = max(step_sizes) if step_sizes else 0
    if total <= 1:
        return {'observed_followed': True,'confidence':'low','reason':'only one tool call; nothing to batch','evidence_refs':[]}
    if n_steps == 1 and max_batch == total:
        return {'observed_followed': True,'confidence':'high','reason':f'all {total} calls issued in a single parallel batch','evidence_refs':[]}
    # multiple steps used: possible serialization of independent tasks
    if max_batch > 1:
        return {'observed_followed': None,'confidence':'low','reason':f'partial batching: {n_steps} steps with sizes {step_sizes}; cannot confirm independence','evidence_refs':[]}
    return {'observed_followed': False,'confidence':'medium','reason':f'{total} tool calls spread across {n_steps} sequential steps with no parallel batching','evidence_refs':[]}
