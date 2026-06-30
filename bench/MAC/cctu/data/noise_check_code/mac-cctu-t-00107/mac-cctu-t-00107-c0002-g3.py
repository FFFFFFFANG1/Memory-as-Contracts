def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    # Find first assistant message text before any tool call
    pre_text = ''
    first_tool_iter = None
    tool_calls = trace.get('tool_calls') or []
    if not tool_calls:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no tool calls to evaluate against','evidence_refs':[]}
    # determine earliest tool call position
    for step in traj:
        content = step.get('content') or ''
        tcs = step.get('tool_calls') or []
        if tcs:
            # check content of this same step counts as pre-text if before calls
            if content:
                pre_text += '\n' + content
            break
        if content:
            pre_text += '\n' + content
    if not pre_text.strip():
        return {'observed_followed': False,'confidence':'high','reason':'no decomposition text before tool calls','evidence_refs':[]}
    # detect numbered list items (1. or 1)) - at least 2 items
    items = re.findall(r'(?m)^\s*(\d+)[\.\)]\s+(.+)$', pre_text)
    if len(items) < 2:
        return {'observed_followed': False,'confidence':'medium','reason':'no explicit numbered sub-task list found before tool calls','evidence_refs':[]}
    # check each item references a tool name
    tools = ['aviation_incident_info_data_retriever','film_awards_merged_tool_v2','historical_event_finder','historical_event_retriever','hotel_cost_calculator','merged_tourism_analyzer','planetary_feature_analyzer','religious_text_info','unread_message_counter_v2']
    missing = []
    for num, text in items:
        low = text.lower()
        if not any(t in low for t in tools):
            missing.append(num)
    if missing:
        return {'observed_followed': False,'confidence':'medium','reason': f'sub-tasks {missing} lack assigned tool name','evidence_refs':[]}
    return {'observed_followed': True,'confidence':'high','reason':'numbered sub-task list with tools present before tool calls','evidence_refs':[]}
