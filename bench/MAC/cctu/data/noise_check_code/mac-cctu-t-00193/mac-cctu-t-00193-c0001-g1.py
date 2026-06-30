def evaluate(trace):
    import re
    tools = ['event_city_locator','event_metric_finder','landmark_info_retriever','literary_influence_finder','memorial_locator','patent_search_tool','person_profession_locator','population_data_retriever','region_highlight_locator','structure_info_retriever','war_hero_identifier']
    resp = (trace.get('final_response') or '').strip()
    if not resp:
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    lines = [ln for ln in resp.splitlines() if ln.strip()]
    if not lines:
        return {'observed_followed': None,'confidence':'unknown','reason':'no content lines','evidence_refs':[]}
    pat = re.compile(r'^\s*\[([a-z_][a-z0-9_]*)\]\s+\S')
    bad = []
    good = 0
    for ln in lines:
        m = pat.match(ln)
        if m and m.group(1) in tools:
            good += 1
        else:
            bad.append(ln[:80])
    if good == 0:
        return {'observed_followed': False,'confidence':'high','reason':'no lines have bracketed tool prefix','evidence_refs': bad[:3]}
    if bad:
        return {'observed_followed': False,'confidence':'medium','reason': f'{len(bad)} of {len(lines)} lines lack proper [tool] prefix','evidence_refs': bad[:3]}
    return {'observed_followed': True,'confidence':'high','reason': f'all {len(lines)} lines prefixed with valid tool name','evidence_refs':[]}
