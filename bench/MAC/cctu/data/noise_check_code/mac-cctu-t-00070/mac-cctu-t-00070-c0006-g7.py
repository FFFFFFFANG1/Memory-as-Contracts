def evaluate(trace):
    import re
    text = trace.get('final_response') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    loc_pattern = re.compile(r'\b([A-Z][\w\-\']+(?:\s+[A-Z][\w\-\']+)*)\s+(Reef|Atoll|Lagoon|Cay|Shoal|Bank|Coast|Beach|Bay|Island|Islands)\b')
    locations = loc_pattern.findall(text)
    keyword_hits = re.findall(r'\b(reef|atoll|coastal|coast|locality|localities)\b', text, re.I)
    coord_pattern = re.compile(r'-?\d{1,3}\.\d+\s*[°�]?\s*[NSns]?[,;\s]+-?\d{1,3}\.\d+\s*[°�]?\s*[EWew]?')
    coords = coord_pattern.findall(text)
    if not locations and not keyword_hits:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no reef/atoll/coastal locality mentions detected', 'evidence_refs': []}
    if not coords:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Found {len(locations)} location mentions but no decimal-degree coordinates', 'evidence_refs': [str(locations[:5])]}
    if len(coords) < max(1, len(locations)):
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'{len(locations)} locations cited but only {len(coords)} coordinate pairs found', 'evidence_refs': [str(locations[:5]), str(coords[:5])]}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': f'{len(coords)} decimal-degree coordinate pairs cover {len(locations)} locations', 'evidence_refs': [str(coords[:5])]}
