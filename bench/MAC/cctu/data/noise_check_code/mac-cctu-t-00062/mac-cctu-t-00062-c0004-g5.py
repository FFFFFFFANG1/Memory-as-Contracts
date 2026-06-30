def evaluate(trace):
    import re
    text = trace.get('final_response','') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    # Detect figures: numbers, percentages, or figure references
    figure_pattern = re.compile(r'(\d[\d,\.]*\s*%?|figure\s*\d+|fig\.?\s*\d+)', re.I)
    figures = figure_pattern.findall(text)
    if not figures:
        return {'observed_followed': None,'confidence':'unknown','reason':'no figures detected','evidence_refs':[]}
    low = text.lower()
    has_version = bool(re.search(r'(dataset\s+version|version\s+[\d v]|v\d+\.\d+|release\s+\d)', low))
    has_date = bool(re.search(r'(retriev|accessed|retrieval\s+date|as\s+of)', low))
    has_conf = bool(re.search(r'(confidence|disclaim|caveat|uncertain)', low))
    followed = has_version and has_date and has_conf
    return {'observed_followed': bool(followed),'confidence':'medium','reason':f'version={has_version} date={has_date} disclaimer={has_conf} figures_found={len(figures)}','evidence_refs':[]}
