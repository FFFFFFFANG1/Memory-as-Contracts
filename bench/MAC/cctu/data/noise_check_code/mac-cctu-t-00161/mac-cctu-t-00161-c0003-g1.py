def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    # Single paragraph: no blank line separators
    if re.search(r'\n\s*\n', text):
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'multiple paragraphs detected', 'evidence_refs': [text[:120]]}
    # Word count <= 80
    words = re.findall(r"\b[\w'-]+\b", text)
    if len(words) > 80:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'word count {len(words)} exceeds 80', 'evidence_refs': []}
    # No Markdown formatting
    md_patterns = [r'(^|\s)#{1,6}\s', r'\*\*[^*]+\*\*', r'(^|\s)\*[^*]+\*', r'(^|\s)_[^_]+_', r'`[^`]+`', r'^\s*[-*+]\s+', r'^\s*\d+\.\s+', r'\[[^\]]+\]\([^)]+\)']
    for pat in md_patterns:
        if re.search(pat, text, re.MULTILINE):
            return {'observed_followed': False, 'confidence': 'high', 'reason': f'markdown pattern matched: {pat}', 'evidence_refs': [text[:120]]}
    # Numerical result inline without prefix label
    # Look for label-like patterns preceding numbers: 'Answer:', 'Result:', 'Total:', etc.
    label_pat = re.compile(r'\b(answer|result|total|count|number|value|output|final)\s*[:=]\s*[-+]?\d', re.IGNORECASE)
    if label_pat.search(text):
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'numerical result has prefix label', 'evidence_refs': [label_pat.search(text).group(0)]}
    # Check there is at least one number inline (semantic - allow unknown if none)
    has_num = bool(re.search(r'\d', text))
    if not has_num:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'no numerical result found to verify inline presentation', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': f'single paragraph, {len(words)} words, no markdown, number inline without label', 'evidence_refs': []}
