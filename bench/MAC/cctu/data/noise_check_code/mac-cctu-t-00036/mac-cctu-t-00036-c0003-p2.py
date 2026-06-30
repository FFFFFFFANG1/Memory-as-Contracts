def evaluate(trace):
    import re
    text = (trace.get('final_response') or '')
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    low = text.lower()
    # Detect Spanish markers
    es_markers = ['español','espanol','recomendación','recomendacion','dieta','región','region','salud','alimentación','alimentacion','nutrición','nutricion',' y ',' la ',' el ',' los ',' las ']
    en_markers = ['english','recommendation','diet','region','health','nutrition',' the ',' and ',' for ']
    es_hits = sum(1 for m in es_markers if m in low)
    en_hits = sum(1 for m in en_markers if m in low)
    bilingual = es_hits >= 2 and en_hits >= 2
    # Region-specific dietary recommendation heuristic
    has_diet = any(w in low for w in ['diet','dietary','dieta','alimentación','alimentacion','nutrition','nutrición','nutricion'])
    has_region = any(w in low for w in ['region','región','regional','area','zone','country','local'])
    has_reco = any(w in low for w in ['recommend','recomend'])
    region_diet = has_diet and has_region and has_reco
    followed = bilingual and region_diet
    return {'observed_followed': bool(followed), 'confidence': 'medium', 'reason': f'bilingual={bilingual} (es_hits={es_hits}, en_hits={en_hits}), region_diet={region_diet}', 'evidence_refs': []}
