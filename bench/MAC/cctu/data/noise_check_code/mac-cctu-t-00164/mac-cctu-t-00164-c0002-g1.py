def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    tool_calls = trace.get('tool_calls') or []
    if not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls present', 'evidence_refs': []}
    # find first tool call iteration/index
    first_iter = None
    for tc in tool_calls:
        it = tc.get('iteration')
        if it is None:
            it = tc.get('index')
        if it is None:
            continue
        if first_iter is None or it < first_iter:
            first_iter = it
    pre_text = ''
    for i, step in enumerate(traj):
        has_calls = bool(step.get('tool_calls'))
        content = step.get('content') or ''
        if has_calls:
            pre_text += '\n' + content
            break
        pre_text += '\n' + content
    if not pre_text.strip():
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'No written content before first tool call', 'evidence_refs': []}
    low = pre_text.lower()
    decomp_terms = ['sub-task','subtask','sub task','step 1','1.','decompos','break down','breakdown','atomic']
    dep_terms = ['depend','depends on','requires','prerequisite','before','after','then','sequence','order','rely on','based on']
    has_decomp = any(t in low for t in decomp_terms)
    has_dep = any(t in low for t in dep_terms)
    # also require some enumeration structure
    enumerated = bool(re.search(r'(^|\n)\s*(\d+[\.)\-]|[-*])\s+\S', pre_text))
    followed = has_decomp and has_dep and enumerated
    reason = f'decomp={has_decomp}, dependency={has_dep}, enumerated={enumerated}'
    return {'observed_followed': bool(followed), 'confidence': 'medium', 'reason': reason, 'evidence_refs': []}
