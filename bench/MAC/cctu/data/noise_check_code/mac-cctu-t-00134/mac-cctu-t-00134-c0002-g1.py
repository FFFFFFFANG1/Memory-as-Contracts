import re
def evaluate(trace):
    resp = (trace.get('final_response') or '').strip()
    if not resp:
        return {'observed_followed': None, 'confidence':'unknown','reason':'No final response','evidence_refs':[]}
    # Allow trailing whitespace/newlines
    m = re.search(r'Seismic Gap:\s*\d+(?:\.\d+)?\s*days\.\s*$', resp)
    if m:
        return {'observed_followed': True, 'confidence':'high','reason':'Response ends with required Seismic Gap phrase','evidence_refs':[m.group(0)]}
    return {'observed_followed': False, 'confidence':'high','reason':'Response does not end with "Seismic Gap: [number] days."','evidence_refs':[resp[-80:]]}
