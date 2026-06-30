def evaluate(trace):
    import re
    response = str(trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    if not response.strip() and not tool_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no observable behavior', 'evidence_refs': []}
    reasons = []
    tool_names = [str(call.get('name') or '') for call in tool_calls if call.get('name')]
    tool_count = len(tool_names)
    _count_anatomical_info_provider = sum(1 for name in tool_names if name == 'anatomical_info_provider')
    if _count_anatomical_info_provider < 3:
        reasons.append('anatomical_info_provider' + ' call count ' + str(_count_anatomical_info_provider) + ' below 3')
    _count_anatomy_facts_provider = sum(1 for name in tool_names if name == 'anatomy_facts_provider')
    if _count_anatomy_facts_provider < 3:
        reasons.append('anatomy_facts_provider' + ' call count ' + str(_count_anatomy_facts_provider) + ' below 3')
    if reasons:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'rule-based repair checks passed', 'evidence_refs': []}
