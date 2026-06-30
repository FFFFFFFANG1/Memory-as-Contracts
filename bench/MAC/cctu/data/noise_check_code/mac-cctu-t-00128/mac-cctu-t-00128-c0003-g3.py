def evaluate(trace):
    import re
    text = (trace.get('final_response') or '')
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    low = text.lower()
    # Detect depth comparison context
    depth_terms = ['deep','depth','shallow','deeper','shallower','below','seafloor','bathymetr']
    comp_terms = ['than','compared','vs','versus','more','less','greater','exceeds']
    has_depth = any(t in low for t in depth_terms)
    has_comp = any(t in low for t in comp_terms)
    # Numeric value present?
    has_num = bool(re.search(r'\d', text))
    if not (has_depth and has_num):
        return {'observed_followed': None,'confidence':'low','reason':'no depth comparison detected in response','evidence_refs':[]}
    # Check fathoms unit
    fathom_used = 'fathom' in low
    # Check other units that would violate (meters/feet) for depth
    other_unit = bool(re.search(r'\b(meters?|metres?|m\b|feet|ft\b|km|kilometers?)\b', low))
    # Check sonar-track citation
    sonar_cite = ('sonar' in low) and ('track' in low or 'citation' in low or 'cite' in low or 'ref' in low or '[' in text)
    followed = fathom_used and sonar_cite and not (other_unit and not fathom_used)
    # If fathoms present along with other units, still acceptable if comparisons themselves in fathoms; heuristic
    if fathom_used and sonar_cite:
        return {'observed_followed': True,'confidence':'medium','reason':'fathoms and sonar-track citation present','evidence_refs':[]}
    return {'observed_followed': False,'confidence':'medium','reason': f'fathoms={fathom_used}, sonar_citation={sonar_cite}','evidence_refs':[]}
