def evaluate(trace):
    import re
    response = str(trace.get('final_response') or '').strip()
    if not response:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'empty response', 'evidence_refs': []}
    # Extract first sentence
    m = re.match(r'\s*(.+?[\.!?])(\s|$)', response, re.DOTALL)
    first = m.group(1).strip() if m else response.split('\n')[0].strip()
    if not first:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no opening sentence', 'evidence_refs': []}
    low = first.lower()
    # Check for date: look for year, month names, or numeric date patterns
    months = ['january','february','march','april','may','june','july','august','september','october','november','december','jan','feb','mar','apr','jun','jul','aug','sep','sept','oct','nov','dec']
    has_year = bool(re.search(r'\b(1[6-9]\d{2}|20\d{2}|21\d{2})\b', first))
    has_month = any(mo in low for mo in months)
    has_numeric_date = bool(re.search(r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b', first)) or bool(re.search(r'\b\d{4}-\d{2}-\d{2}\b', first))
    has_date = has_year or has_month or has_numeric_date
    # Check for figure-type keyword (number/percentage/count/total/figure indicators)
    figure_terms = ['percent','percentage','%','votes','vote count','margin','total','number','count','turnout','share','tally','figure','statistic','rate','results','casualties','fatalities','injuries','deaths','toll']
    has_figure_type = any(t in low for t in figure_terms)
    # Check that it looks like a summary (has some content - event reference)
    # Heuristic: sentence must have at least 6 words to plausibly include event+date+figure
    word_count = len(first.split())
    has_event = word_count >= 6
    missing = []
    if not has_date:
        missing.append('date')
    if not has_figure_type:
        missing.append('type of figure')
    if not has_event:
        missing.append('event reference (sentence too short)')
    if missing:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'opening sentence missing: ' + ', '.join(missing), 'evidence_refs': [first[:200]]}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'opening sentence references event, date, and figure type', 'evidence_refs': [first[:200]]}
