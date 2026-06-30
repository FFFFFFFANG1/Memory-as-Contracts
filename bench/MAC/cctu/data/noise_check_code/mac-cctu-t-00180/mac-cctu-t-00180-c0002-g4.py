def evaluate(trace):
    import re
    text = trace.get('final_response','') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    # Pattern for scientific notation with 3 sig figs: d.dd e±dd or d.dd × 10^±dd
    sci_e = r'[-+]?\d\.\d{2}[eE][-+]?\d+'
    sci_times = r'[-+]?\d\.\d{2}\s*[x×*]\s*10\s*\^?\s*[-+]?\d+'
    sci_sup = r'[-+]?\d\.\d{2}\s*[x×*]\s*10[⁻⁺]?[⁰¹²³⁴⁵⁶⁷⁸⁹]+'
    sci_pat = f'(?:{sci_e}|{sci_times}|{sci_sup})'
    # Unit in parentheses immediately after
    full_pat = sci_pat + r'\s*\([^)]+\)'
    # Find any standalone numbers that look quantitative
    # Generic number pattern (excluding pure years, list numbers)
    num_pat = r'(?<![\w.])[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?(?![\w])'
    numbers = re.findall(num_pat, text)
    if not numbers:
        return {'observed_followed': None,'confidence':'unknown','reason':'no quantitative values found','evidence_refs':[]}
    sci_matches = re.findall(full_pat, text)
    # Count plain numbers not part of a sci+unit construct
    # Remove sci+unit occurrences then count remaining numbers
    cleaned = re.sub(full_pat, ' ', text)
    # Also remove bare sci notation without unit (still violates but separately)
    remaining_nums = re.findall(num_pat, cleaned)
    # Filter out trivial integers that are likely IDs/years/list markers? Keep strict.
    if not sci_matches:
        return {'observed_followed': False,'confidence':'high','reason':'no scientific-notation values with SI unit in parentheses detected','evidence_refs':[text[:200]]}
    if remaining_nums:
        return {'observed_followed': False,'confidence':'medium','reason':f'found numeric values not in required sci-notation+unit form: {remaining_nums[:5]}','evidence_refs':sci_matches[:3]}
    return {'observed_followed': True,'confidence':'medium','reason':'all numeric values in scientific notation with 3 sig figs and SI unit','evidence_refs':sci_matches[:3]}
