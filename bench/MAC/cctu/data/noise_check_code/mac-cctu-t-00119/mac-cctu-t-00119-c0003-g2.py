def evaluate(trace):
    import re
    text = trace.get('final_response') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No final response.', 'evidence_refs': []}
    # Look for a confidence score sentence with a numeric value
    conf_pattern = re.compile(r'confidence[^.\n]*?(\d+(?:\.\d+)?)\s*%?', re.IGNORECASE)
    conf_match = conf_pattern.search(text)
    if not conf_match:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'No numeric confidence score sentence found.', 'evidence_refs': []}
    # Check that confidence sentence is after main answer (not at the very start)
    if conf_match.start() < len(text) * 0.2:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Confidence sentence appears before main answer.', 'evidence_refs': [text[:120]]}
    # Look for analyst commentary paragraph >=400 chars
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
    long_paragraphs = [p for p in paragraphs if len(p) >= 400]
    if not long_paragraphs:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'No paragraph >=400 chars found (longest={max((len(p) for p in paragraphs), default=0)}).', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Found numeric confidence sentence and >=400 char paragraph.', 'evidence_refs': [conf_match.group(0)[:100]]}
