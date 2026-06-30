def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    tool_calls = trace.get('tool_calls') or []
    # Find first tool call iteration/index
    first_tc_idx = None
    for i, step in enumerate(traj):
        if step.get('tool_calls'):
            first_tc_idx = i
            break
    plan_found = False
    plan_evidence = None
    if first_tc_idx is None:
        # check any pre-tool content for a plan
        pre_steps = traj
    else:
        pre_steps = traj[:first_tc_idx+1] if first_tc_idx == 0 else traj[:first_tc_idx]
        # also include the step that made the call if its content has plan before call
        if first_tc_idx < len(traj):
            pre_steps = list(pre_steps) + [traj[first_tc_idx]]
    for step in pre_steps:
        content = (step.get('content') or '') if isinstance(step, dict) else ''
        if not content:
            continue
        # multi-step plan: look for enumeration or step markers
        lines = [l.strip() for l in content.split('\n') if l.strip()]
        numbered = sum(1 for l in lines if re.match(r'^(\d+[\.\)]|[-\*]\s|step\s*\d)', l, re.I))
        has_plan_kw = bool(re.search(r'\bplan\b|\bsteps?\b|\bfirst\b.*\bthen\b', content, re.I))
        if numbered >= 2 or (has_plan_kw and numbered >= 2):
            plan_found = True
            plan_evidence = content[:200]
            break
    turns = len(traj)
    enough_turns = turns >= 4
    if first_tc_idx is None and not traj:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no trajectory', 'evidence_refs': []}
    followed = plan_found and enough_turns
    reason = f'plan_found={plan_found}, turns={turns}, first_tool_step={first_tc_idx}'
    return {'observed_followed': bool(followed), 'confidence': 'medium', 'reason': reason, 'evidence_refs': [plan_evidence] if plan_evidence else []}
