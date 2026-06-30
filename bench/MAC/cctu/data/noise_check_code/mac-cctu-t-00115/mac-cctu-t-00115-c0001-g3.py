def evaluate(trace):
    response = str(trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    if not response.strip() and not tool_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no observable behavior', 'evidence_refs': []}
    allowed = 'award_information_and_record_retriever'
    fact_date_tools = {
        'aviation_incident_info_data_retriever',
        'disaster_event_info_retriever',
        'historical_event_data_retriever',
        'historical_event_date_finder',
        'historical_event_tool',
        'place_info_retriever',
    }
    names = [str(c.get('name') or '') for c in tool_calls]
    used_forbidden = sorted({n for n in names if n in fact_date_tools})
    used_allowed = allowed in names
    if used_forbidden:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'non-exclusive fact/date sources used: ' + ', '.join(used_forbidden), 'evidence_refs': used_forbidden}
    import re
    date_pat = re.compile(r'\b(\d{4})\b|\b(January|February|March|April|May|June|July|August|September|October|November|December)\b', re.I)
    has_date_in_response = bool(date_pat.search(response))
    if not used_allowed:
        if has_date_in_response:
            return {'observed_followed': False, 'confidence': 'medium', 'reason': 'date/fact appears in final response but award_information_and_record_retriever was not used', 'evidence_refs': []}
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no date/fact request evidence and award tool not invoked', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'award_information_and_record_retriever used and no other fact/date retrievers invoked', 'evidence_refs': [allowed]}
