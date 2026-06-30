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
    if word_count == 0:
        reasons.append('response text missing')
    tool_names = [str(call.get('name') or '') for call in tool_calls if call.get('name')]
    tool_count = len(tool_names)
    _count_historical_event_retriever = sum(1 for name in tool_names if name == 'historical_event_retriever')
    if _count_historical_event_retriever > 2:
        reasons.append('historical_event_retriever' + ' call count ' + str(_count_historical_event_retriever) + ' above 2')
    round_count = len(trajectory)
    if response.strip() and not response.rstrip().endswith('.'):
        reasons.append('response does not end with period')
    if reasons:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'rule-based repair checks passed', 'evidence_refs': []}
