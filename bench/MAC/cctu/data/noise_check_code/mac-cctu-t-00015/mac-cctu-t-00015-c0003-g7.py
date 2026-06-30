def evaluate(trace):
    import re
    text = trace.get('final_response') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    era_names = ['Reiwa','Heisei','Showa','Shōwa','Taisho','Taishō','Meiji','令和','平成','昭和','大正','明治']
    has_era = any(e.lower() in text.lower() for e in era_names)
    # Gregorian date: a 4-digit year, optionally with month
    has_gregorian = bool(re.search(r'\b(18|19|20)\d{2}\b', text))
    # IHA bulletin: look for bulletin/告示/官報 reference with number, or 'Imperial Household Agency' plus number
    bulletin_patterns = [r'(?i)imperial household agency[^\n]{0,80}(no\.?|bulletin|notice|#)\s*\d+', r'(?i)bulletin\s*(no\.?|#)?\s*\d+', r'宮内庁[^\n]{0,40}\d+', r'告示[^\n]{0,20}\d+', r'官報[^\n]{0,20}\d+']
    has_bulletin = any(re.search(p, text) for p in bulletin_patterns)
    followed = has_era and has_gregorian and has_bulletin
    reason = f'era={has_era}, gregorian={has_gregorian}, bulletin={has_bulletin}'
    return {'observed_followed': bool(followed), 'confidence': 'medium', 'reason': reason, 'evidence_refs': []}
