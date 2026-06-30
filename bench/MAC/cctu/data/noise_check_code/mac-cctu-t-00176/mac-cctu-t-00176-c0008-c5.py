def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    if not traj:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no trajectory','evidence_refs':[]}
    pre_tool_text = ''
    found_tool = False
    first_step_with_tool_idx = None
    for i, step in enumerate(traj):
        tcs = step.get('tool_calls') or []
        content = step.get('content') or ''
        if tcs:
            found_tool = True
            first_step_with_tool_idx = i
            # include content of this step too (roadmap could be in same message as tool call? constraint says before any tool call)
            break
        pre_tool_text += '\n' + content
    if not found_tool:
        # No tools used; check if roadmap still present
        pre_tool_text = '\n'.join((s.get('content') or '') for s in traj)
    # Detect numbered roadmap: at least 2 lines starting with number.
    lines = [l.strip() for l in pre_tool_text.splitlines() if l.strip()]
    numbered = [l for l in lines if re.match(r'^(\(?\d+[\.\)])|^\d+\s', l)]
    has_roadmap = len(numbered) >= 2
    if not has_roadmap:
        return {'observed_followed': False, 'confidence':'medium','reason':'No numbered roadmap with >=2 items found before first tool call','evidence_refs':[]}
    return {'observed_followed': True, 'confidence':'medium','reason': f'Found {len(numbered)} numbered items before any tool call','evidence_refs':[]}
