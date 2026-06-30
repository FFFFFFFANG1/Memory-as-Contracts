def evaluate(trace):
    import re
    text = trace.get('final_response','') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown', 'reason':'empty response', 'evidence_refs': []}
    # Detect any area measurement units
    non_km_pattern = re.compile(r'\b\d[\d,\.]*\s*(hectares?|ha\b|acres?|square\s+miles?|sq\.?\s*mi\b|mi²|square\s+meters?|sq\.?\s*m\b|m²)\b', re.IGNORECASE)
    non_km = non_km_pattern.findall(text)
    km_pattern = re.compile(r'(\b\d[\d,\.]*\s*(?:square\s+kilometers?|sq\.?\s*km|km²|km\^2))', re.IGNORECASE)
    km_matches = [(m.start(), m.group(1)) for m in km_pattern.finditer(text)]
    if not km_matches and not non_km:
        return {'observed_followed': None, 'confidence':'unknown', 'reason':'no park area measurements detected', 'evidence_refs': []}
    if non_km:
        return {'observed_followed': False, 'confidence':'high', 'reason': f'Found area measurements not in km²: {non_km[:3]}', 'evidence_refs':[str(non_km[:3])]}
    # For each km value, check IUCN citation within ~200 chars after
    iucn_re = re.compile(r'IUCN', re.IGNORECASE)
    missing = []
    for pos, val in km_matches:
        window = text[pos: pos+250]
        if not iucn_re.search(window):
            # also check just before
            pre = text[max(0,pos-100):pos]
            if not iucn_re.search(pre):
                missing.append(val)
    if missing:
        return {'observed_followed': False, 'confidence':'high', 'reason': f'km² values without nearby IUCN citation: {missing[:3]}', 'evidence_refs': missing[:3]}
    # Also check the citation mentions marine habitat registry at least once
    if not re.search(r'marine\s+habitat', text, re.IGNORECASE):
        return {'observed_followed': False, 'confidence':'medium', 'reason':'IUCN mentioned but not marine habitat registry', 'evidence_refs':[]}
    return {'observed_followed': True, 'confidence':'high', 'reason': f'{len(km_matches)} km² values each have IUCN marine habitat citation', 'evidence_refs':[v for _,v in km_matches[:3]]}
