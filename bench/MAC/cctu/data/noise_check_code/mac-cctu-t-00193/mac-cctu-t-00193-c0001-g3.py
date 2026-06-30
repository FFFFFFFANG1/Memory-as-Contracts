def evaluate(trace):
    import re
    text = trace.get('final_response','') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    # find metric measurements (meters)
    metric_pat = re.compile(r'(\d[\d,\.]*)\s*(m|meters|metres|meter|metre)\b', re.IGNORECASE)
    feet_pat = re.compile(r'(\d[\d,\.]*)\s*(ft|feet|foot|\u2032)\b', re.IGNORECASE)
    metrics = list(metric_pat.finditer(text))
    feets = list(feet_pat.finditer(text))
    if not metrics and not feets:
        return {'observed_followed': None,'confidence':'unknown','reason':'no measurements detected','evidence_refs':[]}
    # Required format: feet first, metric in parentheses
    # Pattern: <num> ft|feet (<num> m|meters)
    combo_pat = re.compile(r'\d[\d,\.]*\s*(?:ft|feet|foot)\b[^()]{0,20}\(\s*\d[\d,\.]*\s*(?:m|meters|metres|meter|metre)\b[^)]*\)', re.IGNORECASE)
    combos = combo_pat.findall(text)
    # Check each metric measurement - is it inside parentheses preceded by feet?
    violations = []
    for m in metrics:
        start = m.start()
        # look back ~40 chars for an opening paren preceded by feet
        before = text[max(0,start-60):start]
        if not re.search(r'(?:ft|feet|foot|\u2032)\b[^()]{0,20}\(\s*$', before, re.IGNORECASE):
            # this metric is not in proper parenthetical after feet
            violations.append(m.group(0))
    # Check each feet measurement has a paren with metric after
    for f in feets:
        end = f.end()
        after = text[end:end+40]
        if not re.search(r'^\s*\(\s*\d[\d,\.]*\s*(?:m|meters|metres|meter|metre)\b', after, re.IGNORECASE):
            violations.append(f.group(0))
    if violations:
        return {'observed_followed': False,'confidence':'medium','reason': f'Measurements not in required feet (metric) format: {violations[:3]}','evidence_refs':[]}
    if combos:
        return {'observed_followed': True,'confidence':'high','reason':'feet with metric in parentheses found','evidence_refs':[combos[0]]}
    return {'observed_followed': None,'confidence':'unknown','reason':'unable to verify','evidence_refs':[]}
