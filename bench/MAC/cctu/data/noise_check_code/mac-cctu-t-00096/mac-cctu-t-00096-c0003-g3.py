def evaluate(trace):
    import re
    tools = ['biographical_info_retriever','business_district_locator','business_locator','consulting_client_finder','corporate_housing_locator','cultural_heritage_folk_tale_finder','rental_price_analyzer','university_program_finder','urban_area_identifier']
    final = (trace.get('final_response') or '').lower()
    if not final:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    counts = {t: len(re.findall(re.escape(t), final)) for t in tools}
    missing = [t for t,c in counts.items() if c == 0]
    duplicated = [t for t,c in counts.items() if c > 1]
    tcs = trace.get('tool_calls') or []
    if missing:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'missing tools in report: {missing}', 'evidence_refs': []}
    if duplicated:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'tools listed more than once: {duplicated}', 'evidence_refs': []}
    if tcs:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'downstream tool chaining occurred ({len(tcs)} calls)', 'evidence_refs': [c.get('name') for c in tcs]}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'all tools enumerated once and no tool chaining', 'evidence_refs': []}
