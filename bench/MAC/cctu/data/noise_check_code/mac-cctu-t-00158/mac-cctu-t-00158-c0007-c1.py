def evaluate(trace):
    import re
    response = str(trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    trajectory = trace.get('trajectory') or []
    if not response.strip() and not tool_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no observable behavior', 'evidence_refs': []}
    reasons = []
    marks = ['**', '__', '# ', '- ', '* ', '`']
    if not any(mark in response for mark in marks):
        reasons.append('markdown marker missing')
    tool_names = [str(call.get('name') or '') for call in tool_calls if call.get('name')]
    tool_count = len(tool_names)
    _count_biodiversity_info_tool = sum(1 for name in tool_names if name == 'biodiversity_info_tool')
    if _count_biodiversity_info_tool < 1:
        reasons.append('biodiversity_info_tool' + ' call count ' + str(_count_biodiversity_info_tool) + ' below 1')
    _count_enhanced_nearby_national_park_locator = sum(1 for name in tool_names if name == 'enhanced_nearby_national_park_locator')
    if _count_enhanced_nearby_national_park_locator < 1:
        reasons.append('enhanced_nearby_national_park_locator' + ' call count ' + str(_count_enhanced_nearby_national_park_locator) + ' below 1')
    _count_residence_finder = sum(1 for name in tool_names if name == 'residence_finder')
    if _count_residence_finder < 1:
        reasons.append('residence_finder' + ' call count ' + str(_count_residence_finder) + ' below 1')
    round_count = len(trajectory)
    if response.strip() and not response.rstrip().endswith('.'):
        reasons.append('response does not end with period')
    if reasons:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'rule-based repair checks passed', 'evidence_refs': []}
