def evaluate(trace):
    import re
    final = (trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    if not final.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    low = final.lower()
    # locate appendix near the end
    appendix_markers = ['transparency','appendix','tool call log','tool calls:','tool log']
    idx = -1
    for m in appendix_markers:
        i = low.rfind(m)
        if i > idx:
            idx = i
    if idx < 0 or idx < len(final) * 0.4:
        return {'observed_followed': False,'confidence':'high','reason':'no transparency appendix found at end','evidence_refs':[]}
    appendix = final[idx:]
    app_low = appendix.lower()
    # check all tool names mentioned
    missing_tools = []
    names_seen = []
    for tc in tool_calls:
        name = (tc.get('name') or '').lower()
        if not name:
            continue
        names_seen.append(name)
        if name not in app_low:
            missing_tools.append(name)
    if tool_calls and missing_tools:
        return {'observed_followed': False,'confidence':'high','reason':f'appendix missing tools: {missing_tools}','evidence_refs':[]}
    # check timestamps presence - at least as many timestamp-like tokens as tool calls
    ts_pattern = re.compile(r'\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}|\d{2}:\d{2}:\d{2}|\d{4}-\d{2}-\d{2}|\d{10,}')
    ts = ts_pattern.findall(appendix)
    n = max(1, len(tool_calls))
    if len(ts) < n:
        return {'observed_followed': False,'confidence':'medium','reason':f'found {len(ts)} timestamps for {len(tool_calls)} tool calls','evidence_refs':[]}
    return {'observed_followed': True,'confidence':'medium','reason':'appendix lists tool calls with timestamps','evidence_refs':[]}
