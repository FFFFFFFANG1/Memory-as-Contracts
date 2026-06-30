def evaluate(trace):
    import re
    calls = trace.get('tool_calls') or []
    names = [c.get('name') for c in calls]
    final = (trace.get('final_response') or '').strip()
    if not names and not final:
        return {'observed_followed': None, 'confidence':'unknown', 'reason':'no trajectory data', 'evidence_refs': []}
    allowed = 'tribal_language_identifier'
    other = [n for n in names if n != allowed]
    has_tribal = any(n == allowed for n in names)
    if other:
        return {'observed_followed': False, 'confidence':'high', 'reason': f'extra tool calls: {other}', 'evidence_refs': names}
    if not has_tribal:
        return {'observed_followed': False, 'confidence':'medium', 'reason':'tribal_language_identifier not called', 'evidence_refs': names}
    if not final:
        return {'observed_followed': None, 'confidence':'unknown', 'reason':'no final response', 'evidence_refs': names}
    # single sentence check: split on sentence-ending punctuation
    parts = [p for p in re.split(r'(?<=[.!?])\s+', final) if p.strip()]
    sentence_count = len(parts)
    # also count internal sentence terminators
    terminators = len(re.findall(r'[.!?](?:\s|$)', final))
    if sentence_count > 1 or terminators > 1:
        return {'observed_followed': False, 'confidence':'high', 'reason': f'response has {sentence_count} sentences', 'evidence_refs':[final[:200]]}
    return {'observed_followed': True, 'confidence':'medium', 'reason':'single sentence using only tribal_language_identifier', 'evidence_refs': names}
