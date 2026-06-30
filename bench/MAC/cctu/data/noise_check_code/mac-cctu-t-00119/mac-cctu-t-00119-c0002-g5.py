def evaluate(trace):
    import re
    text = (trace.get('final_response') or '')
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    # Find gas price mentions
    price_pattern = re.compile(r'(?i)(?:gas\s+price|price)[^.\n]{0,80}?\d')
    has_price = bool(re.search(r'(?i)gas', text)) and bool(re.search(r'\d', text))
    if not has_price:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no gas price found','evidence_refs':[]}
    # Check EUR/MWh unit near numbers
    unit_re = re.compile(r'(?i)(€\s*/\s*MWh|EUR\s*/\s*MWh|euros?\s*per\s*megawatt[- ]?hour)')
    ttf_re = re.compile(r'(?i)TTF')
    # Find all numeric price tokens
    nums = re.findall(r'\d+(?:[.,]\d+)?\s*(?:€|EUR|euro|euros|\$|USD|/MWh|per\s*MWh)?', text)
    unit_ok = bool(unit_re.search(text))
    ttf_ok = bool(ttf_re.search(text))
    # Check for forbidden units (other currencies/units suggesting violation)
    bad_unit = re.search(r'(?i)(\$|USD|GBP|£)\s*/?\s*(MWh|MMBtu|therm)?|/\s*MMBtu|per\s*therm', text)
    followed = unit_ok and ttf_ok and not bad_unit
    reason = f'unit_eur_mwh={unit_ok}, ttf_mentioned={ttf_ok}, other_units_present={bool(bad_unit)}'
    return {'observed_followed': bool(followed), 'confidence':'medium','reason':reason,'evidence_refs':[]}
