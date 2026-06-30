def evaluate(trace):
    import re
    final = trace.get('final_response','') or ''
    tcs = trace.get('tool_calls', []) or []
    bac = [t for t in tcs if t.get('name')=='building_area_calculator']
    asl = [t for t in tcs if t.get('name')=='architectural_style_locator']
    if not bac:
        return {'observed_followed': None, 'confidence':'unknown','reason':'building_area_calculator not used','evidence_refs':[]}
    # Look for numeric area mentions in final response with two decimals and sq meters unit
    pattern = re.compile(r'\d+\.\d{2}\s*(?:m\xb2|m2|sq(?:uare)?\s*met(?:er|re)s?)', re.IGNORECASE)
    matches = pattern.findall(final)
    # Detect any area number that doesn't follow the format
    bad_unit = re.search(r'\d+(?:\.\d+)?\s*(?:ft\xb2|sq\s*ft|square\s*feet|hectares?|acres?)', final, re.IGNORECASE)
    has_style = bool(asl) and any(re.search(r'style|architect', final, re.IGNORECASE) for _ in [0])
    if bad_unit:
        return {'observed_followed': False, 'confidence':'high','reason':'non-square-meter unit used','evidence_refs':[bad_unit.group(0)]}
    if not matches:
        return {'observed_followed': False, 'confidence':'medium','reason':'no area reported with two-decimal square meters','evidence_refs':[]}
    # Check decimals exactly two
    for m in matches:
        num = re.match(r'(\d+\.(\d+))', m)
        if num and len(num.group(2)) != 2:
            return {'observed_followed': False,'confidence':'high','reason':'decimal places not two','evidence_refs':[m]}
    if not has_style:
        return {'observed_followed': False,'confidence':'medium','reason':'missing architectural style annotation','evidence_refs':[]}
    return {'observed_followed': True,'confidence':'medium','reason':'area in m^2 with two decimals and style annotation present','evidence_refs': matches[:3]}
