def evaluate(trace):
    import re
    relevant = {'venue_information_retriever','cultural_landmark_locator'}
    calls = [c for c in trace.get('tool_calls',[]) if c.get('name') in relevant]
    if not calls:
        return {'observed_followed': None, 'confidence':'unknown','reason':'No venue/landmark tool calls','evidence_refs':[]}
    # Check if any results contain measurement-like data
    measurement_kw = re.compile(r'(meter|metre|\bm\b|\bcm\b|\bkm\b|foot|feet|\bft\b|inch|\bin\b|yard|mile|height|width|length|area|tall|high|square)', re.I)
    has_measurements = False
    for c in calls:
        res = str(c.get('result',''))
        if measurement_kw.search(res) and re.search(r'\d', res):
            has_measurements = True
            break
    if not has_measurements:
        return {'observed_followed': None,'confidence':'low','reason':'No architectural measurements detected in tool results','evidence_refs':[]}
    final = trace.get('final_response','') or ''
    metric_re = re.compile(r'\d+\s*(?:\.\d+)?\s*(meters?|metres?|m\b|cm\b|km\b|centimet|kilomet)', re.I)
    imperial_re = re.compile(r'\d+\s*(?:\.\d+)?\s*(feet|foot|ft\b|inch|inches|in\b|yards?|miles?)', re.I)
    has_metric = bool(metric_re.search(final))
    has_imperial = bool(imperial_re.search(final))
    if has_metric and has_imperial:
        return {'observed_followed': True,'confidence':'high','reason':'Final response contains both metric and imperial units','evidence_refs':[]}
    return {'observed_followed': False,'confidence':'medium','reason': f'metric={has_metric} imperial={has_imperial} in final response','evidence_refs':[]}
