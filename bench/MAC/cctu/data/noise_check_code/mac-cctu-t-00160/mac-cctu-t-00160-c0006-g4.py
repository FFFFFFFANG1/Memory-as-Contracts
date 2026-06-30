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
    if '**' not in response and '__' not in response:
        reasons.append('bold markdown missing')
    word_count = len(response.split())
    if word_count < 150:
        reasons.append('word count {word_count} below 150')
    if word_count > 200:
        reasons.append('word count {word_count} above 200')
    tool_names = [str(call.get('name') or '') for call in tool_calls if call.get('name')]
    tool_count = len(tool_names)
    _count_comprehensive_biographical_info_retriever = sum(1 for name in tool_names if name == 'comprehensive_biographical_info_retriever')
    if _count_comprehensive_biographical_info_retriever > 2:
        reasons.append('comprehensive_biographical_info_retriever' + ' call count ' + str(_count_comprehensive_biographical_info_retriever) + ' above 2')
    round_count = len(trajectory)
    if not re.search(r'\b\d{4}(?:[-/]\d{1,2}(?:[-/]\d{1,2})?)?\b|\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\b', response, flags=re.IGNORECASE):
        reasons.append('date not found in response')
    if 'eu' not in response.lower():
        reasons.append('eu' + ' not mentioned in response')
    if 'un' not in response.lower():
        reasons.append('un' + ' not mentioned in response')
    if reasons:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'rule-based repair checks passed', 'evidence_refs': []}
