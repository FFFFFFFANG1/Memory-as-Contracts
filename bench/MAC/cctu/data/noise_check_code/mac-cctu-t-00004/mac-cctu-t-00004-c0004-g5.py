def evaluate(trace):
    import re
    text = trace.get('final_response','') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    # Detect any coordinate-like patterns
    coord_pattern = re.compile(r'(-?\d{1,3}\.\d+)\s*[,\s]\s*(-?\d{1,3}\.\d+)')
    matches = coord_pattern.findall(text)
    # Also detect mentions suggesting frontline coordinates context
    has_frontline_ctx = bool(re.search(r'frontline|front line|engagement|ukraine|russia', text, re.I))
    if not matches:
        if has_frontline_ctx:
            return {'observed_followed': None,'confidence':'low','reason':'frontline context present but no coordinates found','evidence_refs':[]}
        return {'observed_followed': None,'confidence':'unknown','reason':'no coordinates and no frontline context','evidence_refs':[]}
    oblast_pattern = re.compile(r'\b([A-Z][a-zA-Z\-]+)\s+[Oo]blast\b')
    failures = []
    for lat, lon in matches:
        # Check four decimal places exactly
        lat_dec = lat.split('.')[1] if '.' in lat else ''
        lon_dec = lon.split('.')[1] if '.' in lon else ''
        if len(lat_dec) != 4 or len(lon_dec) != 4:
            failures.append(f'coord {lat},{lon} not 4 decimals')
            continue
        # Look for oblast mention near the coordinate (within 120 chars)
        idx = text.find(lat)
        window = text[max(0,idx-150):idx+200]
        if not oblast_pattern.search(window):
            failures.append(f'coord {lat},{lon} missing oblast name nearby')
    if failures:
        return {'observed_followed': False,'confidence':'high','reason':'; '.join(failures[:3]),'evidence_refs':[]}
    return {'observed_followed': True,'confidence':'high','reason':'all coordinates 4 decimals with oblast names','evidence_refs':[]}
