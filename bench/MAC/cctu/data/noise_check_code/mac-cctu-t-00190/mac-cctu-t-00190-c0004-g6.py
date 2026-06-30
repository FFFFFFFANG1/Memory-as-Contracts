def evaluate(trace):
    import re
    text = trace.get('final_response','') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    imperial_pat = re.compile(r'\b\d+(?:[.,]\d+)?\s*(feet|foot|ft|inches|inch|in\b|yards|yard|yd|miles|mile|mi\b|gallons|gallon|gal|pounds|pound|lbs|lb|ounces|ounce|oz)\b', re.IGNORECASE)
    metric_pat = re.compile(r'\b\d+(?:[.,]\d+)?\s*(meters?|metres?|m\b|kilometers?|kilometres?|km\b|centimeters?|centimetres?|cm\b|millimeters?|millimetres?|mm\b|kilograms?|kg\b|grams?|g\b|liters?|litres?|l\b|hectares?|ha\b)', re.IGNORECASE)
    any_number_unit = re.compile(r'\b\d+(?:[.,]\d+)?\s*[A-Za-z]+', re.IGNORECASE)
    imperial_hits = imperial_pat.findall(text)
    metric_hits = metric_pat.findall(text)
    numbers = any_number_unit.findall(text)
    if not numbers:
        return {'observed_followed': None,'confidence':'unknown','reason':'no measurements detected in response','evidence_refs':[]}
    # If only metric units present, considered followed (no original to annotate)
    if imperial_hits and not metric_hits:
        return {'observed_followed': False,'confidence':'high','reason':f'Found imperial units {imperial_hits} without metric conversions','evidence_refs':[]}
    if imperial_hits and metric_hits:
        # Check annotation pattern: metric with imperial in parentheses or vice versa
        annot_pat = re.compile(r'\d+(?:[.,]\d+)?\s*(?:m|km|cm|mm|kg|g|l|liters?|litres?|meters?|metres?|kilometers?|kilometres?)\b[^\n.;]{0,40}\(?\s*(?:originally|orig\.?|approx\.?|~)?\s*\d+(?:[.,]\d+)?\s*(?:feet|foot|ft|inches|inch|in|yards|yard|yd|miles|mile|mi|gallons|gallon|gal|pounds|pound|lbs|lb)', re.IGNORECASE)
        reverse_annot = re.compile(r'\d+(?:[.,]\d+)?\s*(?:feet|foot|ft|inches|inch|in|yards|yard|yd|miles|mile|mi|gallons|gal|pounds|lbs|lb)[^\n.;]{0,40}\(?\s*\d+(?:[.,]\d+)?\s*(?:m|km|cm|mm|kg|l|meters?|metres?|kilometers?|kilometres?)\b', re.IGNORECASE)
        if annot_pat.search(text) or reverse_annot.search(text):
            return {'observed_followed': True,'confidence':'medium','reason':'Found metric values with original units annotated','evidence_refs':[]}
        return {'observed_followed': False,'confidence':'low','reason':'Both unit systems present but annotation pairing unclear','evidence_refs':[]}
    return {'observed_followed': None,'confidence':'unknown','reason':'no clear unit-bearing measurements found','evidence_refs':[]}
