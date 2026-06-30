def evaluate(trace):
    import re
    tools = ['event_locator','museum_exhibit_locator','historical_artisan_finder','historical_site_finder','altitude_finder','bird_characteristic_finder','car_design_influence_finder','car_specification_retriever']
    calls = trace.get('tool_calls') or []
    total = len(calls)
    per = {}
    for c in calls:
        n = c.get('name')
        per[n] = per.get(n,0)+1
    traj = trace.get('trajectory') or []
    rounds = len(traj)
    final = (trace.get('final_response') or '').rstrip()
    reasons = []
    ok = True
    if total > 25:
        ok = False; reasons.append(f'total tool calls {total} > 25')
    for t in tools:
        if per.get(t,0) > 4:
            ok = False; reasons.append(f'{t} called {per[t]} times > 4')
    if rounds > 24:
        ok = False; reasons.append(f'rounds {rounds} > 24')
    if not final.endswith('[Done]'):
        ok = False; reasons.append('final response does not end with [Done]')
    return {'observed_followed': ok, 'confidence': 'high', 'reason': '; '.join(reasons) if reasons else 'all checks passed', 'evidence_refs': []}
