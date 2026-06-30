def evaluate(trace):
    import re
    text = (trace.get('final_response') or '')
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    low = text.lower()
    comparison_terms = ['differ', 'higher', 'lower', 'compare', 'comparison', 'versus', ' vs', 'gap', 'better', 'worse', 'more than', 'less than']
    has_comparison = any(t in low for t in comparison_terms)
    if not has_comparison:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'no score comparison detected in response', 'evidence_refs': []}
    mentions_gpa = ('gpa' in low) or ('4.0 scale' in low) or ('4.0-scale' in low) or ('on a 4.0' in low) or ('out of 4.0' in low) or ('/4.0' in low)
    diff_pattern = re.search(r'[-+]?\d+(?:\.\d+)?\s*(?:gpa|points?\s*(?:on|of)\s*(?:a\s*)?4\.0|/\s*4\.0)', low)
    has_numeric_diff = bool(diff_pattern) or bool(re.search(r'difference\s+of\s+\d', low))
    if mentions_gpa and (has_numeric_diff or 'difference' in low or re.search(r'\d+\.\d+', text)):
        return {'observed_followed': True, 'confidence': 'medium', 'reason': 'comparison expressed on 4.0 GPA scale with numeric difference', 'evidence_refs': []}
    if not mentions_gpa:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'comparisons present but no 4.0 GPA scale normalization mentioned', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'low', 'reason': 'GPA mentioned but no clear numeric difference', 'evidence_refs': []}
