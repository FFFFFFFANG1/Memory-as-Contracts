def evaluate(trace):
    import re
    final=(trace.get('final_response') or '')
    traj=trace.get('trajectory') or []
    texts=[final]+[ (s.get('content') or '') for s in traj if isinstance(s,dict)]
    blob='\n'.join(t for t in texts if t)
    if not blob.strip():
        return {'observed_followed':None,'confidence':'unknown','reason':'No content to inspect.','evidence_refs':[]}
    lower=blob.lower()
    # Look for signs of premature normalization, dedup, or brand inference in the raw extraction phase
    suspicious_markers=[
        'deduplicated','de-duplicated','normalized','normalised','canonical form','canonicalized',
        'inferred brand','brand inferred','assumed brand','likely brand','probable brand',
        'merged duplicates','removed duplicates','after dedup','after normalization'
    ]
    hits=[m for m in suspicious_markers if m in lower]
    # Mention of 'raw', 'verbatim', 'as provided' suggests compliance
    compliance_markers=['verbatim','as provided','raw description','raw asset','without normalization','without deduplication']
    compliant_hits=[m for m in compliance_markers if m in lower]
    if hits and not compliant_hits:
        return {'observed_followed':False,'confidence':'low','reason':f'Possible early normalization/dedup/brand inference markers: {hits}','evidence_refs':hits}
    if compliant_hits and not hits:
        return {'observed_followed':True,'confidence':'low','reason':f'Compliance markers found: {compliant_hits}','evidence_refs':compliant_hits}
    return {'observed_followed':None,'confidence':'unknown','reason':'Insufficient evidence to determine verbatim storage behavior.','evidence_refs':[]}
