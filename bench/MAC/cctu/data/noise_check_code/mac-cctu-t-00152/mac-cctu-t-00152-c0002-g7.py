def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    pre_tool_text = []
    found_tool = False
    for step in traj:
        tcs = step.get('tool_calls') or []
        content = step.get('content') or ''
        if tcs:
            found_tool = True
            if content:
                pre_tool_text.append(content)
            break
        if content:
            pre_tool_text.append(content)
    text = '\n'.join(pre_tool_text)
    if not text.strip():
        return {'observed_followed': False, 'confidence':'high','reason':'No planning text before first tool call.','evidence_refs':[]}
    low = text.lower()
    dep_kw = ['depend','dependenc','prerequisite','before','after','requires','->','=>','then','step 1','step1','subtask','sub-task','sub task']
    plan_kw = ['plan','map','outline','sequence','order']
    has_dep = any(k in low for k in dep_kw)
    has_plan = any(k in low for k in plan_kw)
    has_list = bool(re.search(r'(^|\n)\s*(\d+[\.\)]|[-*])\s+', text))
    if has_dep and (has_plan or has_list):
        return {'observed_followed': True,'confidence':'medium','reason':'Pre-tool planning text references dependencies among sub-tasks.','evidence_refs':[]}
    return {'observed_followed': False,'confidence':'medium','reason':'Pre-tool text lacks explicit dependency map of sub-tasks.','evidence_refs':[]}
