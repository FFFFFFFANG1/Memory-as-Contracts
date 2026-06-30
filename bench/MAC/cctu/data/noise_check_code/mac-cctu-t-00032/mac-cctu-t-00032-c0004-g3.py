def evaluate(trace):
    import re
    response = str(trace.get('final_response') or '')
    if not response.strip():
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'empty response', 'evidence_refs': []}
    reasons = []
    word_count = len(response.split())
    if word_count < 15:
        reasons.append('word count ' + str(word_count) + ' below 15')
    if word_count > 50:
        reasons.append('word count ' + str(word_count) + ' above 50')
    stripped = response.rstrip()
    if not stripped.endswith('.'):
        reasons.append('response does not end with period')
    if '[Answer]' not in response:
        reasons.append('missing exact phrase [Answer]')
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(reasons), 'evidence_refs': []}
    idx = response.rfind('[Answer]')
    after = response[idx + len('[Answer]'):].strip()
    if not after:
        reasons.append('no sentence after [Answer]')
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(reasons), 'evidence_refs': []}
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', after) if s.strip()]
    if not sentences:
        reasons.append('no final sentence after [Answer]')
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(reasons), 'evidence_refs': []}
    final_sentence = sentences[-1]
    if not final_sentence.endswith('.'):
        reasons.append('final sentence does not end with period')
    # Semantic check for banned vehicle type cannot be verified definitively
    # Look for vehicle-related terms as a heuristic
    vehicle_terms = ['car','truck','vehicle','motorcycle','scooter','bike','bicycle','bus','van','suv','moped','atv','automobile','lorry','rickshaw','tuk-tuk','trailer']
    has_vehicle_term = any(re.search(r'\b' + t + r'\b', after.lower()) for t in vehicle_terms)
    if not has_vehicle_term:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'cannot verify banned vehicle type mentioned in final sentence', 'evidence_refs': []}
    if reasons:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': '[Answer] precedes final sentence with vehicle term ending in period; word count in range', 'evidence_refs': []}
