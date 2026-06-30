def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    pre_text = ''
    first_tool_step = None
    for i, step in enumerate(traj):
        tcs = step.get('tool_calls') or []
        content = step.get('content') or ''
        if tcs:
            first_tool_step = i
            # include content of this step too (text before tool call in same step)
            pre_text += '\n' + content
            break
        pre_text += '\n' + content
    if first_tool_step is None:
        return {'observed_followed': None, 'confidence':'unknown', 'reason':'No tool calls found in trajectory', 'evidence_refs':[]}
    # Look for a numbered roadmap: at least two lines starting with 1. and 2.
    lines = [l.strip() for l in pre_text.splitlines()]
    nums = []
    for l in lines:
        m = re.match(r'^(\d+)[\.\)]\s+\S', l)
        if m:
            nums.append(int(m.group(1)))
    has_roadmap = 1 in nums and 2 in nums
    if has_roadmap:
        return {'observed_followed': True, 'confidence':'high', 'reason':'Numbered roadmap with items 1 and 2 found before first tool call', 'evidence_refs':[{'step_index':first_tool_step}]}
    return {'observed_followed': False, 'confidence':'medium', 'reason':'No explicit numbered roadmap (items 1., 2., ...) recorded before first tool call', 'evidence_refs':[{'step_index':first_tool_step}]}
