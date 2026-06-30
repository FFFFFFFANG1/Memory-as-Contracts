def evaluate(trace):
    final = (trace.get('final_response') or '').lstrip()
    tool_calls = trace.get('tool_calls') or []
    forbidden = {'population_estimator','river_length_calculator'}
    used = [tc.get('name') for tc in tool_calls if tc.get('name') in forbidden]
    starts_ok = final.startswith('DRAFT:')
    if not final and not tool_calls:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no evidence','evidence_refs':[]}
    if used:
        return {'observed_followed': False, 'confidence':'high','reason': f'forbidden quantitative tools invoked: {used}','evidence_refs': used}
    if not starts_ok:
        return {'observed_followed': False, 'confidence':'high','reason': 'final response does not begin with literal token DRAFT:','evidence_refs':[final[:40]]}
    return {'observed_followed': True,'confidence':'high','reason':'starts with DRAFT: and no forbidden quantitative tools invoked','evidence_refs':[]}
