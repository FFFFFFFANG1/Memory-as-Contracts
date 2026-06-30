def evaluate(trace):
    import re
    allowed = 'tourism_statistics_tool'
    data_tools = {'celestial_discovery_info','flight_price_checker','historical_event_data_info_retriever','historical_event_finder','population_data_retriever','social_media_metrics_tool','space_mission_info_retriever'}
    calls = trace.get('tool_calls') or []
    used = [c.get('name') for c in calls]
    forbidden_used = [n for n in used if n in data_tools]
    if forbidden_used:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Used non-tourism data tools: {forbidden_used}', 'evidence_refs': []}
    final = trace.get('final_response') or ''
    nums = re.findall(r'(?<![\w.])(\d{1,3}(?:,\d{3})+|\d{4,})(?!\d)', final)
    if not nums:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No visitor count numbers detected in final response', 'evidence_refs': []}
    bad = []
    for n in nums:
        v = int(n.replace(',',''))
        if v % 1000 != 0:
            bad.append(n)
    if bad:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Numbers not rounded to nearest thousand: {bad}', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Only tourism_statistics_tool used and counts rounded to thousands', 'evidence_refs': []}
