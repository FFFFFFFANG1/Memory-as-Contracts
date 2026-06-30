def evaluate(trace):
    import re
    final = trace.get('final_response','') or ''
    if not final.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    # Detect foreign currency symbols/codes in final response
    foreign_patterns = [r'€', r'£', r'¥', r'₹', r'₽', r'₩', r'\bEUR\b', r'\bGBP\b', r'\bJPY\b', r'\bCNY\b', r'\bINR\b', r'\bRUB\b', r'\bKRW\b', r'\bAUD\b', r'\bCAD\b', r'\bCHF\b', r'\bMXN\b', r'\bBRL\b']
    foreign_hits = []
    for p in foreign_patterns:
        m = re.search(p, final)
        if m:
            foreign_hits.append(m.group(0))
    # Check USD amounts have two decimals
    usd_amounts = re.findall(r'\$\s?(\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)', final)
    bad_decimals = [a for a in usd_amounts if '.' not in a or len(a.split('.')[-1]) != 2]
    # Determine if there are any price-like values at all
    has_price_context = bool(usd_amounts) or bool(foreign_hits)
    if not has_price_context:
        return {'observed_followed': None,'confidence':'low','reason':'no price values found in final response','evidence_refs':[]}
    if foreign_hits:
        return {'observed_followed': False,'confidence':'medium','reason': f'foreign currency present in final response: {foreign_hits}','evidence_refs': foreign_hits}
    if bad_decimals:
        return {'observed_followed': False,'confidence':'medium','reason': f'USD amounts not in two decimal format: {bad_decimals}','evidence_refs': bad_decimals}
    return {'observed_followed': True,'confidence':'medium','reason':'all prices appear USD with two decimals and no foreign currency symbols','evidence_refs': usd_amounts[:5]}
