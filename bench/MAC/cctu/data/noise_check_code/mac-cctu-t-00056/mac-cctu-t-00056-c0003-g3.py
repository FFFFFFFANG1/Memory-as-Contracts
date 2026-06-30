import re
import csv as csvmod
import io

def evaluate(trace):
    trace = trace or {}
    final = str(trace.get('final_response') or '').strip()
    if not final:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'missing final response', 'evidence_refs': []}
    failures = []
    evidence = []
    # Try to parse as CSV
    try:
        reader = list(csvmod.reader(io.StringIO(final)))
    except Exception as e:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'CSV parse error: {e}', 'evidence_refs': []}
    non_empty = [row for row in reader if any((c or '').strip() for c in row)]
    if len(non_empty) < 2:
        failures.append('CSV must include header and at least one data row')
    header = [c.strip().lower() for c in (non_empty[0] if non_empty else [])]
    evidence.append({'header': header, 'row_count': len(non_empty)})
    expected_cols = {
        'port': ['port'],
        'vessel': ['vessel'],
        'species': ['catch species', 'species', 'catch'],
        'date': ['landing date', 'date'],
    }
    col_idx = {}
    for key, aliases in expected_cols.items():
        idx = None
        for i, h in enumerate(header):
            if any(a == h or a in h for a in aliases):
                idx = i
                break
        if idx is None:
            failures.append(f'missing column for {key}')
        else:
            col_idx[key] = idx
    # Check date format in data rows
    date_pat = re.compile(r'\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}\s+\w+\s+\d{2,4}|\w+\s+\d{1,2},?\s+\d{4}')
    if 'date' in col_idx:
        date_i = col_idx['date']
        bad = 0
        total = 0
        for row in non_empty[1:]:
            if date_i < len(row):
                val = (row[date_i] or '').strip()
                if val:
                    total += 1
                    if not date_pat.search(val):
                        bad += 1
        if total == 0:
            failures.append('no landing date values present')
        elif bad > 0:
            failures.append(f'{bad}/{total} landing dates not in recognizable date format')
        evidence.append({'date_total': total, 'date_bad': bad})
    # Check narrative prose: lines outside CSV structure
    lines = [ln for ln in final.splitlines() if ln.strip()]
    if lines:
        col_count = len(non_empty[0]) if non_empty else 0
        prose_lines = []
        for ln in lines:
            try:
                parts = next(csvmod.reader([ln]))
            except Exception:
                parts = [ln]
            # A CSV row should have multiple comma-separated fields matching column count roughly
            if len(parts) < max(2, col_count - 1):
                prose_lines.append(ln)
        if prose_lines:
            failures.append(f'narrative prose lines detected: {len(prose_lines)}')
            evidence.append({'prose_sample': prose_lines[:3]})
    if failures:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(failures[:6]), 'evidence_refs': evidence}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'CSV with required columns and no prose', 'evidence_refs': evidence}
