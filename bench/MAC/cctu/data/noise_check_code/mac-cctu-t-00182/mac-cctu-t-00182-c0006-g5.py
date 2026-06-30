def evaluate(trace):
    import re
    text = trace.get('final_response','') or ''
    reasons = []
    issues = []
    # Find elevation mentions with units
    elev_pattern = re.compile(r'(\d[\d,\.]*)\s*(meters?|m\b|metres?|feet|ft\b|foot)', re.IGNORECASE)
    elev_matches = elev_pattern.findall(text)
    has_elev_context = bool(re.search(r'elevat|peak|mountain|altitude|summit|height', text, re.IGNORECASE))
    for val, unit in elev_matches:
        u = unit.lower()
        if u.startswith('f') or u == 'ft':
            issues.append(f'non-meter elevation unit: {val} {unit}')
    # Find sales figures
    has_sales_context = bool(re.search(r'sales|revenue|sold', text, re.IGNORECASE))
    sales_nums = []
    if has_sales_context:
        for m in re.finditer(r'\$?\s*([\d,]+(?:\.\d+)?)\s*(thousand|million|billion|k|m|bn)?', text, re.IGNORECASE):
            raw = m.group(1).replace(',','')
            try:
                num = float(raw)
            except:
                continue
            suffix = (m.group(2) or '').lower()
            if suffix in ('million','m','bn','billion'):
                continue  # likely already rounded at higher scale
            if suffix == 'thousand' or suffix == 'k':
                continue
            # Check context window
            start = max(0, m.start()-40)
            ctx = text[start:m.end()+20].lower()
            if not re.search(r'sale|revenue|sold|copies', ctx):
                continue
            if num >= 1000 and num % 1000 != 0:
                issues.append(f'sales not rounded to nearest thousand: {num}')
    if not has_elev_context and not has_sales_context:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no elevation or sales content detected','evidence_refs':[]}
    if issues:
        return {'observed_followed': False, 'confidence':'medium','reason':'; '.join(issues[:3]),'evidence_refs':[]}
    return {'observed_followed': True, 'confidence':'medium','reason':'elevations appear in meters and sales appear rounded to thousands','evidence_refs':[]}
