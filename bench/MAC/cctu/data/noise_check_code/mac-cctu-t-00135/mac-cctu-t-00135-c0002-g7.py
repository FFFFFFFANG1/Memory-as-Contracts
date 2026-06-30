def evaluate(trace):
    import re
    final = trace.get('final_response','') or ''
    tool_calls = trace.get('tool_calls',[]) or []
    hist_tools = [tc.get('name','') for tc in tool_calls if 'historical' in (tc.get('name','') or '').lower() or 'merged_historical' in (tc.get('name','') or '').lower()]
    if not hist_tools:
        return {'observed_followed': None, 'confidence':'unknown','reason':'No historical retrieval tool calls found in trajectory','evidence_refs':[]}
    # find parenthetical annotations
    parens = re.findall(r'\(([^()]+)\)', final)
    if not parens:
        return {'observed_followed': False, 'confidence':'high','reason':'No parenthetical annotations found in final response despite historical tool calls','evidence_refs':[]}
    # Count annotations that include a historical tool name AND a timestamp-like token
    ts_pattern = re.compile(r'\d{1,4}[-:/T]\d{1,2}|\d{1,2}:\d{2}|\d{4}-\d{2}-\d{2}|UTC|GMT|\d{10,}')
    good = 0
    for p in parens:
        has_tool = any(t and t in p for t in hist_tools)
        has_ts = bool(ts_pattern.search(p))
        if has_tool and has_ts:
            good += 1
    if good == 0:
        return {'observed_followed': False,'confidence':'high','reason':'Parentheses present but none contain both a historical tool name and a retrieval timestamp','evidence_refs':[]}
    # Heuristic: at least one well-formed annotation per historical tool call
    expected = len(hist_tools)
    if good >= expected:
        return {'observed_followed': True,'confidence':'medium','reason':f'Found {good} annotations with tool name and timestamp covering {expected} historical calls','evidence_refs':[]}
    return {'observed_followed': False,'confidence':'medium','reason':f'Only {good} of {expected} historical retrievals appear annotated with tool name and timestamp','evidence_refs':[]}
