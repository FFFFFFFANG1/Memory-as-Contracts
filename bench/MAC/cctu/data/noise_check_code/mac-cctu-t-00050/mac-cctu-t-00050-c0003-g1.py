def evaluate(trace):
    import re
    tcs = trace.get('tool_calls') or []
    n = len(tcs)
    final = (trace.get('final_response') or '').strip()
    if not final:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    # Count sentences: split on . ! ? followed by space or end
    # Remove trailing terminal punctuation for counting
    parts = re.split(r'(?<=[.!?])\s+', final)
    sentences = [p for p in parts if p.strip()]
    # Also consider internal terminators within single chunk
    terminators = len(re.findall(r'[.!?]+(?=\s|$)', final))
    single_sentence = (len(sentences) <= 1) and (terminators <= 1)
    tool_ok = n <= 3
    followed = tool_ok and single_sentence
    reason = f'tool_calls={n} (cap 3), sentences~{len(sentences)}, terminators={terminators}'
    return {'observed_followed': bool(followed), 'confidence': 'high' if (tool_ok and single_sentence) or (not tool_ok) else 'medium', 'reason': reason, 'evidence_refs': []}
