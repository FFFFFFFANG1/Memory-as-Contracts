def evaluate(trace):
    import re
    text = (trace.get('final_response') or '')
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    low = text.lower()
    # Look for per-resolution breakdown indicators
    per_res_patterns = [r'resolution\s*(no\.?|number|#)?\s*\d', r's/res/', r'draft resolution', r'per[-\s]resolution', r'resolution-by-resolution']
    per_res_hits = [p for p in per_res_patterns if re.search(p, low)]
    # Look for aggregated ranked list of states
    countries = ['united states','usa','russia','soviet','ussr','china','united kingdom','uk','britain','france']
    country_hits = [c for c in countries if c in low]
    has_numbers = bool(re.search(r'\d+', text))
    # Ranked list indicators
    ranked = bool(re.search(r'(^|\n)\s*(\d+[\.\)]|[-*])\s', text)) or 'rank' in low or 'total' in low
    if per_res_hits:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'per-resolution breakdown indicators: {per_res_hits}', 'evidence_refs': []}
    if len(country_hits) >= 2 and has_numbers and ranked:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': 'aggregated per-state ranked tallies without per-resolution detail', 'evidence_refs': []}
    if len(country_hits) >= 1 and has_numbers:
        return {'observed_followed': True, 'confidence': 'low', 'reason': 'state-level tallies present, no resolution breakdown found', 'evidence_refs': []}
    return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'insufficient evidence of veto tally reporting', 'evidence_refs': []}
