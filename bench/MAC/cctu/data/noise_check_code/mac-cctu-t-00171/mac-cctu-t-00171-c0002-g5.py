def evaluate(trace):
    allowed = {'bibliographic_search_tool','biographical_info_retriever'}
    all_tools = {'artwork_artist_identifier','bibliographic_search_tool','biographical_info_retriever','biographical_residence_finder','historical_geography_associator','museum_dedication_finder','population_data_retriever','sports_award_tracker','tallest_building_finder','venue_capacity_checker'}
    forbidden = all_tools - allowed
    used = [tc.get('name') for tc in trace.get('tool_calls',[]) if tc.get('name')]
    bad = [t for t in used if t in forbidden]
    if bad:
        return {'observed_followed': False, 'confidence':'high', 'reason': f'Used forbidden tools: {sorted(set(bad))}', 'evidence_refs': []}
    resp = (trace.get('final_response') or '').lower()
    if not resp.strip():
        return {'observed_followed': None, 'confidence':'unknown', 'reason':'no final response', 'evidence_refs': []}
    import re
    # Look for annotated bibliography signals
    biblio_terms = ['bibliography','annotated','works cited','references','source','book','author','publish']
    biblio_hits = sum(1 for t in biblio_terms if t in resp)
    # Detect numeric comparison patterns (e.g., 'taller than', 'larger than', 'X vs Y', explicit numeric comparisons)
    cmp_patterns = [r'\btaller than\b', r'\bshorter than\b', r'\blarger than\b', r'\bsmaller than\b', r'\bmore than\b.*\d', r'\bless than\b.*\d', r'\bvs\.?\b', r'\bcompared to\b.*\d']
    cmp_hit = any(re.search(p, resp) for p in cmp_patterns)
    if biblio_hits >= 2 and not cmp_hit:
        return {'observed_followed': True, 'confidence':'medium', 'reason':'annotated bibliography signals present and no numeric comparison', 'evidence_refs': []}
    if cmp_hit:
        return {'observed_followed': False, 'confidence':'medium', 'reason':'response contains numeric comparison language', 'evidence_refs': []}
    return {'observed_followed': None, 'confidence':'low', 'reason':'insufficient bibliography signals to confirm', 'evidence_refs': []}
