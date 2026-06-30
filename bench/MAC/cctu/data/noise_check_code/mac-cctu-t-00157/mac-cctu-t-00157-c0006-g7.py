def evaluate(trace):
    import re
    calls = trace.get('tool_calls') or []
    n = len(calls)
    final = (trace.get('final_response') or '').strip()
    if not final:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    # count sentences: split on . ! ? followed by space or end
    # strip trailing punctuation, count sentence terminators
    text = final.strip()
    # remove trailing whitespace
    parts = re.split(r'(?<=[.!?])\s+', text)
    parts = [p for p in parts if p.strip()]
    sentence_count = len(parts)
    tool_ok = n <= 3
    sent_ok = sentence_count == 1
    if tool_ok and sent_ok:
        return {'observed_followed': True, 'confidence':'high','reason': f'{n} tool calls, 1 sentence','evidence_refs':[]}
    return {'observed_followed': False, 'confidence':'high','reason': f'tool_calls={n} (cap 3), sentences={sentence_count}','evidence_refs':[]}
