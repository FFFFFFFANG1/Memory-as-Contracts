def evaluate(trace):
    import re
    text = trace.get('final_response','') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    # Find coordinate-like patterns: pairs of decimal numbers, possibly with N/S/E/W
    coord_pair = re.compile(r'(-?\d{1,3}\.\d+)\s*[°]?\s*[NSns]?[,\s/;]+\s*(-?\d{1,3}\.\d+)\s*[°]?\s*[EWew]?')
    matches = coord_pair.findall(text)
    if not matches:
        return {'observed_followed': False, 'confidence':'high','reason':'no latitude/longitude coordinate pairs found in final response','evidence_refs':[]}
    bad = []
    for lat, lon in matches:
        lat_dec = lat.split('.')[1] if '.' in lat else ''
        lon_dec = lon.split('.')[1] if '.' in lon else ''
        if len(lat_dec) != 4 or len(lon_dec) != 4:
            bad.append((lat, lon))
    if bad:
        return {'observed_followed': False, 'confidence':'high','reason':f'coordinate pairs not rounded to 4 decimals: {bad[:3]}','evidence_refs':[]}
    return {'observed_followed': True, 'confidence':'medium','reason':f'found {len(matches)} coordinate pair(s) all with 4 decimal places','evidence_refs':[]}
