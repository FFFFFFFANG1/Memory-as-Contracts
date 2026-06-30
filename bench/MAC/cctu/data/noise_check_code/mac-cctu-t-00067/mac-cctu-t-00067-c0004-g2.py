def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no tool calls','evidence_refs':[]}
    n = len(calls)
    first = calls[0].get('name')
    if n > 6:
        return {'observed_followed': False, 'confidence':'high','reason': f'{n} tool calls exceeds cap of 6','evidence_refs':[{'index':0,'name':first}]}
    if first != 'lake_feature_finder':
        return {'observed_followed': False, 'confidence':'medium','reason': f'first tool was {first}, not lake_feature_finder','evidence_refs':[{'index':0,'name':first}]}
    return {'observed_followed': True, 'confidence':'high','reason': f'{n} calls within cap and lake_feature_finder first','evidence_refs':[{'index':0,'name':first}]}
