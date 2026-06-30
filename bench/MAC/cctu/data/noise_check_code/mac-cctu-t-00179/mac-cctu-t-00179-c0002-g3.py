def evaluate(trace):
    response = str(trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    if not response.strip() and not tool_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no observable behavior', 'evidence_refs': []}
    reasons = []
    tool_names = [str(call.get('name') or '') for call in tool_calls if call.get('name')]
    called = {name for name in tool_names if name}
    required_tools = ['architectural_designer_finder', 'city_area_calculator']
    missing = sorted(t for t in required_tools if t not in called)
    if missing:
        reasons.append('required tools not called: ' + ', '.join(missing[:5]))
    forbidden_tools = ['biodiversity_database', 'satellite_info_retriever', 'academic_paper_finder', 'biographical_info_retriever', 'capital_city_lookup', 'innovation_country_identifier', 'organization_locator', 'research_location_identifier', 'sports_venue_info']
    forbidden_used = sorted(t for t in forbidden_tools if t in called)
    if forbidden_used:
        reasons.append('forbidden tools called: ' + ', '.join(forbidden_used[:5]))
    if reasons:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'rule-based repair checks passed', 'evidence_refs': []}
