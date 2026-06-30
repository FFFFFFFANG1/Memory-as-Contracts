def evaluate(trace):
    calls = trace.get('tool_calls', []) or []
    if not calls:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no tool calls found','evidence_refs':[]}
    target = 'unified_population_data_retriever'
    other = [c for c in calls if c.get('name') != target]
    target_calls = [c for c in calls if c.get('name') == target]
    if other:
        names = sorted({c.get('name') for c in other})
        return {'observed_followed': False, 'confidence':'high','reason':f'used non-target tools: {names}','evidence_refs':[c.get('name') for c in other]}
    turns = set()
    for c in target_calls:
        t = c.get('iteration')
        if t is None:
            t = c.get('turn')
        if t is not None:
            turns.add(t)
    if not turns:
        return {'observed_followed': None,'confidence':'unknown','reason':'no turn/iteration info on calls','evidence_refs':[]}
    if len(turns) >= 4:
        return {'observed_followed': True,'confidence':'high','reason':f'{len(target_calls)} calls to {target} across {len(turns)} distinct turns','evidence_refs':sorted(turns)}
    return {'observed_followed': False,'confidence':'high','reason':f'only {len(turns)} distinct turns (<4) for retrievals','evidence_refs':sorted(turns)}
