import re

def evaluate(trace):
    trace = trace or {}
    final = str((trace or {}).get('final_response') or '')
    if not final.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'missing final response', 'evidence_refs': []}
    failures = []
    evidence = []
    words = re.findall(r'\S+', final)
    wc = len(words)
    evidence.append({'word_count': wc})
    if wc < 300:
        failures.append(f'word count {wc} below minimum 300')
    lines = final.splitlines()
    bullet_lines = []
    numeric_header_lines = []
    table_lines = []
    for i, ln in enumerate(lines):
        s = ln.strip()
        if not s:
            continue
        if re.match(r'^[-*+\u2022]\s+\S', s):
            bullet_lines.append(i)
        if re.match(r'^\d+[\.)]\s+\S', s):
            numeric_header_lines.append(i)
        if re.match(r'^#{1,6}\s+\S', s):
            numeric_header_lines.append(i)
        if '|' in s and s.count('|') >= 2:
            table_lines.append(i)
        if re.match(r'^\s*\|?\s*:?-{3,}', s):
            table_lines.append(i)
    if bullet_lines:
        failures.append(f'bullet list detected on lines {bullet_lines[:5]}')
    if numeric_header_lines:
        failures.append(f'numeric/heading style lines detected {numeric_header_lines[:5]}')
    if table_lines:
        failures.append(f'table syntax detected on lines {table_lines[:5]}')
    # single prose block: many blank-line-separated paragraphs allowed? Constraint says single descriptive prose block.
    paragraphs = [p for p in re.split(r'\n\s*\n', final.strip()) if p.strip()]
    evidence.append({'paragraphs': len(paragraphs)})
    if len(paragraphs) > 1:
        failures.append(f'expected single prose block, found {len(paragraphs)} paragraphs')
    if failures:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(failures[:6]), 'evidence_refs': evidence}
    return {'observed_followed': True, 'confidence': 'high', 'reason': f'single prose block with {wc} words, no tables/bullets/headers', 'evidence_refs': evidence}
