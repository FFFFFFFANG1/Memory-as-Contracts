def evaluate(trace):
    calls = [c for c in trace.get('tool_calls',[]) if c.get('name')=='organization_establishment_tracker_analyzer_v2']
    if len(calls) < 2:
        return {'observed_followed': False, 'confidence':'high','reason':f'Tool called {len(calls)} times; need >=2','evidence_refs':[]}
    phrasings = []
    for c in calls:
        args = c.get('arguments') or {}
        if isinstance(args, dict):
            q = ' '.join(str(v) for v in args.values() if isinstance(v,(str,int,float)))
        else:
            q = str(args)
        phrasings.append(q.strip().lower())
    distinct = set(phrasings)
    if len(distinct) < 2:
        return {'observed_followed': False,'confidence':'high','reason':'Calls used identical query phrasings','evidence_refs': phrasings}
    return {'observed_followed': True,'confidence':'medium','reason':f'{len(calls)} calls with {len(distinct)} distinct phrasings','evidence_refs': list(distinct)}
