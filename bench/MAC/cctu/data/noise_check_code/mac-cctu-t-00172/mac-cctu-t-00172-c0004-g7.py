def evaluate(trace):
    import re
    text = (trace.get('final_response') or '')
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No final response.', 'evidence_refs': []}
    american = ['color','colors','flavor','flavors','honor','honors','labor','labors','neighbor','neighbors','organize','organized','organizes','organizing','realize','realized','realizes','realizing','recognize','recognized','analyze','analyzed','analyzes','center','centers','theater','theaters','traveled','traveling','catalog','catalogs','defense','offense','license ','program ']
    lower = text.lower()
    am_hits = [w for w in american if re.search(r'\b'+re.escape(w.strip())+r'\b', lower)]
    british_markers = ['colour','flavour','honour','labour','neighbour','organise','organised','realise','realised','recognise','recognised','analyse','analysed','centre','theatre','travelled','travelling','catalogue','defence','offence','licence','programme']
    br_hits = [w for w in british_markers if re.search(r'\b'+w+r'\b', lower)]
    # Detect cultural briefing summary: a single sentence labelled or at end
    has_label = bool(re.search(r'cultural briefing|cultural summary|briefing[: ]', text, re.I))
    # Approximate single-sentence: last non-empty line contains exactly one terminal punctuation
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    last = lines[-1] if lines else ''
    sentences = re.findall(r'[^.!?]+[.!?]', last)
    one_sentence = len(sentences) == 1
    summary_ok = has_label and one_sentence
    if am_hits:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'American spellings found: {am_hits}', 'evidence_refs': []}
    if not summary_ok:
        return {'observed_followed': False, 'confidence': 'low', 'reason': f'Cultural briefing summary missing or not one sentence. label={has_label} one_sentence={one_sentence}', 'evidence_refs': []}
    conf = 'high' if br_hits else 'low'
    return {'observed_followed': True, 'confidence': conf, 'reason': f'No American spellings; cultural briefing present. British markers: {br_hits}', 'evidence_refs': []}
