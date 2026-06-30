def evaluate(trace):
    traj = trace.get('trajectory') or []
    pre_text = ''
    found_tool = False
    for step in traj:
        tcs = step.get('tool_calls') or []
        content = step.get('content') or ''
        if tcs:
            found_tool = True
            break
        if isinstance(content, str):
            pre_text += '\n' + content
    if not found_tool:
        # No tools invoked at all; constraint about ordering is vacuously satisfied if text exists
        if pre_text.strip():
            text = pre_text.lower()
            has_subtasks = any(k in text for k in ['sub-task','subtask','step 1','1.','1)','first,','plan'])
            has_deps = any(k in text for k in ['depend','dependenc','before','after','then','requires','->'])
            if has_subtasks and has_deps:
                return {'observed_followed': True, 'confidence':'low','reason':'No tools used; decomposition present in text.','evidence_refs':[]}
        return {'observed_followed': None,'confidence':'unknown','reason':'No tool invocations found; cannot fully verify ordering requirement.','evidence_refs':[]}
    text = pre_text.lower().strip()
    if not text:
        return {'observed_followed': False,'confidence':'high','reason':'No written content emitted before first tool call.','evidence_refs':[]}
    has_subtasks = any(k in text for k in ['sub-task','subtask','step 1','step1','1.','1)','first','plan','decompos','breakdown','break down'])
    has_tool_mention = any(t.lower() in text for t in ['tool','retriev','locator','finder','search','mapper','calculator','counter','identifier']) 
    has_deps = any(k in text for k in ['depend','before','after','then','requires','->','followed by','prerequisite','feed','use the result','based on'])
    if has_subtasks and has_tool_mention and has_deps:
        return {'observed_followed': True,'confidence':'high','reason':'Pre-tool message includes sub-task decomposition with tool dependencies.','evidence_refs':[]}
    missing = []
    if not has_subtasks: missing.append('sub-task list')
    if not has_tool_mention: missing.append('tool references')
    if not has_deps: missing.append('dependency description')
    return {'observed_followed': False,'confidence':'medium','reason':'Pre-tool text missing: '+', '.join(missing),'evidence_refs':[]}
