def evaluate(trace):
    import re
    text = trace.get('final_response') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    reasons = []
    # single paragraph: no blank lines
    if re.search(r'\n\s*\n', text):
        reasons.append('multiple paragraphs')
    # word count
    words = re.findall(r'\S+', text)
    if len(words) > 80:
        reasons.append(f'word count {len(words)} > 80')
    # markdown checks
    md_patterns = [r'(^|\n)\s*#{1,6}\s', r'\*\*[^*]+\*\*', r'(^|\s)\*[^*]+\*', r'(^|\s)_[^_]+_', r'`[^`]+`', r'(^|\n)\s*[-*+]\s', r'(^|\n)\s*\d+\.\s', r'\[[^\]]+\]\([^)]+\)']
    for pat in md_patterns:
        if re.search(pat, text):
            reasons.append(f'markdown detected: {pat}')
            break
    # final answer prefix
    if re.match(r'\s*(\*\*)?\s*final answer\s*:', text, re.IGNORECASE):
        reasons.append('contains Final Answer: prefix')
    if reasons:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': f'single paragraph, {len(words)} words, no markdown, no Final Answer prefix', 'evidence_refs': []}
