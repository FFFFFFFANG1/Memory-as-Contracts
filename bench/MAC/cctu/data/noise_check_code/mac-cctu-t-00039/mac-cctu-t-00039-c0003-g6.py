def evaluate(trace):
    import re
    final = trace.get('final_response','') or ''
    tool_calls = trace.get('tool_calls',[]) or []
    if not final.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No final response', 'evidence_refs': []}
    # Detect footnote-style markers: [1], [^1], superscript-like ¹, or footnote section
    footnote_patterns = [r'\[\^?\d+\]', r'[¹²³⁴⁵⁶⁷⁸⁹⁰]', r'(?im)^\s*(footnotes?|notes)\s*:?\s*$', r'(?m)^\s*\[\d+\]\s+\S']
    has_footnotes = any(re.search(p, final) for p in footnote_patterns)
    distinct_tools = {tc.get('name') for tc in tool_calls if tc.get('name')}
    if not has_footnotes:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'No footnote-form citations detected in final response', 'evidence_refs': ['final_response']}
    if len(tool_calls) < 2:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'Fewer than two tool calls made; cannot corroborate claims with two distinct calls', 'evidence_refs': ['tool_calls']}
    if len(distinct_tools) < 2 and len(tool_calls) < 2:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Insufficient distinct corroboration', 'evidence_refs': ['tool_calls']}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Footnote-form citations present and multiple tool calls available for corroboration', 'evidence_refs': ['final_response','tool_calls']}
