def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    required = ['poet','playwright','play','character','asteroid','astronomer','country','national flower']
    plan_text = ''
    plan_found_before_tools = False
    for step in traj:
        tcs = step.get('tool_calls') or []
        content = step.get('content') or ''
        if not tcs:
            if content:
                plan_text += '\n' + content
            continue
        # first step with tool_calls
        if plan_text.strip():
            plan_found_before_tools = True
        break
    else:
        # no tool calls at all
        if plan_text.strip():
            plan_found_before_tools = True
    if not plan_found_before_tools:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'No written plan present before first tool call.', 'evidence_refs': []}
    low = plan_text.lower()
    missing = [t for t in required if t not in low]
    dep_terms = ['depend','dependenc','rely','then','after','before','requires','based on','use','feed']
    has_dep = any(d in low for d in dep_terms)
    if missing:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Plan missing sub-questions: {missing}', 'evidence_refs': []}
    if not has_dep:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Plan does not articulate inter-dependencies.', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Pre-tool plan enumerates all sub-questions and dependencies.', 'evidence_refs': []}
