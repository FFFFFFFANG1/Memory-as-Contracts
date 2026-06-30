def evaluate(trace):
    import re
    final = (trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    if not final.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    low = final.lower()
    # Detect appendix section
    has_appendix = bool(re.search(r'(reproducibility\s+appendix|appendix)', low))
    if not has_appendix:
        return {'observed_followed': False, 'confidence':'high','reason':'no reproducibility appendix found in final response','evidence_refs':[]}
    # Find appendix region
    m = re.search(r'(reproducibility\s+appendix|appendix)', low)
    appendix_text = final[m.start():] if m else final
    names = [tc.get('name','') for tc in tool_calls if tc.get('name')]
    if not names:
        # constraint says list every invocation; if none were made, an empty/absent list is acceptable if appendix exists
        return {'observed_followed': True, 'confidence':'low','reason':'appendix present; no tool calls to list','evidence_refs':[]}
    # Check each tool name appears in appendix
    missing = [n for n in names if n.lower() not in appendix_text.lower()]
    if missing:
        return {'observed_followed': False, 'confidence':'high','reason':f'appendix missing tool invocations: {missing}','evidence_refs':[]}
    # Check chronological order: indices of first occurrences should be non-decreasing matching call order
    positions = []
    cursor = 0
    ok_order = True
    text_l = appendix_text.lower()
    for n in names:
        idx = text_l.find(n.lower(), cursor)
        if idx == -1:
            # appears earlier than cursor -> out of order
            ok_order = False
            break
        positions.append(idx)
        cursor = idx + 1
    if not ok_order:
        return {'observed_followed': False, 'confidence':'medium','reason':'tool invocations not in chronological order in appendix','evidence_refs':[]}
    return {'observed_followed': True, 'confidence':'high','reason':'appendix lists all tool invocations in chronological order','evidence_refs':[]}
