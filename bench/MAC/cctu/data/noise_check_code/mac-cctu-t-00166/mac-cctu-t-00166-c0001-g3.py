def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    if not traj:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no trajectory','evidence_refs':[]}
    first = traj[0]
    content = (first.get('content') or '')
    tool_calls = first.get('tool_calls') or []
    if tool_calls:
        return {'observed_followed': False, 'confidence':'high','reason':'tool calls issued in initial scoping step','evidence_refs':[{'step':0,'tool_calls':len(tool_calls)}]}
    text = content.lower()
    has_subtasks = bool(re.search(r'sub[- ]?task|step\s*\d|task\s*\d|1\.|2\.', text))
    has_deps = ('depend' in text) or ('prerequisite' in text) or ('after ' in text) or ('before ' in text) or ('requires' in text)
    plan_word = ('plan' in text) or ('decompos' in text) or ('scoping' in text)
    if len(content.strip()) < 40:
        return {'observed_followed': False,'confidence':'medium','reason':'initial response too short to be a decomposition plan','evidence_refs':[{'len':len(content)}]}
    if has_subtasks and has_deps and plan_word:
        return {'observed_followed': True,'confidence':'high','reason':'initial scoping has plan with sub-tasks and dependencies, no tool calls','evidence_refs':[]}
    if has_subtasks and has_deps:
        return {'observed_followed': True,'confidence':'medium','reason':'sub-tasks and dependencies present without tool calls','evidence_refs':[]}
    return {'observed_followed': False,'confidence':'medium','reason':'initial step lacks explicit sub-tasks and/or dependencies','evidence_refs':[{'has_subtasks':has_subtasks,'has_deps':has_deps}]}
