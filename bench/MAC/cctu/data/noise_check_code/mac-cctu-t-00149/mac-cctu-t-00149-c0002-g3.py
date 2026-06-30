def evaluate(trace):
    import re
    text = trace.get('final_response') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    # Find score citations - look for numeric scores
    score_pattern = re.compile(r'\b(?:score|rating|grade)[^\n]{0,40}?\d', re.IGNORECASE)
    scores = score_pattern.findall(text)
    if not scores:
        # fallback: look for standalone numeric scores like 'X/Y' or '8.5'
        scores = re.findall(r'\b\d+(?:\.\d+)?\s*/\s*\d+', text)
    if not scores:
        return {'observed_followed': None,'confidence':'unknown','reason':'no score citations detected','evidence_refs':[]}
    low = text.lower()
    has_transcript = bool(re.search(r'transcript\s*id|source\s*transcript', low))
    has_timestamp = bool(re.search(r'timestamp|retriev(ed|al)\s*(at|time|on)|\d{4}-\d{2}-\d{2}', low))
    has_initials = bool(re.search(r'verifier\s*initials|initials\s*[:=]|verified by', low))
    all_present = has_transcript and has_timestamp and has_initials
    return {
        'observed_followed': all_present,
        'confidence': 'medium',
        'reason': f'transcript_id={has_transcript}, timestamp={has_timestamp}, initials={has_initials}, scores_found={len(scores)}',
        'evidence_refs': []
    }
