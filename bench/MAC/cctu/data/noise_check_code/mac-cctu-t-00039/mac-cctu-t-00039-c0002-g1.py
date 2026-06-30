def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no content lines', 'evidence_refs': []}
    numbered = [ln for ln in lines if re.match(r'^\s*\d+[\.\)]\s+', ln)]
    if len(numbered) < 2 or len(numbered) < max(1, int(0.6 * len(lines))):
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'response not formatted as numbered bullet list', 'evidence_refs': []}
    # detect table layouts
    if '|' in text and re.search(r'\|.*\|', text):
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'tabular layout detected (pipes)', 'evidence_refs': []}
    if re.search(r'^\s*\|?\s*[-:]+\s*\|', text, re.MULTILINE):
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'markdown table separator detected', 'evidence_refs': []}
    # one fact per line: numbered items shouldn't contain hard line breaks beyond their single line
    for ln in numbered:
        # check that the numbered item isn't a multi-sentence dense block with embedded tab
        if '\t' in ln:
            return {'observed_followed': False, 'confidence': 'medium', 'reason': 'tab character suggests tabular layout', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'numbered list with one fact per line, no table', 'evidence_refs': []}
