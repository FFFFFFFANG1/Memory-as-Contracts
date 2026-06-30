def evaluate(trace):
    import re
    final=trace.get('final_response','') or ''
    tool_calls=trace.get('tool_calls',[]) or []
    used=[tc for tc in tool_calls if tc.get('name')=='mountain_peak_altitude_finder']
    if not used:
        return {'observed_followed': None, 'confidence':'unknown','reason':'No mountain_peak_altitude_finder calls; nothing to report.','evidence_refs':[]}
    # find altitude-like numbers in final response
    # match numbers followed by m or meters
    pattern=re.compile(r'(\d{1,3}(?:[,\s]?\d{3})*(?:\.\d+)?)\s*(m\b|meters\b|metres\b)', re.IGNORECASE)
    matches=pattern.findall(final)
    if not matches:
        return {'observed_followed': False,'confidence':'medium','reason':'No altitudes reported in meters in final response.','evidence_refs':[]}
    bad=[]
    for num,unit in matches:
        clean=num.replace(',','').replace(' ','')
        if '.' not in clean:
            bad.append(num+unit)
            continue
        dec=clean.split('.')[1]
        if len(dec)!=1:
            bad.append(num+unit)
    # check citation to the tool
    cite_present=('mountain_peak_altitude_finder' in final) or ('[mountain_peak_altitude_finder]' in final)
    if bad:
        return {'observed_followed': False,'confidence':'medium','reason':'Altitudes not at one-decimal meters: '+', '.join(bad),'evidence_refs':[]}
    if not cite_present:
        return {'observed_followed': False,'confidence':'medium','reason':'Missing citation to mountain_peak_altitude_finder tool.','evidence_refs':[]}
    return {'observed_followed': True,'confidence':'medium','reason':'Altitudes reported in meters with one-decimal precision and cite tool.','evidence_refs':[]}
