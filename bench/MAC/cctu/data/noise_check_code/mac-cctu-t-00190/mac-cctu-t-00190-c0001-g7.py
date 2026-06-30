import re
def evaluate(trace):
    exonyms = {
        'München':'Munich','Köln':'Cologne','Wien':'Vienna','Praha':'Prague',
        'Moskva':'Moscow','Roma':'Rome','Firenze':'Florence','Venezia':'Venice',
        'Napoli':'Naples','Torino':'Turin','Milano':'Milan','Genova':'Genoa',
        'Lisboa':'Lisbon','Warszawa':'Warsaw','Bucureşti':'Bucharest','București':'Bucharest',
        'Kraków':'Krakow','Beograd':'Belgrade','Athina':'Athens','Αθήνα':'Athens',
        'København':'Copenhagen','Göteborg':'Gothenburg','Den Haag':'The Hague',
        'Brugge':'Bruges','Antwerpen':'Antwerp','Gent':'Ghent','Genève':'Geneva',
        'Zürich':'Zurich','Sevilla':'Seville','Praga':'Prague','Bruxelles':'Brussels',
        'Bodensee':'Lake Constance','Genfersee':'Lake Geneva','Lac Léman':'Lake Geneva',
        'Vierwaldstättersee':'Lake Lucerne','Lago di Como':'Lake Como',
        'Lago di Garda':'Lake Garda','Lago Maggiore':'Lake Maggiore'
    }
    tool_text = ''
    for tc in trace.get('tool_calls', []) or []:
        r = tc.get('result')
        if r is not None:
            tool_text += ' ' + str(r)
    present = [k for k in exonyms if k in tool_text]
    if not present:
        return {'observed_followed': None, 'confidence':'unknown', 'reason':'No detectable foreign proper nouns in tool outputs.', 'evidence_refs':[]}
    out_parts = [str(trace.get('final_response') or '')]
    for step in trace.get('trajectory', []) or []:
        c = step.get('content')
        if c: out_parts.append(str(c))
    out_text = ' \n '.join(out_parts)
    violations = [k for k in present if k in out_text]
    if violations:
        return {'observed_followed': False, 'confidence':'high', 'reason': 'Foreign proper noun(s) appeared untranslated in output: ' + ', '.join(violations), 'evidence_refs': violations}
    return {'observed_followed': True, 'confidence':'medium', 'reason':'Foreign proper nouns from tool output were not echoed verbatim; exonym usage plausible.', 'evidence_refs': present}
