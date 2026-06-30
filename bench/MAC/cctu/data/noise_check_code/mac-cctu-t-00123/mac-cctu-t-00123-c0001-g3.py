def evaluate(trace):
    import re
    resp = trace.get('final_response','') or ''
    if not resp.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    movement_terms = ['baroque','classical era','romantic','romanticism','renaissance','medieval music','impressionis','modernis','jazz','blues','bebop','swing era','rock','hip-hop','minimalis','serialis','atonal','nationalis','expressionis','neoclassic','avant-garde','folk revival','disco','punk','new wave','grunge']
    low = resp.lower()
    mentions = [t for t in movement_terms if t in low]
    if not mentions:
        return {'observed_followed': None,'confidence':'low','reason':'no historical musical movement claims detected','evidence_refs':[]}
    citation_patterns = [r'\[tool[_\s-]?call[_\s-]?\w+\]', r'\[call[_\s-]?\d+\]', r'\[#?\d+\]', r'\(tool[_\s:-]?\w+\)', r'\[(composer_works_merged|astronomical_event_finder|corporate_employee_tracker|population_data_retriever|storage_info_retriever|train_route_info)[^\]]*\]', r'\bsource:\s*\S+', r'\bcitation:\s*\S+']
    found = []
    for p in citation_patterns:
        m = re.findall(p, resp, flags=re.IGNORECASE)
        if m:
            found.extend(m)
    # Heuristic: need at least one citation per mentioned movement term (approx)
    sentences = re.split(r'(?<=[.!?])\s+', resp)
    claim_sents = [s for s in sentences if any(t in s.lower() for t in movement_terms)]
    cited_sents = 0
    for s in claim_sents:
        if any(re.search(p, s, flags=re.IGNORECASE) for p in citation_patterns):
            cited_sents += 1
    if not claim_sents:
        return {'observed_followed': None,'confidence':'low','reason':'movement terms present but no claim sentences isolated','evidence_refs':[]}
    if cited_sents == len(claim_sents) and cited_sents > 0:
        return {'observed_followed': True,'confidence':'medium','reason':f'all {cited_sents} movement-claim sentences contain citation-like refs','evidence_refs': found[:5]}
    if cited_sents == 0:
        return {'observed_followed': False,'confidence':'high','reason':f'{len(claim_sents)} claim sentences without inline citations','evidence_refs':[]}
    return {'observed_followed': False,'confidence':'medium','reason':f'only {cited_sents}/{len(claim_sents)} claim sentences cited','evidence_refs': found[:5]}
