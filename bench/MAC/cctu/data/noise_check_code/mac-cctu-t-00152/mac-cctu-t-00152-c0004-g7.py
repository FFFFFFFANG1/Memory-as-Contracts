def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    tool_calls = trace.get('tool_calls') or []
    allowed = 'historical_fact_retriever'
    # Try to identify planning phase: steps whose assistant content mentions planning/decomposition
    planning_iters = set()
    decomposition_done_iter = None
    for i, step in enumerate(traj):
        content = (step.get('content') or '').lower()
        if not content:
            continue
        if re.search(r'\b(plan|planning|decompos|break (it|this) down|sub-?task|steps to)', content):
            planning_iters.add(i)
        if decomposition_done_iter is None and re.search(r'(decomposition (is )?complete|plan (is )?(complete|ready|finalized)|execution phase|now (i will|let me) execute|moving to execution)', content):
            decomposition_done_iter = i
    # Identify violating calls: calls made during planning phase using tools other than allowed
    violations = []
    planning_calls_seen = False
    for tc in tool_calls:
        it = tc.get('iteration')
        name = tc.get('name')
        in_planning = False
        if it in planning_iters:
            in_planning = True
        elif decomposition_done_iter is not None and isinstance(it, int) and it < decomposition_done_iter:
            in_planning = True
        if in_planning:
            planning_calls_seen = True
            if name != allowed:
                violations.append({'iteration': it, 'name': name})
    if not planning_iters and decomposition_done_iter is None:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'Could not identify a planning phase in trajectory.', 'evidence_refs': []}
    if not planning_calls_seen:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'Planning phase identified but no tool calls observed within it.', 'evidence_refs': []}
    if violations:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Non-allowed tools used during planning: {violations}', 'evidence_refs': violations}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Only historical_fact_retriever used during identified planning phase.', 'evidence_refs': []}
