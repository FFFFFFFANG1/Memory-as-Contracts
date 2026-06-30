def evaluate(trace):
    import re
    text = trace.get('final_response','') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    countries = ['Afghanistan','Albania','Algeria','Andorra','Angola','Argentina','Armenia','Australia','Austria','Azerbaijan','Bahamas','Bahrain','Bangladesh','Barbados','Belarus','Belgium','Belize','Benin','Bhutan','Bolivia','Bosnia','Botswana','Brazil','Brunei','Bulgaria','Burkina Faso','Burundi','Cambodia','Cameroon','Canada','Chad','Chile','China','Colombia','Comoros','Congo','Costa Rica','Croatia','Cuba','Cyprus','Czechia','Czech Republic','Denmark','Djibouti','Dominica','Ecuador','Egypt','El Salvador','Eritrea','Estonia','Eswatini','Ethiopia','Fiji','Finland','France','Gabon','Gambia','Georgia','Germany','Ghana','Greece','Grenada','Guatemala','Guinea','Guyana','Haiti','Honduras','Hungary','Iceland','India','Indonesia','Iran','Iraq','Ireland','Israel','Italy','Jamaica','Japan','Jordan','Kazakhstan','Kenya','Kiribati','Kuwait','Kyrgyzstan','Laos','Latvia','Lebanon','Lesotho','Liberia','Libya','Liechtenstein','Lithuania','Luxembourg','Madagascar','Malawi','Malaysia','Maldives','Mali','Malta','Mauritania','Mauritius','Mexico','Moldova','Monaco','Mongolia','Montenegro','Morocco','Mozambique','Myanmar','Namibia','Nauru','Nepal','Netherlands','New Zealand','Nicaragua','Niger','Nigeria','Norway','Oman','Pakistan','Palau','Panama','Paraguay','Peru','Philippines','Poland','Portugal','Qatar','Romania','Russia','Rwanda','Samoa','Senegal','Serbia','Singapore','Slovakia','Slovenia','Somalia','South Africa','South Korea','South Sudan','Spain','Sri Lanka','Sudan','Suriname','Sweden','Switzerland','Syria','Taiwan','Tajikistan','Tanzania','Thailand','Togo','Tonga','Tunisia','Turkey','Turkmenistan','Tuvalu','Uganda','Ukraine','United Arab Emirates','United Kingdom','UK','United States','USA','U.S.','Uruguay','Uzbekistan','Vanuatu','Venezuela','Vietnam','Yemen','Zambia','Zimbabwe','North Korea','Soviet Union','USSR','Yugoslavia','Czechoslovakia','East Germany','West Germany']
    iso = r'\(\s*\d{4}-\d{2}-\d{2}\s*\)'
    found_any = False
    bad = []
    for c in countries:
        for m in re.finditer(r'\b' + re.escape(c) + r'\b', text):
            found_any = True
            tail = text[m.end():m.end()+30]
            if not re.match(r'\s*' + iso, tail):
                bad.append(c + ' @' + str(m.start()))
                if len(bad) >= 5: break
        if len(bad) >= 5: break
    if not found_any:
        return {'observed_followed': None,'confidence':'low','reason':'no recognizable country names found','evidence_refs':[]}
    if bad:
        return {'observed_followed': False,'confidence':'medium','reason':'country mentions missing ISO date in parens: ' + '; '.join(bad),'evidence_refs':bad}
    return {'observed_followed': True,'confidence':'medium','reason':'each detected country followed by (YYYY-MM-DD)','evidence_refs':[]}
