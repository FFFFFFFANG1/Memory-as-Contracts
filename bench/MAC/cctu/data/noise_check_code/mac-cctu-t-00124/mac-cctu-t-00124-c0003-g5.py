def evaluate(trace):
    import re
    text = (trace.get('final_response') or '')
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    low = text.lower()
    # Detect any evacuation window calculation discussion
    if 'evacuation' not in low and 'evacuate' not in low:
        return {'observed_followed': None,'confidence':'unknown','reason':'no evacuation window discussed','evidence_refs':[]}
    has_hours = bool(re.search(r'\b\d+(?:\.\d+)?\s*(hours?|hrs?|h)\b', low))
    # days usage in evacuation context (forbidden)
    days_used = bool(re.search(r'\b\d+(?:\.\d+)?\s*(days?|d)\b', low))
    map_ref = bool(re.search(r'hazard[- ]zone\s*map|hazard map|zone map', low))
    followed = has_hours and not days_used and map_ref
    reason = f'hours={has_hours}, days_used={days_used}, hazard_map_ref={map_ref}'
    return {'observed_followed': bool(followed), 'confidence': 'high' if (has_hours or days_used or map_ref) else 'low', 'reason': reason, 'evidence_refs': []}
