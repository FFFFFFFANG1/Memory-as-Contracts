def evaluate(trace):
    import re
    tool_calls = trace.get('tool_calls') or []
    locator_tools = [tc for tc in tool_calls if isinstance(tc.get('name'),str) and tc['name'].endswith('_locator')]
    seq_ok = None
    if locator_tools:
        first = locator_tools[0].get('name')
        seq_ok = (first == 'individual_region_locator')
    final = trace.get('final_response') or ''
    text = final.strip()
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty final response', 'evidence_refs': []}
    md_patterns = [r'\*\*', r'__', r'^#', r'\n#', r'^\s*[-*+]\s', r'\n\s*[-*+]\s', r'`', r'\[[^\]]+\]\([^\)]+\)']
    md_found = any(re.search(p, text, re.MULTILINE) for p in md_patterns)
    sentences = re.split(r'(?<=[.!?])\s+', text)
    sentences = [s for s in sentences if s.strip()]
    single_sentence = len(sentences) <= 1 and '\n' not in text.strip()
    fmt_ok = (not md_found) and single_sentence
    if seq_ok is False:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'individual_region_locator was not the first locator tool called', 'evidence_refs': ['tool_calls']}
    if not fmt_ok:
        reasons = []
        if md_found: reasons.append('markdown formatting detected')
        if not single_sentence: reasons.append('more than one sentence or contains newlines')
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(reasons), 'evidence_refs': ['final_response']}
    if seq_ok is None:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': 'no locator tools called; final response is single plain sentence', 'evidence_refs': ['final_response']}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'individual_region_locator called first and output is single plain sentence', 'evidence_refs': ['tool_calls','final_response']}
