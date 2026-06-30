def evaluate(trace):
    import re
    text = trace.get('final_response') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown', 'reason':'empty response', 'evidence_refs': []}
    # Check for the word 'Final' (case-insensitive, word-bounded)
    final_hits = re.findall(r'\bfinal\b', text, flags=re.IGNORECASE)
    # American spellings to flag (presence suggests non-British)
    american_patterns = [
        (r'\bcolor(s|ed|ing|ful)?\b', 'color->colour'),
        (r'\bflavor(s|ed|ing|ful)?\b', 'flavor->flavour'),
        (r'\bhonor(s|ed|ing|able)?\b', 'honor->honour'),
        (r'\bbehavior(s|al)?\b', 'behavior->behaviour'),
        (r'\bfavor(s|ed|ing|ite|ites)?\b', 'favor->favour'),
        (r'\bneighbor(s|hood|ing)?\b', 'neighbor->neighbour'),
        (r'\blabor(s|ed|ing)?\b', 'labor->labour'),
        (r'\bcenter(s|ed|ing)?\b', 'center->centre'),
        (r'\bmeter(s)?\b', 'meter->metre'),
        (r'\btheater(s)?\b', 'theater->theatre'),
        (r'\borganiz(e|es|ed|ing|ation|ations)\b', 'organize->organise'),
        (r'\brecogniz(e|es|ed|ing)\b', 'recognize->recognise'),
        (r'\banalyz(e|es|ed|ing)\b', 'analyze->analyse'),
        (r'\brealiz(e|es|ed|ing)\b', 'realize->realise'),
        (r'\btraveling\b', 'traveling->travelling'),
        (r'\btraveled\b', 'traveled->travelled'),
        (r'\bdefense\b', 'defense->defence'),
        (r'\blicense\b', 'license(n)->licence'),
        (r'\bjewelry\b', 'jewelry->jewellery'),
        (r'\bcatalog(s|ed|ing)?\b', 'catalog->catalogue'),
        (r'\bdialog(s|ed|ing)?\b', 'dialog->dialogue'),
    ]
    american_found = []
    for pat, label in american_patterns:
        if re.search(pat, text, flags=re.IGNORECASE):
            american_found.append(label)
    issues = []
    if final_hits:
        issues.append(f"contains 'final' {len(final_hits)}x")
    if american_found:
        issues.append('American spellings: ' + ', '.join(american_found[:5]))
    if issues:
        return {'observed_followed': False, 'confidence':'high' if final_hits else 'medium', 'reason':'; '.join(issues), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence':'medium', 'reason':"no 'Final' usage and no obvious American spellings detected", 'evidence_refs': []}
