def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no tool calls','evidence_refs':[]}
    names = [c.get('name') for c in calls]
    bfa = [i for i,n in enumerate(names) if n=='bank_failure_analyzer']
    others = [i for i,n in enumerate(names) if n and n!='bank_failure_analyzer']
    if not bfa:
        return {'observed_followed': False,'confidence':'high','reason':'bank_failure_analyzer not used as primary source','evidence_refs':names}
    if not others:
        return {'observed_followed': False,'confidence':'high','reason':'no secondary tool call to corroborate findings','evidence_refs':names}
    # primary check: bfa should appear at or before some secondary corroboration
    if min(bfa) > min(others):
        return {'observed_followed': None,'confidence':'low','reason':'bank_failure_analyzer not used first; unclear if primary','evidence_refs':names}
    return {'observed_followed': True,'confidence':'medium','reason':'bank_failure_analyzer used with at least one secondary tool','evidence_refs':names}
