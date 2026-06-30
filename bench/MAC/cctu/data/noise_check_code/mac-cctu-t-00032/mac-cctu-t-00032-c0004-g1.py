def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    if not traj:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no trajectory','evidence_refs':[]}
    # find first assistant step
    first_plan = None
    first_plan_idx = None
    first_tool_idx = None
    for i, step in enumerate(traj):
        tcs = step.get('tool_calls') or []
        content = step.get('content') or ''
        if first_plan is None and content.strip():
            first_plan = content
            first_plan_idx = i
        if tcs:
            first_tool_idx = i
            break
    if first_plan is None:
        return {'observed_followed': False,'confidence':'high','reason':'no plan text before tool calls','evidence_refs':[]}
    if first_tool_idx is not None and first_plan_idx is not None and first_plan_idx > first_tool_idx:
        return {'observed_followed': False,'confidence':'high','reason':'tool invoked before any plan','evidence_refs':[]}
    # check numbered list (at least 2 numbered items)
    nums = re.findall(r'(?m)^\s*(\d+)[\.\)]\s+\S', first_plan)
    has_numbered = len(nums) >= 2
    # check tools mentioned in plan
    tools = ['election_data_retriever','election_result_finder','election_result_finder_v2','international_event_finder','legislative_action_retriever','political_event_info_retriever','treaty_signatories_checker']
    mentioned = [t for t in tools if t.lower() in first_plan.lower()]
    # also accept generic word 'tool' references mapped per item
    has_tool_mapping = len(mentioned) >= 1 or bool(re.search(r'tool', first_plan, re.I))
    if has_numbered and has_tool_mapping:
        return {'observed_followed': True,'confidence':'medium','reason':'numbered decomposition with tool assignments found before tool calls','evidence_refs':[]}
    if not has_numbered:
        return {'observed_followed': False,'confidence':'medium','reason':'no numbered decomposition found in initial plan','evidence_refs':[]}
    return {'observed_followed': False,'confidence':'medium','reason':'plan lacks tool-to-subtask mapping','evidence_refs':[]}
