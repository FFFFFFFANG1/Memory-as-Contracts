def evaluate(trace):
    text = (trace.get('final_response') or '')
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    low = text.lower()
    vary_terms = ['vary by source','varies by source','differ by source','vary depending on','vary among sources','differ between sources','sources vary','sources differ','depending on the source']
    highest_terms = ['highest cited','highest reported','highest available','highest figure','highest value','maximum reported','tallest cited','greatest cited']
    has_vary = any(t in low for t in vary_terms)
    has_highest = any(t in low for t in highest_terms)
    mentions_waterfall_measure = ('waterfall' in low) and any(w in low for w in ['height','measurement','measure'])
    followed = has_vary and has_highest and mentions_waterfall_measure
    return {'observed_followed': bool(followed),'confidence':'medium' if followed else 'low','reason': f'vary={has_vary} highest={has_highest} waterfall_measure={mentions_waterfall_measure}','evidence_refs':[]}
