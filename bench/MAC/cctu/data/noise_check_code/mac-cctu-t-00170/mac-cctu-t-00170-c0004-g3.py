import re

def evaluate(trace):
    trace = trace or {}
    final = str((trace or {}).get('final_response') or '')
    if not final.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'missing final response', 'evidence_refs': []}
    words = re.findall(r'\S+', final)
    word_count = len(words)
    failures = []
    if word_count < 300:
        failures.append(f'word count {word_count} below minimum 300')
    lines = final.splitlines()
    bullet_lines = []
    for ln in lines:
        stripped = ln.lstrip()
        if re.match(r'^([\-\*\+\u2022])\s+', stripped):
            bullet_lines.append(ln)
        elif re.match(r'^\d+[\.)]\s+', stripped):
            bullet_lines.append(ln)
    if bullet_lines:
        failures.append(f'found {len(bullet_lines)} bullet/list line(s)')
    table_lines = [ln for ln in lines if '|' in ln and ln.count('|') >= 2]
    sep_lines = [ln for ln in lines if re.match(r'^\s*\|?\s*:?-{3,}', ln)]
    if len(table_lines) >= 2 or sep_lines:
        failures.append('table-like markdown structure detected')
    evidence = [{'field': 'final_response', 'unit': 'words', 'count': word_count}]
    if failures:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(failures), 'evidence_refs': evidence}
    return {'observed_followed': True, 'confidence': 'high', 'reason': f'narrative paragraph with {word_count} words and no bullets/tables', 'evidence_refs': evidence}
