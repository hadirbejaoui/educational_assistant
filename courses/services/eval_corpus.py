"""Corpus synthétique multi-matières pour évaluer la recherche.

Cinq petits « cours » (droit, informatique, mathématiques, data science, et un
cours en anglais), écrits comme le texte brut que renvoie un PDF : lignes coupées
à ~75 caractères, titres sur leur propre ligne, en-tête et numéro de page répétés.

Chaque question indique des « aiguilles » : des extraits exacts du passage qui
contient la réponse. Un passage (chunk) est pertinent s'il contient une aiguille,
ce qui rend l'évaluation indépendante de la taille des chunks. Une question sans
aiguille n'a pas de réponse dans le cours (elle doit être refusée).

Le corpus sert à mesurer, pas à régler : aucun paramètre du code ne doit être
choisi pour « coller » à ces questions.
"""

import textwrap

from .data import PageData

# Types de questions (pour lire les résultats par catégorie)
EXACT = "termes exacts"
ACRONYM = "sigle"
DOTTED = "sigle avec points"
NO_ACCENT = "sans accents"
SHORT = "terme court"
PARAPHRASE = "reformulation"
CROSS_LINGUAL = "autre langue"
UNANSWERABLE = "hors cours"


DOCUMENTS = [
    {
        "key": "droit",
        "title": "Droit des sociétés",
        "language": "fr",
        "header": "Université de Tunis - Licence 2 - Droit des sociétés",
        "pages": [
            [
                ("h", "Chapitre 1 : La société en nom collectif (SNC)"),
                ("p", "La société en nom collectif (SNC) est une société commerciale dans laquelle "
                      "tous les associés ont la qualité de commerçant. Elle est constituée d'au "
                      "moins deux associés. Aucun capital minimum n'est exigé par la loi. Les parts "
                      "sociales ne peuvent être cédées qu'avec le consentement unanime des associés."),
                ("h", "Responsabilité des associés"),
                ("p", "Dans la SNC, les associés répondent indéfiniment et solidairement des dettes "
                      "sociales. Un créancier peut poursuivre n'importe quel associé pour la totalité "
                      "de la dette, mais seulement après avoir vainement mis en demeure la société "
                      "par acte extrajudiciaire."),
            ],
            [
                ("h", "Chapitre 2 : La société à responsabilité limitée (SARL)"),
                ("p", "La SARL compte de un à cent associés. La responsabilité des associés est "
                      "limitée au montant de leurs apports. Le gérant, obligatoirement une personne "
                      "physique, est nommé par les associés dans les statuts ou par un acte postérieur."),
                ("p", "Les décisions ordinaires sont prises par un ou plusieurs associés représentant "
                      "plus de la moitié des parts sociales. Les décisions qui modifient les statuts "
                      "exigent une majorité renforcée."),
            ],
            [
                ("h", "Chapitre 3 : La société anonyme (SA)"),
                ("p", "La SA est une société de capitaux. Le capital social minimum est de 37 000 euros. "
                      "Elle compte au moins deux actionnaires lorsque ses titres ne sont pas cotés, et "
                      "sept lorsqu'ils sont admis aux négociations sur un marché réglementé."),
                ("p", "La SA est dirigée soit par un conseil d'administration et un directeur général, "
                      "soit par un directoire placé sous le contrôle d'un conseil de surveillance."),
            ],
            [
                ("h", "Chapitre 4 : La dissolution des sociétés"),
                ("p", "La société prend fin à l'expiration du temps pour lequel elle a été constituée, "
                      "par la réalisation de son objet ou par décision des associés. Le décès d'un "
                      "associé de SNC entraîne en principe la dissolution, sauf clause de continuation "
                      "prévue par les statuts."),
                ("p", "La liquidation consiste à réaliser l'actif et à payer le passif. Le boni de "
                      "liquidation est ensuite partagé entre les associés."),
            ],
        ],
        "questions": [
            ("Quelle est la responsabilité des associés dans une SNC ?",
             ["indéfiniment et solidairement"], ACRONYM),
            ("Les associés d'une S.N.C. sont-ils tenus des dettes de la société ?",
             ["indéfiniment et solidairement"], DOTTED),
            ("societe en nom collectif capital minimum exige",
             ["Aucun capital minimum"], NO_ACCENT),
            ("Combien faut-il d'actionnaires au minimum dans une SA ?",
             ["au moins deux actionnaires"], ACRONYM),
            ("Quel est le montant minimum du capital d'une société anonyme ?",
             ["37 000 euros"], EXACT),
            ("Que se passe-t-il quand un associé de la société en nom collectif meurt ?",
             ["clause de continuation"], PARAPHRASE),
            ("Qui peut être gérant d'une SARL ?",
             ["obligatoirement une personne"], ACRONYM),
            ("Un créancier peut-il réclamer directement l'argent à un associé ?",
             ["mis en demeure la société"], PARAPHRASE),
            ("Quelle est la durée maximale d'une garde à vue ?", [], UNANSWERABLE),
            ("Comment calculer la TVA sur une facture ?", [], UNANSWERABLE),
        ],
    },
    {
        "key": "informatique",
        "title": "Développement web et bases de données",
        "language": "fr",
        "header": "Module Informatique - Développement web",
        "pages": [
            [
                ("h", "1. Les API REST"),
                ("p", "Une API REST expose des ressources identifiées par des URL. Les opérations "
                      "utilisent les méthodes HTTP : GET pour lire, POST pour créer, PUT ou PATCH pour "
                      "modifier et DELETE pour supprimer. Une API REST est sans état : chaque requête "
                      "contient toutes les informations nécessaires à son traitement."),
                ("p", "Les codes de statut indiquent le résultat : 200 signifie succès, 201 qu'une "
                      "ressource a été créée, 404 qu'elle est introuvable et 500 une erreur du serveur."),
            ],
            [
                ("h", "2. Le framework Django"),
                ("p", "Django est un framework web écrit en Python qui suit l'architecture MVT "
                      "(modèle, vue, template). Les modèles décrivent les tables de la base de "
                      "données ; l'ORM traduit les requêtes Python en SQL."),
                ("p", "Les migrations, créées avec la commande makemigrations puis appliquées avec "
                      "migrate, font évoluer le schéma de la base sans perdre les données."),
            ],
            [
                ("h", "3. Bases de données SQL"),
                ("p", "Une base de données relationnelle range les données dans des tables. La clé "
                      "primaire identifie chaque ligne de façon unique ; une clé étrangère référence "
                      "la clé primaire d'une autre table."),
                ("p", "La requête SELECT nom FROM etudiant WHERE age > 20 ORDER BY nom; renvoie les "
                      "noms des étudiants de plus de 20 ans, triés par ordre alphabétique. Une "
                      "jointure (JOIN) combine les lignes de plusieurs tables."),
            ],
            [
                ("h", "4. Langages de programmation"),
                ("p", "Le langage C est compilé et donne un accès direct à la mémoire grâce aux "
                      "pointeurs. Le C++ ajoute la programmation orientée objet. Le langage R est "
                      "spécialisé dans l'analyse statistique."),
                ("p", "Un index accélère les recherches dans une table mais ralentit les insertions."),
            ],
        ],
        "questions": [
            ("Quelle méthode HTTP utiliser pour supprimer une ressource ?",
             ["DELETE pour supprimer"], EXACT),
            ("Que signifie le code 404 ?", ["404 qu'elle est introuvable"], SHORT),
            ("Que veut dire qu'une API REST est sans état ?", ["sans état"], ACRONYM),
            ("Comment faire évoluer le schéma de la base avec Django ?",
             ["makemigrations"], EXACT),
            ("Quelle architecture suit Django ?", ["MVT"], EXACT),
            ("Quelle est la différence entre clé primaire et clé étrangère ?",
             ["clé étrangère référence"], EXACT),
            ("À quoi sert le langage R ?", ["langage R est"], SHORT),
            ("Quel langage permet de manipuler directement la mémoire ?",
             ["pointeurs"], PARAPHRASE),
            ("Comment combiner les lignes de deux tables ?", ["jointure"], PARAPHRASE),
            ("Comment configurer un routeur Wi-Fi domestique ?", [], UNANSWERABLE),
            ("Qui a gagné la coupe du monde de football en 2018 ?", [], UNANSWERABLE),
        ],
    },
    {
        "key": "mathematiques",
        "title": "Probabilités",
        "language": "fr",
        "header": "Mathématiques appliquées - Probabilités",
        "pages": [
            [
                ("h", "Chapitre 1 - Probabilités"),
                ("p", "Une expérience aléatoire a plusieurs issues possibles. L'ensemble des issues "
                      "est l'univers, noté Ω. Une probabilité P associe à chaque événement A un nombre "
                      "P(A) compris entre 0 et 1, avec P(Ω) = 1."),
                ("p", "Deux événements A et B sont indépendants si P(A ∩ B) = P(A) × P(B). La "
                      "probabilité conditionnelle de A sachant B vaut P(A|B) = P(A ∩ B) / P(B)."),
            ],
            [
                ("h", "Chapitre 2 - Variable aléatoire"),
                ("p", "Une variable aléatoire X associe un nombre réel à chaque issue. Son espérance "
                      "E(X) est la moyenne des valeurs pondérée par leurs probabilités. La variance "
                      "V(X) = E(X²) − E(X)² mesure la dispersion ; l'écart-type est sa racine carrée."),
            ],
            [
                ("h", "Chapitre 3 - Loi binomiale"),
                ("p", "On répète n fois, de façon indépendante, une épreuve de Bernoulli de paramètre "
                      "p. Le nombre X de succès suit la loi binomiale B(n, p) : P(X = k) = C(n, k) "
                      "p^k (1 − p)^(n − k). Son espérance vaut E(X) = np et sa variance V(X) = np(1 − p)."),
            ],
            [
                ("h", "Chapitre 4 - Loi normale"),
                ("p", "La loi normale N(μ, σ²) a une densité en forme de cloche, symétrique autour de "
                      "la moyenne μ. Environ 95 % des valeurs se situent entre μ − 2σ et μ + 2σ."),
                ("p", "Le théorème central limite justifie l'approximation de nombreuses lois, comme "
                      "la loi binomiale pour n grand, par la loi normale."),
            ],
        ],
        "questions": [
            ("Quelle est l'espérance d'une loi binomiale ?", ["E(X) = np"], EXACT),
            ("formule de la probabilite conditionnelle", ["P(A|B)"], NO_ACCENT),
            ("Quand dit-on que deux événements sont indépendants ?",
             ["P(A ∩ B) = P(A) × P(B)"], EXACT),
            ("Comment calcule-t-on la variance d'une variable aléatoire ?",
             ["E(X²) − E(X)²"], EXACT),
            ("Que représente le paramètre p dans B(n, p) ?",
             ["Bernoulli de paramètre"], SHORT),
            ("Quelle proportion des valeurs d'une loi normale se trouve à moins de deux "
             "écarts-types de la moyenne ?", ["95 %"], PARAPHRASE),
            ("Pourquoi peut-on remplacer une loi binomiale par une loi normale quand n est grand ?",
             ["théorème central limite"], PARAPHRASE),
            ("Comment résoudre une équation différentielle du second ordre ?", [], UNANSWERABLE),
            ("Quelle est la capitale de l'Australie ?", [], UNANSWERABLE),
        ],
    },
    {
        "key": "data_science",
        "title": "Introduction à l'apprentissage automatique",
        "language": "fr",
        "header": "Data Science - Master 1",
        "pages": [
            [
                ("h", "Apprentissage supervisé"),
                ("p", "En apprentissage supervisé, le modèle apprend à partir d'exemples étiquetés : "
                      "chaque observation possède des variables explicatives et une variable cible. "
                      "On distingue la régression, où la cible est continue, et la classification, où "
                      "la cible est une catégorie."),
                ("p", "Le jeu de données est divisé en un ensemble d'entraînement et un ensemble de "
                      "test afin d'estimer l'erreur de généralisation."),
            ],
            [
                ("h", "Régression logistique"),
                ("p", "La régression logistique est un modèle de classification binaire. Elle estime "
                      "la probabilité d'appartenance à la classe positive grâce à la fonction sigmoïde "
                      "σ(z) = 1 / (1 + e^(−z)). Les coefficients sont estimés en maximisant la "
                      "vraisemblance, ce qui revient à minimiser l'entropie croisée."),
                ("p", "Un seuil, souvent 0,5, transforme la probabilité en classe prédite."),
            ],
            [
                ("h", "Évaluation d'un classifieur"),
                ("p", "La matrice de confusion croise classes réelles et classes prédites. La "
                      "précision est la part de vrais positifs parmi les prédictions positives ; le "
                      "rappel est la part de vrais positifs parmi les positifs réels. Le score F1 est "
                      "la moyenne harmonique de la précision et du rappel."),
                ("p", "La courbe ROC et l'AUC résument les performances pour tous les seuils."),
            ],
            [
                ("h", "Surapprentissage et validation"),
                ("p", "Un modèle trop complexe apprend le bruit des données d'entraînement : c'est le "
                      "surapprentissage (overfitting). La régularisation L1 ou L2 pénalise les grands "
                      "coefficients."),
                ("p", "La validation croisée à k plis (k-fold) estime la performance de façon plus "
                      "fiable. L'algorithme k-NN classe une observation selon la classe majoritaire "
                      "de ses k plus proches voisins."),
            ],
        ],
        "questions": [
            ("Quelle fonction utilise la régression logistique ?", ["fonction sigmoïde"], EXACT),
            ("Comment sont estimés les coefficients de la regression logistique ?",
             ["maximisant la vraisemblance"], NO_ACCENT),
            ("Quelle est la différence entre régression et classification ?",
             ["la cible est continue"], EXACT),
            ("Qu'est-ce que le score F1 ?", ["moyenne harmonique"], SHORT),
            ("Comment empêcher un modèle d'apprendre le bruit des données ?",
             ["régularisation L1 ou L2"], PARAPHRASE),
            ("Comment fonctionne l'algorithme kNN ?", ["k-NN classe"], ACRONYM),
            ("Pourquoi séparer les données en entraînement et test ?",
             ["erreur de généralisation"], PARAPHRASE),
            ("Comment fonctionne un réseau de neurones convolutif ?", [], UNANSWERABLE),
            ("Quel est le rôle de la mitochondrie dans la cellule ?", [], UNANSWERABLE),
        ],
    },
    {
        "key": "english",
        "title": "Computer science fundamentals",
        "language": "en",
        "header": "CS 101 - Lecture notes",
        "pages": [
            [
                ("h", "Supervised learning"),
                ("p", "Supervised learning trains a model on labelled examples. Logistic regression "
                      "is a linear classifier that outputs a probability through the sigmoid function. "
                      "A decision threshold, usually 0.5, turns the probability into a class label."),
            ],
            [
                ("h", "Relational databases"),
                ("p", "A relational database stores data in tables. SQL queries use SELECT to read "
                      "rows, INSERT to add rows and UPDATE to modify them. A primary key uniquely "
                      "identifies each row."),
                ("p", "Normalisation reduces redundancy by splitting data into related tables."),
            ],
            [
                ("h", "Web APIs"),
                ("p", "A REST API exposes resources through URLs and standard HTTP verbs. Responses "
                      "are usually encoded in JSON. Authentication is often handled with tokens sent "
                      "in the Authorization header. Rate limiting protects the server from too many "
                      "requests."),
            ],
            [
                ("h", "Discrete probability"),
                ("p", "A random variable maps outcomes to numbers. The binomial distribution counts "
                      "the successes in n independent trials with success probability p; its mean is "
                      "np. The Poisson distribution models the number of rare events in a fixed "
                      "interval; its mean and variance are both equal to λ."),
            ],
        ],
        "questions": [
            ("What function does logistic regression use to output a probability?",
             ["sigmoid function"], EXACT),
            ("How do I add rows to a SQL table?", ["INSERT to add rows"], ACRONYM),
            ("What is the mean of a binomial distribution?", ["its mean is"], EXACT),
            ("Which distribution should be used to count rare events?",
             ["Poisson distribution"], PARAPHRASE),
            ("Comment une API REST gère-t-elle l'authentification ?",
             ["Authorization header"], CROSS_LINGUAL),
            ("Why should a database be normalised?", ["reduces redundancy"], EXACT),
            ("Who wrote the play Hamlet?", [], UNANSWERABLE),
            ("How do vaccines train the immune system?", [], UNANSWERABLE),
        ],
    },
]


def raw_pages(document):
    """Texte brut des pages, tel que l'extraction d'un PDF le donnerait."""
    total = len(document["pages"])
    pages = []
    for number, blocks in enumerate(document["pages"], start=1):
        lines = [document["header"]]
        for kind, text in blocks:
            lines.extend([text] if kind == "h" else textwrap.wrap(text, 75))
        lines.append(f"Page {number} / {total}")
        pages.append(PageData(number, "\n".join(lines), ""))
    return pages


def questions(document):
    """Questions du document sous forme de dictionnaires."""
    return [
        {"question": text, "needles": needles, "kind": kind}
        for text, needles, kind in document["questions"]
    ]
