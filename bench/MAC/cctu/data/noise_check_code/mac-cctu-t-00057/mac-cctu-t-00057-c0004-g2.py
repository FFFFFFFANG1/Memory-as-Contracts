def evaluate(trace):
    import re
    response = str(trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    if not response.strip() and not tool_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no observable behavior', 'evidence_refs': []}
    reasons = []
    marks = ['**', '__', '# ', '- ', '* ', '`']
    if not any(mark in response for mark in marks):
        reasons.append('markdown marker missing')
    if '**' not in response and '__' not in response:
        reasons.append('bold markdown missing')
    if not re.search(r'(^|\n)\s*[-*+]\s+', response):
        reasons.append('bullet list missing')
    word_count = len(response.split())
    if word_count < 300:
        reasons.append('word count {word_count} below 300')
    if word_count > 500:
        reasons.append('word count {word_count} above 500')
    tool_names = [str(call.get('name') or '') for call in tool_calls if call.get('name')]
    tool_count = len(tool_names)
    _count_academic_relationship_finder = sum(1 for name in tool_names if name == 'academic_relationship_finder')
    if _count_academic_relationship_finder < 1:
        reasons.append('academic_relationship_finder' + ' call count ' + str(_count_academic_relationship_finder) + ' below 1')
    _count_literary_connection_finder = sum(1 for name in tool_names if name == 'literary_connection_finder')
    if _count_literary_connection_finder > 2:
        reasons.append('literary_connection_finder' + ' call count ' + str(_count_literary_connection_finder) + ' above 2')
    if reasons:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'rule-based repair checks passed', 'evidence_refs': []}
