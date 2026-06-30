def evaluate(trace):
    import re
    text = (trace.get('final_response') or '')
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No final response to evaluate.', 'evidence_refs': []}
    low = text.lower()
    has_workbook = any(k in low for k in ['workbook', 'xlsx', 'spreadsheet', '.xls'])
    has_sheets = bool(re.search(r'sheet\s*\d|multi[- ]sheet|sheets?\b|tab\s*\d|tabs?\b', low))
    has_endemic = 'endemic' in low
    has_elevation = any(k in low for k in ['elevation', 'altitud'])
    has_band = any(k in low for k in ['band', 'zone', 'belt', 'tier'])
    has_range = any(k in low for k in ['range', 'massif', 'mountain'])
    signals = {'workbook': has_workbook, 'sheets': has_sheets, 'endemic': has_endemic, 'elevation': has_elevation, 'band': has_band, 'range': has_range}
    score = sum(1 for v in signals.values() if v)
    followed = has_workbook and has_sheets and has_endemic and has_elevation and has_band and has_range
    if followed:
        conf = 'high'
    elif score >= 4:
        conf = 'medium'
    elif score >= 2:
        conf = 'low'
    else:
        conf = 'high' if not followed else 'low'
    return {'observed_followed': bool(followed), 'confidence': conf, 'reason': f'Signals present: {signals}', 'evidence_refs': []}
