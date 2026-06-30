def evaluate(trace):
    import re
    text = trace.get('final_response') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    low = text.lower()
    has_table = ('|' in text and text.count('|') >= 4) or bool(re.search(r'(?m)^\s*\|.*\|', text))
    years = re.findall(r'\b\d{3,4}\s*(?:BCE|BC|CE|AD|B\.C\.|A\.D\.)?\b', text)
    has_lifespan = bool(re.search(r'\d{3,4}\s*[-–—]\s*\d{3,4}', text)) or len(years) >= 4
    mentions_phil = 'philosoph' in low or 'lifespan' in low or 'born' in low or 'died' in low
    if not (has_table and has_lifespan and mentions_phil):
        return {'observed_followed': False, 'confidence':'medium','reason':'missing table, lifespans, or philosopher context','evidence_refs':[]}
    # Check chronological order of first year per row
    rows = [r for r in text.splitlines() if r.strip().startswith('|')]
    first_years = []
    for r in rows:
        m = re.search(r'(\d{3,4})', r)
        if m:
            yr = int(m.group(1))
            # adjust BCE as negative
            if re.search(r'\d{3,4}\s*(BCE|BC|B\.C\.)', r, re.I):
                yr = -yr
            first_years.append(yr)
    chronological = len(first_years) < 2 or all(first_years[i] <= first_years[i+1] for i in range(len(first_years)-1)) or all(first_years[i] >= first_years[i+1] for i in range(len(first_years)-1))
    return {'observed_followed': bool(chronological), 'confidence':'medium','reason': f'table={has_table} lifespans={has_lifespan} chronological={chronological}','evidence_refs':[]}
