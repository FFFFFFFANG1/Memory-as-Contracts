def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No final response', 'evidence_refs': []}
    paragraphs = [p for p in re.split(r'\n\s*\n', text) if p.strip()]
    multi_para = len(paragraphs) >= 2
    heading_patterns = [r'^#{1,6}\s+\S', r'^\*\*[^*\n]+\*\*\s*:?\s*$', r'^[A-Z][A-Za-z0-9 ,/&-]{2,60}:\s*$', r'^[A-Z][A-Z0-9 ,/&-]{2,60}$']
    heading_lines = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        for pat in heading_patterns:
            if re.match(pat, s):
                heading_lines.append(s)
                break
    has_headings = len(heading_lines) >= 2
    summary_pat = re.compile(r'(summary|conclusion|in\s+summary|in\s+conclusion|to\s+summarize|closing\s+thoughts|wrap[-\s]?up|takeaway)', re.IGNORECASE)
    last_chunk = '\n'.join(text.splitlines()[-15:])
    has_summary = bool(summary_pat.search(last_chunk))
    ok = multi_para and has_headings and has_summary
    reason = f'paragraphs={len(paragraphs)}, headings={len(heading_lines)}, closing_summary={has_summary}'
    return {'observed_followed': bool(ok), 'confidence': 'medium', 'reason': reason, 'evidence_refs': []}
