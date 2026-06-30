def evaluate(trace):
    import re
    text = trace.get('final_response') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    # Find numbers in the response
    nums = re.findall(r'(?<![\w.])-?\d+(?:[.,]\d+)?(?![\w])', text)
    if not nums:
        return {'observed_followed': None, 'confidence':'low','reason':'no numerical answers found','evidence_refs':[]}
    metric_units = ['m','km','cm','mm','kg','g','t','m2','km2','m3','km3','m²','km²','m³','km³','meter','meters','metre','metres','kilometer','kilometers','kilometre','kilometres']
    imperial = ['ft','feet','foot','mile','miles','yd','yard','yards','inch','inches','lb','lbs','pound']
    low = text.lower()
    has_imperial = any(re.search(r'\b'+u+r'\b', low) for u in imperial)
    # Check 2-decimal formatting for numeric values that look like measurements
    measurement_pattern = re.compile(r'(-?\d+(?:\.\d+)?)\s*(m|km|cm|mm|kg|t|m²|km²|m³|km³|meters?|metres?|kilometers?|kilometres?)\b', re.IGNORECASE)
    measurements = measurement_pattern.findall(text)
    if not measurements:
        return {'observed_followed': False, 'confidence':'medium','reason':'no metric-unit measurements detected for numerical answers','evidence_refs':[text[:200]]}
    bad_decimals = [m for m in measurements if '.' not in m[0] or len(m[0].split('.')[1]) != 2]
    # Check for catalog identifier - typically alphanumeric code
    has_catalog_id = bool(re.search(r'\b[A-Z]{2,}[-_]?\d+\b|\bcatalog\s*(id|identifier|number)\b|\bID[:\s]', text, re.IGNORECASE))
    issues = []
    if has_imperial:
        issues.append('imperial units present')
    if bad_decimals:
        issues.append(f'{len(bad_decimals)} measurements not at exactly 2 decimals')
    if not has_catalog_id:
        issues.append('no catalog identifier detected')
    if issues:
        return {'observed_followed': False, 'confidence':'medium','reason':'; '.join(issues),'evidence_refs':[text[:300]]}
    return {'observed_followed': True, 'confidence':'medium','reason':'metric units with 2 decimals and catalog id present','evidence_refs':[text[:200]]}
