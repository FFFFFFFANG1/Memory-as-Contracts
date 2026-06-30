def evaluate(trace):
    import re
    response = str(trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    text = response.lower()
    summit_terms = ['summit', 'g7', 'g20', 'g-7', 'g-20', 'apec', 'asean summit', 'nato summit', 'brics']
    is_summit = any(t in text for t in summit_terms) and 'international' in text or any(t in text for t in ['summit','g7','g20','apec','brics','nato summit'])
    if not is_summit:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no international summit topic detected in response', 'evidence_refs': []}
    if not tool_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'constraint requires political_event_finder lookups but no tool calls present', 'evidence_refs': []}
    pef_calls = [c for c in tool_calls if str(c.get('name') or '') == 'political_event_finder']
    if len(pef_calls) < 2:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'expected >=2 political_event_finder calls (one for fact, one for confidence); found {len(pef_calls)}', 'evidence_refs': [str(c.get('index')) for c in pef_calls]}
    has_confidence = bool(re.search(r'confidence[:\s]', text)) or bool(re.search(r'\b(confidence rating|confidence level|confidence score)\b', text)) or bool(re.search(r'\bconfidence\b.*\b(high|medium|low|\d)', text))
    if not has_confidence:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'no confidence rating appended to factual answer', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'two political_event_finder calls present and confidence rating appended', 'evidence_refs': [str(c.get('index')) for c in pef_calls]}
