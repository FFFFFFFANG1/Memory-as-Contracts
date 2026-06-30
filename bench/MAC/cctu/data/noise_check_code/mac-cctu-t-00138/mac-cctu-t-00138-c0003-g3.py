def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    lines = [l for l in text.split('\n') if l.strip()]
    # Paragraph check: no blank-line separated multiple paragraphs
    paragraphs = [p for p in re.split(r'\n\s*\n', text) if p.strip()]
    if len(paragraphs) > 1:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'{len(paragraphs)} paragraphs detected', 'evidence_refs': []}
    # Bullets / list markers
    for l in lines:
        s = l.lstrip()
        if re.match(r'^([\-\*\+•·]|\d+[\.\)])\s+', s):
            return {'observed_followed': False, 'confidence': 'high', 'reason': 'bullet or list marker found', 'evidence_refs': [l[:80]]}
    # Table / column headers (pipes or markdown table separators)
    if '|' in text and re.search(r'\|.*\|', text):
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'table-like pipes found', 'evidence_refs': []}
    if re.search(r'^\s*[-=]{3,}\s*$', text, re.MULTILINE):
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'separator/header rule found', 'evidence_refs': []}
    if re.search(r'^#{1,6}\s', text, re.MULTILINE):
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'markdown heading found', 'evidence_refs': []}
    # Sentence count
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z0-9"\'])', text)
    sentences = [s for s in sentences if s.strip()]
    if len(sentences) > 4:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'{len(sentences)} sentences', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': f'single paragraph, {len(sentences)} sentences, no tables/bullets/headers', 'evidence_refs': []}
