def evaluate(trace):
    calls = trace.get('tool_calls') or []
    names = [c.get('name') for c in calls]
    if not names:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no tool calls','evidence_refs':[]}
    if 'volcano_activity_analyzer' not in names:
        return {'observed_followed': False,'confidence':'high','reason':'volcano_activity_analyzer not used','evidence_refs':[{'tool_calls':names}]}
    first_volcano_idx = names.index('volcano_activity_analyzer')
    others_before = [n for n in names[:first_volcano_idx] if n != 'volcano_activity_analyzer']
    primary_ok = first_volcano_idx == 0 or len(others_before) == 0
    distinct_others = set(n for n in names if n and n != 'volcano_activity_analyzer')
    cross_checked = len(distinct_others) >= 1
    final = (trace.get('final_response') or '').lower()
    mentions_casualty = any(k in final for k in ['casualt','killed','death','fatalit','victim'])
    if not mentions_casualty:
        return {'observed_followed': None,'confidence':'low','reason':'no casualty figure mentioned in final response; cannot verify cross-check','evidence_refs':[{'tools':names}]}
    followed = primary_ok and cross_checked
    return {'observed_followed': followed,'confidence':'medium' if followed else 'high','reason':f'primary_volcano={primary_ok}, cross_check_tools={sorted(distinct_others)}','evidence_refs':[{'tool_sequence':names}]}
