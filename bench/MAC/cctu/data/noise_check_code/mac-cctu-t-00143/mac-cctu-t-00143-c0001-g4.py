def evaluate(trace):
    import json
    import re
    response = str(trace.get('final_response') or '')
    if not response.strip():
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no observable behavior', 'evidence_refs': []}
    reasons = []
    parsed_json = None
    try:
        parsed_json = json.loads(response.strip())
    except Exception:
        parsed_json = None
    if not isinstance(parsed_json, dict):
        reasons.append('valid json object missing')
    if not re.search(r'\b\d{4}(?:[-/]\d{1,2}(?:[-/]\d{1,2})?)?\b|\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\b', response, flags=re.IGNORECASE):
        reasons.append('date not found in response')
    if re.search(r'\b\d{4}\b', response) and not re.search(r'\([^\)]+\)', response):
        reasons.append('date citation in parentheses missing')
    if reasons:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'rule-based repair checks passed', 'evidence_refs': []}
