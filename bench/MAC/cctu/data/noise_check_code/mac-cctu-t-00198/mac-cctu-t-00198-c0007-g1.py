def evaluate(trace):
    import re
    text = trace.get('final_response') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No final response', 'evidence_refs': []}
    words = re.findall(r'\S+', text)
    wc = len(words)
    md_patterns = [r'\*\*', r'__', r'(^|\n)\s*#', r'(^|\n)\s*[-*+]\s', r'`', r'\[[^\]]+\]\([^)]+\)', r'(^|\n)\s*>\s', r'(^|\n)\s*\d+\.\s']
    md_hits = [p for p in md_patterns if re.search(p, text)]
    paragraphs = [p for p in re.split(r'\n\s*\n', text.strip()) if p.strip()]
    single_para = len(paragraphs) == 1 and '\n' not in text.strip()
    ok = wc <= 80 and not md_hits and single_para
    reason = f'words={wc}, md_hits={md_hits}, paragraphs={len(paragraphs)}'
    return {'observed_followed': bool(ok), 'confidence': 'high', 'reason': reason, 'evidence_refs': []}
