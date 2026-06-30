def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    tail = text[-600:].lower()
    mentions_no_pretrained = any(k in tail for k in ['pre-trained', 'pretrained', 'pre trained', 'internal knowledge', 'internal pre-trained', 'prior knowledge', 'training data'])
    mentions_tool_verified = any(k in tail for k in ['tool-verified', 'tool verified', 'verified via tool', 'verified by tool', 'verified through tool', 'all facts were tool', 'facts were verified', 'verified using tool'])
    if mentions_no_pretrained and mentions_tool_verified:
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'disclaimer present at end mentioning no pre-trained knowledge and tool-verified facts', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': f'missing disclaimer parts (no_pretrained={mentions_no_pretrained}, tool_verified={mentions_tool_verified})', 'evidence_refs': []}
