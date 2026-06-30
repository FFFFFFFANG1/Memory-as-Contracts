def evaluate(trace):
    import re
    response = str(trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    trajectory = trace.get('trajectory') or []
    if not response.strip() and not tool_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no observable behavior', 'evidence_refs': []}
    reasons = []
    word_count = len(response.split())
    if word_count < 10:
        reasons.append('word count {word_count} below 10')
    if word_count > 20:
        reasons.append('word count {word_count} above 20')
    tool_names = [str(call.get('name') or '') for call in tool_calls if call.get('name')]
    tool_count = len(tool_names)
    _count_factual_information_retriever = sum(1 for name in tool_names if name == 'factual_information_retriever')
    if _count_factual_information_retriever > 2:
        reasons.append('factual_information_retriever' + ' call count ' + str(_count_factual_information_retriever) + ' above 2')
    _count_marine_biology_facts = sum(1 for name in tool_names if name == 'marine_biology_facts')
    if _count_marine_biology_facts > 2:
        reasons.append('marine_biology_facts' + ' call count ' + str(_count_marine_biology_facts) + ' above 2')
    round_count = len(trajectory)
    if response.strip() and not response.rstrip().endswith('.'):
        reasons.append('response does not end with period')
    if reasons:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'rule-based repair checks passed', 'evidence_refs': []}
