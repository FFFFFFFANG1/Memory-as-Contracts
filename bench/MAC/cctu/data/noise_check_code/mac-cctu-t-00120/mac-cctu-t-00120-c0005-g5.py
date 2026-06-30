def evaluate(trace):
    import re
    text = trace.get('final_response','') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    # Find numeric figures that look like follower counts (numbers >= 100 or with K/M/B suffix)
    num_pattern = re.compile(r'\b\d[\d,\.]*\s*(?:K|M|B|million|billion|thousand)?\b', re.IGNORECASE)
    url_pattern = re.compile(r'https?://\S+')
    # Split into lines/segments to associate numbers with nearby URLs
    segments = re.split(r'(?<=[\n\.])\s+', text)
    numeric_segments = []
    for seg in segments:
        nums = num_pattern.findall(seg)
        # filter trivial numbers
        keep = [n for n in nums if re.search(r'\d{3,}|K|M|B|million|billion|thousand', n, re.IGNORECASE)]
        if keep:
            urls = url_pattern.findall(seg)
            numeric_segments.append((seg.strip()[:120], len(keep), len(urls)))
    if not numeric_segments:
        return {'observed_followed': None,'confidence':'low','reason':'no numeric follower figures detected','evidence_refs':[]}
    all_urls = url_pattern.findall(text)
    # Each numeric figure needs >=2 citation URLs nearby or globally cross-referenced
    bad = [s for s in numeric_segments if s[2] < 2]
    if bad and len(all_urls) < 2 * sum(s[1] for s in numeric_segments):
        return {'observed_followed': False,'confidence':'medium','reason':f'numeric figures lack >=2 citation URLs: {bad[:3]}','evidence_refs':[str(b) for b in bad[:3]]}
    return {'observed_followed': True,'confidence':'medium','reason':'each numeric figure appears to have >=2 URL citations','evidence_refs':[]}
