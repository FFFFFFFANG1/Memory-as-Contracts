def evaluate(trace):
    import re
    final = (trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    # Detect death toll figures in final response
    toll_patterns = [r'\b\d{1,3}(?:,\d{3})+\b', r'\b\d{2,}\s*(?:killed|dead|deaths|casualties|fatalities|died|perished|lives lost)\b', r'(?:killed|dead|deaths|casualties|fatalities|died|perished|death toll)[^.]{0,40}?\b\d{2,}\b']
    text = final.lower()
    matches = []
    for p in toll_patterns:
        for m in re.finditer(p, text):
            matches.append(m.group(0))
    constit_used = any((tc.get('name') or '') == 'constitutional_info_retriever' for tc in tool_calls)
    if not matches:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'No death toll figures detected in final response; cannot assess cross-verification.', 'evidence_refs': []}
    if constit_used:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': f'Death toll figures present and constitutional_info_retriever was invoked. Matches: {matches[:3]}', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Death toll figures reported ({matches[:3]}) but constitutional_info_retriever was never called for cross-verification.', 'evidence_refs': []}
