def evaluate(trace):
    import re
    response = str(trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    if not response.strip() and not tool_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no observable behavior', 'evidence_refs': []}
    reasons = []
    word_count = len(response.split())
    if word_count < 50:
        reasons.append('word count {word_count} below 50')
    if word_count > 150:
        reasons.append('word count {word_count} above 150')
    tool_names = [str(call.get('name') or '') for call in tool_calls if call.get('name')]
    tool_count = len(tool_names)
    if tool_count > 10:
        reasons.append('tool call count {tool_count} above 10')
    _count_asteroid_name_matcher = sum(1 for name in tool_names if name == 'asteroid_name_matcher')
    if _count_asteroid_name_matcher > 1:
        reasons.append('asteroid_name_matcher' + ' call count ' + str(_count_asteroid_name_matcher) + ' above 1')
    _count_astronomical_discovery_finder = sum(1 for name in tool_names if name == 'astronomical_discovery_finder')
    if _count_astronomical_discovery_finder > 1:
        reasons.append('astronomical_discovery_finder' + ' call count ' + str(_count_astronomical_discovery_finder) + ' above 1')
    _count_biographical_lookup = sum(1 for name in tool_names if name == 'biographical_lookup')
    if _count_biographical_lookup > 1:
        reasons.append('biographical_lookup' + ' call count ' + str(_count_biographical_lookup) + ' above 1')
    _count_historical_contemporary_finder = sum(1 for name in tool_names if name == 'historical_contemporary_finder')
    if _count_historical_contemporary_finder > 10:
        reasons.append('historical_contemporary_finder' + ' call count ' + str(_count_historical_contemporary_finder) + ' above 10')
    _count_literary_author_identifier = sum(1 for name in tool_names if name == 'literary_author_identifier')
    if _count_literary_author_identifier > 10:
        reasons.append('literary_author_identifier' + ' call count ' + str(_count_literary_author_identifier) + ' above 10')
    _count_literary_work_identifier = sum(1 for name in tool_names if name == 'literary_work_identifier')
    if _count_literary_work_identifier > 10:
        reasons.append('literary_work_identifier' + ' call count ' + str(_count_literary_work_identifier) + ' above 10')
    _count_national_symbol_finder = sum(1 for name in tool_names if name == 'national_symbol_finder')
    if _count_national_symbol_finder > 1:
        reasons.append('national_symbol_finder' + ' call count ' + str(_count_national_symbol_finder) + ' above 1')
    if reasons:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'rule-based repair checks passed', 'evidence_refs': []}
