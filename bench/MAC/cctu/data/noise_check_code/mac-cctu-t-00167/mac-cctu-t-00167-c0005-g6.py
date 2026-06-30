def evaluate(trace):
    import re
    text = trace.get('final_response','') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    imperial = ['miles','mile','mi','feet','foot','ft','inches','inch','yards','yard','yd','pounds','pound','lbs','lb','ounces','ounce','oz','fahrenheit','°f','acres','acre','gallons','gallon']
    low = text.lower()
    found_imp = [u for u in imperial if re.search(r'\b'+re.escape(u)+r'\b', low)]
    if found_imp:
        return {'observed_followed': False,'confidence':'high','reason':f'imperial units present: {found_imp}','evidence_refs':[text[:200]]}
    metric_units = ['km','m','cm','mm','kg','g','mg','l','ml','ha','°c','c','ms','s']
    pattern = re.compile(r'(\d+(?:[\.,]\d+)?)(\s*)([a-zA-Z°]+)')
    comparatives = ['than','more','less','larger','smaller','bigger','greater','taller','shorter','longer','wider','heavier','lighter','vs','compared','versus']
    has_comparative = any(w in low for w in comparatives)
    if not has_comparative:
        return {'observed_followed': None,'confidence':'low','reason':'no comparative context detected','evidence_refs':[]}
    violations = []
    for m in pattern.finditer(text):
        num, ws, unit = m.group(1), m.group(2), m.group(3)
        u = unit.lower().rstrip('.,;:)')
        if u in metric_units or u.startswith('°c'):
            if ws:
                violations.append(m.group(0))
    if violations:
        return {'observed_followed': False,'confidence':'high','reason':f'whitespace between numeral and unit: {violations[:5]}','evidence_refs':violations[:5]}
    return {'observed_followed': True,'confidence':'medium','reason':'metric units used and no whitespace before unit symbol','evidence_refs':[]}
