def evaluate(trace):
    import re
    resp = (trace.get('final_response') or '').strip()
    if not resp:
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    # Look at the tail of the response for IEEE bracket citations like [1] Author, ...
    tail = resp[-2000:]
    # Find all [N] markers
    brackets = re.findall(r'\[(\d+)\]', tail)
    if not brackets:
        return {'observed_followed': False, 'confidence':'high','reason':'no [N] bracket citations found at end','evidence_refs':[tail[-200:]]}
    # Ensure at least one bracket appears in the final portion (last ~500 chars) indicating appended references
    last_segment = resp[-800:]
    if not re.search(r'\[\d+\][^\[]{5,}', last_segment):
        return {'observed_followed': False, 'confidence':'medium','reason':'brackets present but no IEEE-style citation entries appended','evidence_refs':[last_segment]}
    # Check that the citation block is at the END (after main content)
    # Find position of last paragraph break before brackets
    m = list(re.finditer(r'\[\d+\]', resp))
    if not m:
        return {'observed_followed': False, 'confidence':'high','reason':'no bracket markers','evidence_refs':[]}
    first_bracket_pos = m[0].start()
    # The bracket should be in the latter half or after a clear separator
    if first_bracket_pos < len(resp) * 0.3:
        return {'observed_followed': None, 'confidence':'low','reason':'bracket citations appear early, may be inline only','evidence_refs':[resp[first_bracket_pos:first_bracket_pos+200]]}
    return {'observed_followed': True, 'confidence':'medium','reason':'IEEE-style [N] citations appended at end','evidence_refs':[resp[first_bracket_pos:][:300]]}
