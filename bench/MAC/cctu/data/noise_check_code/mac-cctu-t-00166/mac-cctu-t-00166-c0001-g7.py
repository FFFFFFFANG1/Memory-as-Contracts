def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    tool_calls = trace.get('tool_calls') or []
    if not tool_calls:
        return {'observed_followed': None, 'confidence':'unknown','reason':'No tool calls found to evaluate logging.','evidence_refs':[]}
    used_tools = []
    for tc in tool_calls:
        n = tc.get('name')
        if n and n not in used_tools:
            used_tools.append(n)
    # Gather all assistant textual content
    texts = []
    for step in traj:
        c = step.get('content')
        if isinstance(c, str) and c.strip():
            texts.append(c)
    final = trace.get('final_response') or ''
    combined = '\n'.join(texts) + '\n' + final
    low = combined.lower()
    worksheet_markers = ['worksheet','draft worksheet','log','source log','source-gathering','sources:','source list','citations','citation log']
    has_worksheet = any(m in low for m in worksheet_markers)
    # Check tool names appear in assistant content (logging with originating tool name)
    logged = [t for t in used_tools if t.lower() in low]
    ratio = len(logged)/len(used_tools) if used_tools else 0
    if has_worksheet and ratio >= 0.8:
        return {'observed_followed': True,'confidence':'medium','reason':f'Worksheet markers found and {len(logged)}/{len(used_tools)} tool names logged.','evidence_refs':[]}
    if ratio >= 0.8:
        return {'observed_followed': True,'confidence':'low','reason':f'Tool names logged ({len(logged)}/{len(used_tools)}) but no explicit worksheet marker.','evidence_refs':[]}
    if ratio == 0 and not has_worksheet:
        return {'observed_followed': False,'confidence':'medium','reason':'No worksheet or tool-name attribution found in assistant content.','evidence_refs':[]}
    return {'observed_followed': False,'confidence':'low','reason':f'Only {len(logged)}/{len(used_tools)} tool names attributed; worksheet={has_worksheet}.','evidence_refs':[]}
