def evaluate(trace):
    import re
    resp = (trace.get('final_response') or '').strip()
    tools = ['election_info_retriever','event_information_extractor','historical_event_finder','historical_event_info_retriever','space_mission_event_finder','space_mission_info_retriever']
    if not resp:
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    # Split into sentence-like claims
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', resp) if s.strip()]
    if not sentences:
        return {'observed_followed': None,'confidence':'unknown','reason':'no sentences','evidence_refs':[]}
    claim_like = []
    for s in sentences:
        # crude factual-claim heuristic: contains a digit/year or proper noun-ish capitalized word besides first
        if re.search(r'\b(19|20)\d{2}\b', s) or re.search(r'\b\d+\b', s) or re.search(r'[A-Z][a-z]+\s+[A-Z][a-z]+', s):
            claim_like.append(s)
    if not claim_like:
        return {'observed_followed': None,'confidence':'low','reason':'no clear factual claims detected','evidence_refs':[]}
    bad = []
    for s in claim_like:
        names = [t for t in tools if t in s]
        if len(set(names)) < 3:
            bad.append(s[:120])
    if bad:
        return {'observed_followed': False,'confidence':'medium','reason': f'{len(bad)} claim(s) lack 3 inline tool names','evidence_refs': bad[:3]}
    return {'observed_followed': True,'confidence':'medium','reason':'all detected claims have >=3 inline tool names','evidence_refs':[]}
