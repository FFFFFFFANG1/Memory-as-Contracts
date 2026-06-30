def evaluate(trace):
    import re
    text = trace.get('final_response') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty final response', 'evidence_refs': []}
    # Coordinate patterns: decimal degrees like 12.34°N, 56.78°W or 12.34, -56.78 with N/S/E/W; or DMS
    patterns = [
        r'-?\d{1,3}\.\d+\s*°?\s*[NS]\s*[,;/]?\s*-?\d{1,3}\.\d+\s*°?\s*[EW]',
        r'\d{1,3}°\s*\d{1,2}[\'′]?\s*(?:\d{1,2}(?:\.\d+)?["″]?)?\s*[NS][\s,;]+\d{1,3}°\s*\d{1,2}[\'′]?\s*(?:\d{1,2}(?:\.\d+)?["″]?)?\s*[EW]',
        r'\(\s*-?\d{1,3}\.\d+\s*,\s*-?\d{1,3}\.\d+\s*\)',
        r'latitude\s*[:=]?\s*-?\d{1,3}\.\d+.*longitude\s*[:=]?\s*-?\d{1,3}\.\d+',
    ]
    has_coords = any(re.search(p, text, re.IGNORECASE | re.DOTALL) for p in patterns)
    has_number = bool(re.search(r'\d', text))
    if has_coords and has_number:
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'coordinates and numeric result present', 'evidence_refs': []}
    if not has_coords:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'no geographic coordinates detected in final response', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'low', 'reason': 'missing numeric result', 'evidence_refs': []}
