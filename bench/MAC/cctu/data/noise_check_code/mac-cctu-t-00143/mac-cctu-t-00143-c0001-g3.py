def evaluate(trace):
    import re
    text = trace.get('final_response','') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    low = text.lower()
    anatomy_terms = ['anatom', 'skeleton', 'organ', 'bone', 'muscle', 'limb', 'skull', 'vertebr']
    has_anatomy = any(t in low for t in anatomy_terms)
    if not has_anatomy:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'no anatomical comparison detected in final response', 'evidence_refs': []}
    tree_chars = ['├', '└', '│', '┬', '┤', '┌', '┐']
    has_unicode_tree = any(c in text for c in tree_chars)
    ascii_pattern = re.search(r'(\|--|\+--|`--|/--|\\--|---+)', text)
    phylo_mention = 'phylogen' in low or 'tree' in low or 'clade' in low
    looks_like_tree = has_unicode_tree or (ascii_pattern is not None and phylo_mention)
    if looks_like_tree:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': 'anatomical content with ASCII/unicode tree diagram present', 'evidence_refs': ['final_response']}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': 'anatomical content present but no ASCII phylogenetic tree diagram detected', 'evidence_refs': ['final_response']}
