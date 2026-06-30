def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    if not traj:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no trajectory','evidence_refs':[]}
    # find first step with content and first step with tool calls
    first_tool_idx = None
    for i, step in enumerate(traj):
        if step.get('tool_calls'):
            first_tool_idx = i
            break
    # gather assistant content before first tool call
    pre_content = ''
    pre_steps = traj if first_tool_idx is None else traj[:first_tool_idx+1]
    # The outline must be complete BEFORE invoking any tool, so look at content of steps prior to (and including the planning step that precedes) tool calls
    for i, step in enumerate(traj):
        if first_tool_idx is not None and i > first_tool_idx:
            break
        c = step.get('content') or ''
        # If this step has tool_calls, only count its content (which should contain the outline before the call)
        pre_content += '\n' + c
        if step.get('tool_calls') and i == first_tool_idx:
            # also stop after this
            pass
    # detect numbered outline: lines starting with '1.' '2.' etc., at least 2 items
    lines = pre_content.splitlines()
    nums = []
    for ln in lines:
        m = re.match(r'\s*(\d+)[\.\)]\s+\S', ln)
        if m:
            nums.append(int(m.group(1)))
    has_outline = len(nums) >= 2 and nums[:2] == [1,2]
    if first_tool_idx is None:
        # No tools called; outline still required during decomposition
        if has_outline:
            return {'observed_followed': True,'confidence':'medium','reason':'numbered outline present, no tools invoked','evidence_refs':[]}
        return {'observed_followed': None,'confidence':'low','reason':'no tools and no clear outline','evidence_refs':[]}
    if has_outline:
        return {'observed_followed': True,'confidence':'high','reason':'numbered outline present before first tool call','evidence_refs':[f'first_tool_step={first_tool_idx}']}
    return {'observed_followed': False,'confidence':'high','reason':'no numbered outline detected before first tool invocation','evidence_refs':[f'first_tool_step={first_tool_idx}']}
