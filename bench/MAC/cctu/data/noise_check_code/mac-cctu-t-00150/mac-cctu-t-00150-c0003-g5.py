def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    if not traj:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no trajectory','evidence_refs':[]}
    # Find the first assistant step with content (the decomposition step)
    first_idx = None
    for i, step in enumerate(traj):
        content = (step.get('content') or '').strip()
        if content:
            first_idx = i
            break
    if first_idx is None:
        return {'observed_followed': None,'confidence':'unknown','reason':'no assistant content found','evidence_refs':[]}
    first_step = traj[first_idx]
    content = first_step.get('content') or ''
    # Check for numbered plan: at least two lines like '1.' '2.' or '1)' '2)'
    numbered = re.findall(r'(?m)^\s*(\d+)[\.\)]\s+\S', content)
    has_plan = len(numbered) >= 2
    # Check that the first step (decomposition) did not invoke tools
    tool_calls_in_first = first_step.get('tool_calls') or []
    # Also check that no earlier step invoked tools
    earlier_tools = []
    for j in range(0, first_idx+1):
        earlier_tools.extend(traj[j].get('tool_calls') or [])
    no_tools_before_plan = len(earlier_tools) == 0
    followed = has_plan and no_tools_before_plan
    reason = f'numbered_items={len(numbered)}, tools_during_or_before_decomp={len(earlier_tools)}'
    return {'observed_followed': bool(followed),'confidence':'medium' if has_plan or earlier_tools else 'low','reason':reason,'evidence_refs':[]}
