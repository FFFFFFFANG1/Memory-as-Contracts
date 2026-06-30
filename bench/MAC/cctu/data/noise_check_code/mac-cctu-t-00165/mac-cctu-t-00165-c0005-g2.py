def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    # Detect tabular formatting
    if '|' in text and re.search(r'\|.*\|', text):
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'pipe table detected', 'evidence_refs': []}
    if re.search(r'(^|\n)\s*[-+]{3,}', text):
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'table separator detected', 'evidence_refs': []}
    if re.search(r'\t.*\t', text):
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'tab-separated columns', 'evidence_refs': []}
    # Count sentences
    # Strip trailing punctuation count
    sentences = re.split(r'(?<=[.!?])\s+', text)
    sentences = [s for s in sentences if s.strip()]
    if len(sentences) > 1:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'{len(sentences)} sentences, not single', 'evidence_refs': []}
    if '\n' in text.strip():
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'multiple lines in final response', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'single prose sentence, no tabular formatting', 'evidence_refs': []}
