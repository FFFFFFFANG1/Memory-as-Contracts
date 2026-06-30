def evaluate(trace):
    import re
    calls = trace.get('tool_calls') or []
    n = len(calls)
    final = (trace.get('final_response') or '').strip()
    if not final:
        return {'observed_followed': None, 'confidence':'unknown', 'reason':'no final response', 'evidence_refs':[]}
    # Count sentences: split on ., !, ? not inside decimals trivially
    # Strip trailing whitespace and a single terminal punctuation
    text = final
    # Find sentence terminators
    parts = re.split(r'[.!?]+\s+', text)
    parts = [p for p in parts if p.strip()]
    # Also if text contains internal terminator followed by more content, that's >1 sentence
    sentence_count = len(parts)
    # Heuristic: if ends with terminator and only one part, it's 1 sentence
    tool_ok = n <= 3
    sent_ok = sentence_count <= 1
    followed = tool_ok and sent_ok
    reason = f'tool_calls={n} (<=3:{tool_ok}); sentences={sentence_count} (<=1:{sent_ok})'
    return {'observed_followed': bool(followed), 'confidence':'high' if (tool_ok and sentence_count<=1) or (not tool_ok) else 'medium', 'reason': reason, 'evidence_refs': []}
