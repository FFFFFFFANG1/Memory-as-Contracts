def evaluate(trace):
    import re
    response = str(trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    if not response.strip():
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'empty final response', 'evidence_refs': []}
    low = response.lower()
    has_footnote_word = 'footnote' in low
    # footnote markers like [1], [^1], (1), or superscript-style references
    bracket_refs = re.findall(r'\[\^?\d+\]', response)
    paren_refs = re.findall(r'\(\d+\)', response)
    has_refs = len(bracket_refs) >= 1 or len(paren_refs) >= 2 or has_footnote_word
    # citation/report structure indicators
    cite_terms = ['citation', 'cite', 'source', 'reference']
    has_cite = any(t in low for t in cite_terms) or has_footnote_word
    # mapping to tool outputs: mention of tool name or 'tool' in footnote context
    tool_names = set()
    for tc in tool_calls:
        n = tc.get('name')
        if n:
            tool_names.add(str(n))
    tool_mentioned = ('tool' in low) or any(tn.lower() in low for tn in tool_names)
    reasons = []
    if not has_footnote_word and not bracket_refs and len(paren_refs) < 2:
        reasons.append('no footnote markers or footnote terminology found')
    if not has_cite:
        reasons.append('no citation/reference structure indicated')
    if not tool_mentioned:
        reasons.append('footnotes do not appear to map to tool outputs (no tool reference)')
    if not tool_calls:
        # cannot map footnotes to tool outputs if no tools were called
        reasons.append('no tool calls available to cite')
    if reasons:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'footnote markers, citation structure, and tool-output mapping present', 'evidence_refs': []}
