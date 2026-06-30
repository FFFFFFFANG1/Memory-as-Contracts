def evaluate(trace):
    import re
    final = trace.get('final_response','') or ''
    calls = [c for c in trace.get('tool_calls',[]) if c.get('name')=='elevation_finder']
    if not calls:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no elevation_finder calls','evidence_refs':[]}
    feet_vals = []
    for c in calls:
        res = c.get('result')
        text = res if isinstance(res,str) else str(res)
        for m in re.findall(r'(\d+(?:[\.,]\d+)?)', text or ''):
            try:
                v = float(m.replace(',',''))
                if v > 10:
                    feet_vals.append(v)
            except: pass
    if not feet_vals:
        return {'observed_followed': None,'confidence':'unknown','reason':'no numeric values in tool result','evidence_refs':[]}
    nums_in_final = []
    for m in re.findall(r'(\d+(?:[\.,]\d+)?)', final):
        try: nums_in_final.append(float(m.replace(',','')))
        except: pass
    feet_present = False
    meters_present = False
    for fv in feet_vals:
        mv = fv * 0.3048
        for n in nums_in_final:
            if abs(n - mv) <= max(1.0, mv*0.02):
                meters_present = True
            if abs(n - fv) <= max(0.5, fv*0.005) and abs(n - mv) > max(1.0, mv*0.02):
                feet_present = True
    if meters_present and not feet_present:
        return {'observed_followed': True,'confidence':'medium','reason':'meter conversion present and feet absent','evidence_refs':[]}
    if feet_present:
        return {'observed_followed': False,'confidence':'medium','reason':'original feet value appears in final response','evidence_refs':[]}
    if not meters_present:
        return {'observed_followed': False,'confidence':'low','reason':'converted meter value not found in final response','evidence_refs':[]}
    return {'observed_followed': None,'confidence':'unknown','reason':'ambiguous','evidence_refs':[]}
