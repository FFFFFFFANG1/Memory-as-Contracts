def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    lines = [l.rstrip() for l in text.splitlines()]
    bullet_re = re.compile(r'^\s*([\-\*\u2022\u2023\u25E6])\s+')
    bullets = [l for l in lines if bullet_re.match(l)]
    if len(bullets) < 2:
        return {'observed_followed': False, 'confidence':'medium','reason':'no bulleted list detected','evidence_refs':[]}
    # Detect groups: header lines (non-bullet, non-empty) followed by bullets
    groups = []
    current_header = None
    current_bullets = []
    for l in lines:
        if bullet_re.match(l):
            current_bullets.append(l)
        else:
            if l.strip():
                if current_header is not None or current_bullets:
                    groups.append((current_header, current_bullets))
                current_header = l.strip()
                current_bullets = []
    if current_header is not None or current_bullets:
        groups.append((current_header, current_bullets))
    groups = [g for g in groups if g[1]]
    if len(groups) < 1:
        return {'observed_followed': False,'confidence':'low','reason':'no grouping headers found','evidence_refs':[]}
    boundary_kw = re.compile(r'(plate|boundary|convergent|divergent|transform|subduction|ridge|fault|trench)', re.I)
    grouped_by_boundary = any(g[0] and boundary_kw.search(g[0]) for g in groups)
    if not grouped_by_boundary:
        return {'observed_followed': False,'confidence':'medium','reason':'groups not labeled by tectonic plate boundary','evidence_refs':[g[0] for g in groups if g[0]]}
    mag_re = re.compile(r'(?:magnitude|mag\.?|M[ _]?w?|M)\s*[:=]?\s*(\d+(?:\.\d+)?)', re.I)
    num_re = re.compile(r'(\d+\.\d+|\d+)')
    order_ok = True
    details = []
    for header, blist in groups:
        mags = []
        for b in blist:
            m = mag_re.search(b)
            if not m:
                m2 = num_re.search(b)
                if not m2:
                    mags = None
                    break
                mags.append(float(m2.group(1)))
            else:
                mags.append(float(m.group(1)))
        if mags is None:
            details.append(f'missing magnitudes in {header}')
            return {'observed_followed': None,'confidence':'low','reason':'could not parse magnitudes','evidence_refs':details}
        if mags != sorted(mags, reverse=True):
            order_ok = False
            details.append(f'group {header} order {mags}')
    if not order_ok:
        return {'observed_followed': False,'confidence':'high','reason':'bullets not sorted by magnitude desc','evidence_refs':details}
    return {'observed_followed': True,'confidence':'medium','reason':'bulleted, grouped by boundary, sorted desc','evidence_refs':[g[0] for g in groups]}
