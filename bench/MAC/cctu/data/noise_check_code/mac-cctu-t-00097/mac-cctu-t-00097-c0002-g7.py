def evaluate(trace):
    import re
    text = trace.get('final_response') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No final response to evaluate.', 'evidence_refs': []}
    contractions = ["n't", "'re", "'ve", "'ll", "'d", "'m", "'s ", "won't", "can't", "don't", "isn't", "aren't", "wasn't", "weren't", "haven't", "hasn't", "hadn't", "didn't", "doesn't", "wouldn't", "shouldn't", "couldn't", "it's", "that's", "there's", "I'm", "you're", "we're", "they're", "I've", "you've", "we've", "they've", "I'll", "you'll", "he'll", "she'll", "we'll", "they'll", "I'd", "you'd", "he'd", "she'd", "we'd", "they'd"]
    low = text.lower()
    found_contractions = [c for c in contractions if c.lower() in low]
    american_patterns = [r'\b\w+ize\b', r'\b\w+ized\b', r'\b\w+izing\b', r'\b\w+ization\b', r'\bcolor\b', r'\bcolors\b', r'\bfavor\b', r'\bfavorite\b', r'\bhonor\b', r'\bbehavior\b', r'\blabor\b', r'\bneighbor\b', r'\bcenter\b', r'\bmeter\b', r'\btheater\b', r'\bfiber\b', r'\bliter\b', r'\btraveled\b', r'\btraveling\b', r'\bcanceled\b', r'\bdefense\b', r'\boffense\b', r'\blicense\b', r'\banalyze\b', r'\bcatalog\b', r'\bdialog\b', r'\bprogram\b']
    american_hits = []
    for pat in american_patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            w = m.group(0).lower()
            if w in ('program','programs','programme','programmes'):
                continue
            if w.endswith('ize') or w.endswith('ized') or w.endswith('izing') or w.endswith('ization'):
                allow = {'size','sized','sizing','prize','prized','seize','seized','seizing'}
                if w in allow:
                    continue
            american_hits.append(w)
    if found_contractions or american_hits:
        reason = ''
        if found_contractions:
            reason += 'Contractions present: ' + ', '.join(sorted(set(found_contractions))[:5]) + '. '
        if american_hits:
            reason += 'Possible American spellings: ' + ', '.join(sorted(set(american_hits))[:5]) + '.'
        return {'observed_followed': False, 'confidence': 'medium', 'reason': reason.strip(), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'No contractions or common American spellings detected.', 'evidence_refs': []}
