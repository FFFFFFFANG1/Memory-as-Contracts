def evaluate(trace):
    import json, re
    calls = trace.get('tool_calls') or []
    final = trace.get('final_response') or ''
    if len(calls) > 3:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'{len(calls)} tool calls exceed limit of 3', 'evidence_refs': []}
    text = final.strip()
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty final response', 'evidence_refs': []}
    md_patterns = [r'```', r'^#{1,6}\s', r'\*\*[^*]+\*\*', r'(^|\n)\s*[-*+]\s']
    for pat in md_patterns:
        if re.search(pat, text, re.MULTILINE):
            return {'observed_followed': False, 'confidence': 'high', 'reason': f'markdown formatting detected: {pat}', 'evidence_refs': []}
    try:
        parsed = json.loads(text)
    except Exception as e:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'final response is not valid JSON: {e}', 'evidence_refs': []}
    if not isinstance(parsed, dict):
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'final JSON is not an object', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': f'{len(calls)} tool calls and final is a JSON object without markdown', 'evidence_refs': []}
