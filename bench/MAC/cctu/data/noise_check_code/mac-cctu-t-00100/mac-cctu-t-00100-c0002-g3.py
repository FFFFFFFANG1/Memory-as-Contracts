import re

def evaluate(trace):
    trace = trace or {}
    final = str((trace or {}).get('final_response') or '')
    if not final.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'missing final response', 'evidence_refs': []}
    lines = final.splitlines()
    # Detect markdown table: header row with | and separator row of dashes
    table_end_idx = -1
    table_found = False
    for i in range(len(lines) - 1):
        header = lines[i]
        sep = lines[i+1]
        if '|' in header and re.match(r'^\s*\|?\s*:?-{2,}.*\|', sep) and '-' in sep:
            # find end of table
            j = i + 2
            while j < len(lines) and '|' in lines[j] and lines[j].strip():
                j += 1
            table_end_idx = j
            table_found = True
            break
    failures = []
    if not table_found:
        failures.append('no markdown comparison table detected')
    # Narrative after table
    narrative = '\n'.join(lines[table_end_idx:]) if table_found else ''
    narrative_words = len(re.findall(r'\S+', narrative))
    if table_found and narrative_words < 150:
        failures.append('narrative after table has %d words, below 150' % narrative_words)
    # If no table, also check overall word count signal
    if not table_found:
        total_words = len(re.findall(r'\S+', final))
        if total_words < 150:
            failures.append('total response has %d words, below 150' % total_words)
    evidence = [{'table_found': table_found, 'narrative_words': narrative_words}]
    if failures:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(failures), 'evidence_refs': evidence}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'markdown table present and narrative >=150 words', 'evidence_refs': evidence}
