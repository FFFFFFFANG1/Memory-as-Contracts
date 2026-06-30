def evaluate(trace):
    import re
    text = trace.get('final_response') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    # Find Latin binomial patterns: Genus species (Capitalized + lowercase)
    binomials = re.findall(r'\b[A-Z][a-z]+\s+[a-z]{3,}\b', text)
    # Heuristic: look for common species indicators
    # If no binomials found at all, likely not followed if species mentioned
    species_hints = re.search(r'\b(species|plant|tree|flower|animal|bird|fish|mammal|insect|fungus|shrub|herb)\b', text, re.I)
    if not species_hints and not binomials:
        return {'observed_followed': None,'confidence':'low','reason':'no clear species references detected','evidence_refs':[]}
    if binomials:
        return {'observed_followed': True,'confidence':'medium','reason':f'found likely binomials: {binomials[:5]}','evidence_refs': binomials[:5]}
    return {'observed_followed': False,'confidence':'low','reason':'species-like terms present but no Latin binomial detected','evidence_refs':[]}
