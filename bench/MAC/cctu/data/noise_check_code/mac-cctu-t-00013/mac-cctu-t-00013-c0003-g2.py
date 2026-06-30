import re

def evaluate(trace):
    trace = trace or {}
    final = str(trace.get('final_response') or '')
    if not final.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'missing final response', 'evidence_refs': []}
    failures = []
    evidence = []
    # Check ends with period
    if not final.rstrip().endswith('.'):
        failures.append("response does not end with '.'")
    # Check tabular format (markdown table)
    lines = [ln for ln in final.strip().splitlines() if ln.strip()]
    table_lines = [ln for ln in lines if '|' in ln]
    has_separator = any(re.match(r'^\s*\|?\s*:?-{2,}:?\s*\|?\s*$', ln) for ln in table_lines)
    if not table_lines or not has_separator:
        failures.append('response is not in markdown tabular format')
        evidence.append({'table_lines': len(table_lines), 'has_separator': has_separator})
    else:
        # Parse table: expect single column, single data row
        def cells(ln):
            s = ln.strip()
            if s.startswith('|'): s = s[1:]
            if s.endswith('|'): s = s[:-1]
            return [c.strip() for c in s.split('|')]
        header_row = None
        sep_idx = None
        for i, ln in enumerate(table_lines):
            if re.match(r'^\s*\|?\s*:?-{2,}:?\s*\|?\s*$', ln):
                sep_idx = i
                break
        if sep_idx is not None and sep_idx > 0:
            header_row = cells(table_lines[sep_idx - 1])
            data_rows = [cells(ln) for ln in table_lines[sep_idx + 1:]]
        else:
            header_row = []
            data_rows = []
        col_count = len(header_row)
        if col_count != 1:
            failures.append(f'expected single column, found {col_count}')
        if len(data_rows) != 1:
            failures.append(f'expected single data row, found {len(data_rows)}')
        # Check date present in data row
        date_present = False
        date_patterns = [
            r'\b\d{4}-\d{1,2}-\d{1,2}\b',
            r'\b\d{1,2}/\d{1,2}/\d{2,4}\b',
            r'\b\d{1,2}-\d{1,2}-\d{2,4}\b',
            r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s*\d{4}\b',
            r'\b\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\b',
            r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\b',
            r'\b\d{4}\b',
        ]
        check_text = ' '.join(' '.join(r) for r in data_rows) if data_rows else ''
        for pat in date_patterns:
            if re.search(pat, check_text, re.IGNORECASE):
                date_present = True
                break
        if not date_present:
            failures.append('no recognizable date in table data row')
        evidence.append({'columns': col_count, 'data_rows': len(data_rows), 'date_present': date_present})
    if failures:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(failures[:6]), 'evidence_refs': evidence}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'ends with period and single-row/col table contains date', 'evidence_refs': evidence}
