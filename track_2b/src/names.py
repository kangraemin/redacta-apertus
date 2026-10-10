"""Synthetic but plausible Swiss names, streets and towns used to refill placeholders.

Common first names and surnames by language region. No combination refers to a
real party: names are drawn at random and never taken from the decision itself.
"""

FIRST = {
    "de": ["Andreas", "Barbara", "Beat", "Claudia", "Daniel", "Daniela", "Fabian", "Franziska", "Hans",
           "Jasmin", "Jürg", "Karin", "Lukas", "Manuela", "Marco", "Monika", "Nicole", "Patrick",
           "Reto", "Ruth", "Sandra", "Stefan", "Thomas", "Ursula", "Urs", "Verena", "Werner", "Yvonne"],
    "fr": ["Alain", "Amélie", "Bernard", "Camille", "Céline", "Christophe", "Daniel", "Delphine",
           "Élodie", "Françoise", "Grégoire", "Isabelle", "Jean-Marc", "Julien", "Laurence", "Luc",
           "Marie-Claude", "Mathieu", "Nathalie", "Olivier", "Pascal", "Philippe", "Sandrine",
           "Sophie", "Sylvie", "Thierry", "Valérie", "Yves"],
    "it": ["Alessandro", "Andrea", "Angela", "Carla", "Chiara", "Claudio", "Daniela", "Elena",
           "Fabio", "Federica", "Francesca", "Giorgio", "Giovanni", "Giulia", "Lorenzo", "Luca",
           "Manuela", "Marco", "Mattia", "Monica", "Nicola", "Paola", "Roberto", "Sara", "Silvia",
           "Simone", "Stefano", "Valentina"],
}

LAST = {
    "de": ["Ammann", "Bachmann", "Baumann", "Brunner", "Bühler", "Egli", "Fischer", "Frei",
           "Gerber", "Graf", "Hofmann", "Huber", "Keller", "Kälin", "Lüthi", "Marti", "Meier",
           "Moser", "Schmid", "Schneider", "Steiner", "Stucki", "Suter", "Vogel", "Wälti",
           "Widmer", "Wyss", "Zbinden", "Zimmermann", "Zürcher"],
    "fr": ["Aubert", "Berset", "Blanc", "Bonvin", "Chappuis", "Chevalley", "Clément", "Cuendet",
           "Dubois", "Ducret", "Favre", "Fontannaz", "Gay", "Girard", "Jaquier", "Juillerat",
           "Mercier", "Monnier", "Morand", "Pasche", "Perrin", "Pittet", "Rey", "Rochat",
           "Roulin", "Savary", "Tissot", "Vuilleumier"],
    "it": ["Bernasconi", "Bianchi", "Bottani", "Brenni", "Bulloni", "Cattaneo", "Ceppi", "Colombo",
           "Cereghetti", "Ferrari", "Fontana", "Galli", "Gianella", "Grassi", "Lepori", "Lurati",
           "Maggi", "Moretti", "Pedrazzini", "Quadri", "Rezzonico", "Rusconi", "Sala", "Solari",
           "Tamò", "Togni", "Vassalli", "Zanetti"],
}

COMPANY_WORDS = {
    "de": ["Bau", "Treuhand", "Immobilien", "Transport", "Garage", "Informatik", "Gastro", "Handel"],
    "fr": ["Construction", "Fiduciaire", "Immobilier", "Transports", "Garage", "Informatique", "Négoce"],
    "it": ["Costruzioni", "Fiduciaria", "Immobiliare", "Trasporti", "Garage", "Informatica", "Commercio"],
}

STREETS = {
    "de": ["Linden", "Bahnhof", "Kirch", "Berg", "Sonnen", "Wiesen", "Garten", "Mühle", "Schul", "Ahorn"],
    "fr": ["des Alpes", "du Lac", "de la Gare", "du Midi", "des Vergers", "du Moulin", "de Lausanne",
           "des Pâquis", "du Château", "des Tilleuls"],
    "it": ["dei Fiori", "Cantonale", "San Gottardo", "del Sole", "ai Ronchi", "della Posta", "Lugano",
           "dei Pini", "Castello", "Vela"],
}

TOWNS = {
    "de": [("8004", "Zürich"), ("3012", "Bern"), ("4057", "Basel"), ("6003", "Luzern"),
           ("9000", "St. Gallen"), ("8400", "Winterthur"), ("5000", "Aarau"), ("7000", "Chur")],
    "fr": [("1004", "Lausanne"), ("1205", "Genève"), ("2000", "Neuchâtel"), ("1700", "Fribourg"),
           ("1950", "Sion"), ("1400", "Yverdon-les-Bains"), ("2800", "Delémont"), ("1820", "Montreux")],
    "it": [("6900", "Lugano"), ("6500", "Bellinzona"), ("6600", "Locarno"), ("6850", "Mendrisio"),
           ("6830", "Chiasso"), ("6710", "Biasca"), ("6780", "Airolo"), ("6612", "Ascona")],
}
