def evaluate(trace):
    import re
    text = trace.get('final_response') or ''
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No final response found', 'evidence_refs': []}
    reasons = []
    md_patterns = [r'^#{1,6}\s', r'\*\*[^*]+\*\*', r'(?<!\*)\*[^*\n]+\*(?!\*)', r'__[^_]+__', r'(?<!`)`[^`\n]+`(?!`)', r'```', r'^\s*[-*+]\s+', r'^\s*\d+\.\s+', r'^>\s', r'\[[^\]]+\]\([^)]+\)']
    for pat in md_patterns:
        if re.search(pat, text, re.MULTILINE):
            reasons.append(f'Markdown-like pattern detected: {pat}')
            break
    length = len(text)
    if length >= 200:
        reasons.append(f'Response length {length} chars is not under 200')
    if reasons:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': f'Plain text, {length} chars, no markdown detected', 'evidence_refs': []}
