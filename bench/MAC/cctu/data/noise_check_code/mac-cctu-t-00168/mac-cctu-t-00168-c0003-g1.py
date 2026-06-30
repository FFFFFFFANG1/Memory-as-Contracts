def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    reasons = []
    # No tables (markdown pipes used as table delimiters)
    if re.search(r'^\s*\|.*\|\s*$', text, re.MULTILINE):
        reasons.append('table detected')
    # No bullet lists
    if re.search(r'(^|\n)\s*[-*+]\s+\S', text):
        reasons.append('bullet list detected')
    if re.search(r'(^|\n)\s*\d+[.)]\s+\S', text):
        reasons.append('numbered list detected')
    # No symbolic delimiters like ---, ===, ***, ###, >>>
    if re.search(r'(^|\n)\s*(-{3,}|={3,}|\*{3,}|#{1,6}\s|>{1,})', text):
        reasons.append('symbolic delimiter or heading detected')
    # Single flowing paragraph: no blank lines separating multiple paragraphs
    paragraphs = [p for p in re.split(r'\n\s*\n', text) if p.strip()]
    if len(paragraphs) > 1:
        reasons.append(f'multiple paragraphs: {len(paragraphs)}')
    followed = len(reasons) == 0
    return {'observed_followed': followed, 'confidence': 'high' if followed else 'medium', 'reason': 'ok' if followed else '; '.join(reasons), 'evidence_refs': []}
