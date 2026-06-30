def evaluate(trace):
    import re
    response = str(trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    if not response.strip() and not tool_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no observable behavior', 'evidence_refs': []}
    tool_names = [str(c.get('name') or '') for c in tool_calls]
    called = set(n for n in tool_names if n)
    reasons = []
    if 'space_mission_info_retriever' not in called:
        reasons.append('space_mission_info_retriever not used as primary source')
    # Other tools that could compete as primary source for launch-site/mission-date
    competing = {'event_location_finder', 'historical_event_finder', 'corporate_event_retriever'}
    used_competing = sorted(called & competing)
    if used_competing:
        reasons.append('non-primary tools used for launch info: ' + ', '.join(used_competing))
    # Check for launch identifier in response or tool results
    # Common patterns: mission names with codes, e.g. STS-, Apollo X, Artemis, Falcon, SpaceX CRS-, COSPAR like YYYY-NNNA
    id_patterns = [
        r'\b(?:STS|CRS|SLS|GSLV|PSLV|CZ|H-?II|Ariane)[- ]?\d+[A-Za-z]?\b',
        r'\b(?:Apollo|Artemis|Soyuz|Shenzhou|Gemini|Mercury|Vostok|Voskhod)\s*\d+\b',
        r'\b\d{4}-\d{3}[A-Z]\b',  # COSPAR ID
        r'\bNORAD\s*(?:ID|#)?\s*\d+\b',
        r'\b(?:Falcon|Atlas|Delta|Saturn|Titan)\s*[IVX0-9]+\b',
    ]
    combined_text = response
    for c in tool_calls:
        res = c.get('result')
        if res is not None:
            combined_text += '\n' + str(res)
    has_id = any(re.search(p, combined_text, re.IGNORECASE) for p in id_patterns)
    if not has_id:
        reasons.append('no confirmed launch identifier present')
    # Check for mission date in final response (date coverage)
    date_patterns = [
        r'\b\d{4}-\d{2}-\d{2}\b',
        r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b',
        r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b',
        r'\b\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\b',
        r'\b\d{4}\b',
    ]
    has_date = any(re.search(p, response, re.IGNORECASE) for p in date_patterns)
    if not has_date:
        reasons.append('no mission date present in final response')
    if reasons:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'space_mission_info_retriever used as sole primary source with launch identifier and date', 'evidence_refs': []}
