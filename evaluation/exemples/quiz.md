# Exemples de quiz (avec correction)

## Quiz - Chapitre 9_3c409860 (1)

*Cours : Chapitre 9_3c409860 (1) · difficulté : moyen · modèle : ollama qwen3:4b*

**1. Quel est le rôle principal du Model Binding dans ASP.NET Core ?**

- A. Permet de récupérer automatiquement les données HTTP et de les associer aux propriétés d'un objet C# ✔ (bonne réponse)
- B. Permet de générer des vues HTML pour les formulaires
- C. Crée des routes pour les requêtes HTTP
- D. Gère la validation des champs obligatoires dans les formulaires

*Explication : Selon le cours, le Model Binding est un mécanisme qui permet de récupérer automatiquement les données envoyées par une requête HTTP et de les associer aux propriétés d'un objet C#.*

**2. Quel est l'effet de l'attribut asp-action dans un formulaire HTML selon le cours ?**

- A. Il spécifie le nom de la méthode d'action du contrôleur ✔ (bonne réponse)
- B. Il définit le type de méthode HTTP utilisée (ex: POST)
- C. Il indique le chemin relatif pour accéder à la page
- D. Il permet de spécifier le nom du champ de formulaire

*Explication : Dans l'exemple fourni, le formulaire utilise <form asp-action="Create" method="post">, ce qui indique que l'action cible est la méthode Create du contrôleur.*

**3. Quel est le comportement de Model Binding pour les champs obligatoires dans le cours ?**

- A. Il ne vérifie pas les contraintes et les erreurs sont gérées manuellement ✔ (bonne réponse)
- B. Il lance une exception si les champs obligatoires sont absents
- C. Il vérifie automatiquement les contraintes de longueur des champs
- D. Il ne traite pas les champs obligatoires

*Explication : Le cours indique que le Model Binding établit automatiquement la correspondance entre les noms des champs HTML et les propriétés du modèle, mais il ne mentionne pas de vérification automatique des contraintes. Les messages d'erreur sont spécifiques aux contraintes (comme la longueur) et sont gérés séparément.*

**4. Quel est le type de méthode utilisé dans l'exemple de formulaire HTML fourni ?**

- A. POST ✔ (bonne réponse)
- B. PUT
- C. GET
- D. DELETE

*Explication : Dans l'exemple, le formulaire utilise method="post", ce qui indique que la méthode HTTP utilisée est POST.*

**5. Quel est le champ qui doit contenir une valeur entre 0 et 1000 selon le cours ?**

- A. Movie
- B. Name
- C. Stock ✔ (bonne réponse)
- D. Movie1

*Explication : Le cours précise que le champ Stock doit contenir une valeur comprise entre 0 et 1000, avec un message d'erreur en cas de non-respect.*

**6. Quel est le rôle de l'interface IMovieService dans l'application ASP.NET Core ?**

- A. Permet de définir les méthodes que le service doit implémenter ✔ (bonne réponse)
- B. Permet de remplacer le service sans modifier le contrôleur
- C. Permet de créer des dépendances directes entre le contrôleur et le service
- D. Toutes les réponses ci-dessus

*Explication : Le cours indique que l'interface IMovieService définit un contrat contenant les méthodes que le service doit obligatoirement implémenter, ce qui permet de réduire le couplage et d'éviter de modifier le contrôleur lorsqu'on remplace le service.*

**7. Quel est l'effet de l'interface IMovieService sur le couplage entre le contrôleur et le service ?**

- A. Rend le couplage impossible
- B. Augmente le couplage
- C. Ne change pas le couplage
- D. Réduit le couplage ✔ (bonne réponse)

*Explication : Le cours indique que cette approche permet de réduire le couplage entre les composants, ce qui est un avantage pour la maintenance et l'évolutivité.*

**8. Quel est le comportement de l'application lorsque le champ Stock n'est pas entre 0 et 1000 ?**

- A. Un message d'erreur s'affiche ✔ (bonne réponse)
- B. Aucune action
- C. Le champ est ignoré
- D. L'application se ferme

*Explication : Le cours précise : "Le champ Stock doit contenir une valeur comprise entre 0 et 1000. Dans le cas contraire, un message d'erreur s'affiche."*

**9. Quel est le comportement de l'application lorsque le champ Stock n'est pas entre 0 et 1000 selon le cours ?**

- A. L'application ne fonctionne pas
- B. L'application ajoute le film en base de données
- C. L'application affiche une erreur de validation ✔ (bonne réponse)
- D. L'application ignore la validation du champ Stock

*Explication : Selon le cours, le champ Stock est vérifié pour être entre 0 et 1000. Si les données ne respectent pas les règles de validation définies dans le modèle, ModelState.IsValid permet de vérifier si les données sont valides. Si le champ Stock n'est pas entre 0 et 1000, les données ne seront pas valides et l'application affichera une erreur de validation.*

**10. Quel est l'objectif principal de l'attribut asp-validation-for dans le formulaire HTML selon le cours ?**

- A. Afficher les messages d'erreur associés aux propriétés du modèle Movie ✔ (bonne réponse)
- B. Valider les champs obligatoires avant l'envoi au contrôleur
- C. Permettre la gestion des erreurs de validation côté serveur
- D. Générer des scripts JavaScript pour la validation côté client

*Explication : Selon le cours, l'attribut asp-validation-for est utilisé pour afficher les messages d'erreur associés aux propriétés du modèle Movie, comme indiqué sur les pages 6-7.*

**11. Quel est le rôle de la section Scripts avec _ValidationScriptsPartial dans l'application ASP.NET Core ?**

- A. Afficher les messages d'erreur associés aux propriétés du modèle Movie
- B. Générer des scripts JavaScript pour la validation côté client ✔ (bonne réponse)
- C. Valider les champs obligatoires avant l'envoi au contrôleur
- D. Permettre la gestion des erreurs de validation côté serveur

*Explication : Le cours indique que _ValidationScriptsPartial est une vue partielle fournie par ASP.NET Core qui contient les scripts JavaScript nécessaires à la validation côté client, permettant de vérifier les données saisies dans le navigateur avant leur envoi au contrôleur.*

**12. Quel est l'effet de l'attribut asp-for="Stock" dans le formulaire HTML selon le cours ?**

- A. Affiche les messages d'erreur pour le champ Stock
- B. Valide le champ Stock pour être entre 0 et 1000
- C. Associe le champ HTML à la propriété Stock du modèle Movie ✔ (bonne réponse)
- D. Permet de définir la valeur initiale du champ Stock

*Explication : Le cours précise que l'attribut asp-for="Stock" associe le champ HTML à la propriété Stock du modèle Movie, comme indiqué sur les pages 6-6.*

**13. Quel est le comportement de l'application lorsqu'un champ obligatoire n'est pas rempli dans le formulaire ?**

- A. L'application envoie les données au contrôleur sans vérification
- B. L'application ne génère aucun message d'erreur
- C. L'application bloque l'envoi du formulaire
- D. L'application affiche les messages d'erreur associés aux champs obligatoires ✔ (bonne réponse)

*Explication : Selon le cours, l'application utilise asp-validation-for pour afficher les messages d'erreur associés aux propriétés du modèle Movie, ce qui inclut les champs obligatoires non remplis.*

**14. Quel est le type de validation côté client réalisé par les scripts JavaScript dans l'application ASP.NET Core selon le cours ?**

- A. Vérification des données saisies dans le navigateur avant leur envoi au contrôleur
- B. Validation des champs obligatoires avant l'envoi au contrôleur ✔ (bonne réponse)
- C. Génération de messages d'erreur pour les champs non valides
- D. Toutes les réponses ci-dessus

*Explication : Le cours indique que les scripts JavaScript permettent de vérifier les données saisies directement dans le navigateur avant leur envoi au contrôleur, ce qui correspond à la description de la validation côté client.*

**15. Quel est le rôle principal de l'interface IMovieService dans l'application ASP.NET Core ?**

- A. Permettre l'inscription du service MovieService dans le conteneur d'injection de dépendances
- B. Permettre au contrôleur d'accéder aux fonctionnalités du service sans dépendre de son implémentation ✔ (bonne réponse)
- C. Faciliter la liaison entre la vue et les éléments de l'application
- D. Gérer les validations côté client avec des scripts JavaScript

*Explication : Selon le cours, l'interface IMovieService permet au contrôleur d'accéder aux fonctionnalités du service MovieService sans dépendre directement de son implémentation (page 5).*

**16. Quel est le rôle principal du Model Binding dans ASP.NET Core selon le cours ?**

- A. Permet de récupérer automatiquement les données envoyées par une requête HTTP et de les associer aux propriétés d'un objet C# ✔ (bonne réponse)
- B. Crée des formulaires HTML pour l'ajout de films
- C. Effectue la validation côté serveur des champs obligatoires
- D. Gère les erreurs de validation des champs obligatoires

*Explication : Selon le cours, le Model Binding est un mécanisme qui permet de récupérer automatiquement les données envoyées par une requête HTTP (formulaire, URL, etc.) et de les associer aux propriétés d'un objet C#.*

## Quiz - Big Data

*Cours : Big Data · difficulté : moyen · modèle : ollama qwen3:4b*

**1. Quelle est la troisième grande révolution technique de l'histoire moderne selon Stéphane Vial, mentionné dans le cours ?**

- A. Les objets connectés
- B. Les Big Data ✔ (bonne réponse)
- C. La révolution mécanique de l'ère industrielle
- D. L'imprimerie

*Explication : Selon le cours, Stéphane Vial identifie trois grandes révolutions techniques : 1) l'imprimerie (Johannes Gutenberg), 2) les objets connectés (IoT), 3) les Big Data. La troisième révolution est donc les Big Data.*

**2. Quel est le rôle des objets connectés dans la révolution numérique selon le cours ?**

- A. Ils permettent de stocker les données en temps réel
- B. Ils servent de pétrole pour la révolution numérique
- C. Ils sont uniquement utilisés pour la communication en ligne
- D. Ils sont des outils au service des utilisateurs et collecteurs de données ✔ (bonne réponse)

*Explication : Le cours indique que "Les objets connectés occupent une place centrale: outils au service des utilisateurs, collecteurs de données". Ils ne sont pas seulement des outils mais aussi des collecteurs de données.*

**3. Quelle est la définition la plus précise des Big Data selon le cours ?**

- A. Des données qui sont stockées dans des bases de données traditionnelles
- B. Des données volumineuses qui ne peuvent être hébergées sur une seule machine ✔ (bonne réponse)
- C. Des données qui sont analysées sans stockage
- D. Des données qui sont utilisées pour la communication en temps réel

*Explication : Le cours définit les Big Data comme "les jeux de données extrêmement volumineux qui ne peuvent pas être hébergés sur une seule machine". C'est la définition la plus précise selon le cours.*

**4. Quelle est la différence principale entre les données brutes et les données analysées selon le cours ?**

- A. Les données brutes sont stockées en temps réel, les données analysées en retard
- B. Les données brutes sont utilisées pour la communication, les données analysées pour la prise de décision
- C. Les données brutes ne sont pas pertinentes par elles-mêmes, mais deviennent créatrices de valeur une fois analysées ✔ (bonne réponse)
- D. Les données brutes sont des données structurées, les données analysées semi-structurées

*Explication : Le cours précise que "De même que le pétrole brut ne peut être utilisé comme combustible automobile, les données brutes ne sont pas pertinentes par elles-mêmes. Elles deviendraient en revanche créatrices de valeur une fois analysées."*

**5. Quel est l'objectif principal des métadonnées dans le contexte des Big Data selon le cours ?**

- A. Elles sont utilisées pour la sécurité des données
- B. Elles servent à stocker les données en temps réel
- C. Elles fournissent des informations contextuelles pour mieux comprendre les données ✔ (bonne réponse)
- D. Elles permettent de définir la structure des données

*Explication : Le cours mentionne que les métadonnées sont des informations supplémentaires qui permettent de comprendre le contexte des données. Par exemple, l'exemple donné est "45° 50’ 30’’ N 3° 15’ 40’’ E", qui fournit des informations géographiques contextuelles.*

## Quiz - liste de projets IoT_DSSD

*Cours : liste de projets IoT_DSSD · difficulté : moyen · modèle : ollama qwen3:4b*

**1. Quel est l'objectif principal de la Smart City en termes d'optimisation de la consommation énergétique selon le cours ?**

- A. Réduction des coûts énergétiques via des capteurs de surveillance
- B. Amélioration de l'efficacité énergétique grâce à l'analyse de données ✔ (bonne réponse)
- C. Optimisation des réseaux électriques via des capteurs industriels
- D. Génération de données pour des algorithmes de prévision

*Explication : Selon le cours, la Smart City vise l'optimisation de la consommation énergétique avec des capteurs, des algorithmes et des données simulées. L'objectif principal est l'amélioration de l'efficacité énergétique via l'analyse de données, ce qui correspond à la réponse 1.*

**2. Quel critère d'évaluation a une ponderation de 30% dans le cadre des projets IoT ?**

- A. Analyse
- B. Réalisation
- C. Innovation
- D. Technique ✔ (bonne réponse)

*Explication : Le cours indique que le critère 'technique' a une ponderation de 30%, avec des éléments comme la complexité algorithmique et l'architecture des données.*

**3. Quel est l'élément clé de la critère 'analyse' dans l'évaluation des projets IoT ?**

- A. Validation des résultats ✔ (bonne réponse)
- B. Scalabilité
- C. Complexité algorithmique
- D. Qualité du code

*Explication : Dans le critère 'analyse' (ponderation 25%), l'élément clé est la validation des résultats, ce qui permet d'évaluer la qualité de l'analyse effectuée.*

**4. Quel projet IoT utilise des capteurs wearables pour surveiller les patients ?**

- A. Véhicules Autonomes & Analyse de Trafic
- B. Réseau de Capteurs Environnementaux
- C. Santé Connectée - Surveillance de Patients ✔ (bonne réponse)
- D. Smart City - Optimisation de la Consommation Énergétique

*Explication : Le cours mentionne que le projet 'Santé Connectée - Surveillance de Patients' utilise des capteurs wearables (comme les bracelets) pour surveiller les patients.*

**5. Quel est l'objectif principal de l'Optimisation de Chaîne Logistique dans le contexte des projets IoT ?**

- A. Génération de données pour des algorithmes de prévision
- B. Optimisation des itinéraires de transport
- C. Amélioration de la traçabilité des produits
- D. Réduction des coûts logistiques via des capteurs de suivi ✔ (bonne réponse)

*Explication : Selon le cours, l'Optimisation de Chaîne Logistique vise à améliorer la chaîne logistique avec des capteurs utilisés, des objectifs et des KPI. L'objectif principal est la réduction des coûts logistiques via des capteurs de suivi, ce qui correspond à la réponse 0.*

## Quiz - Methodologies_Gestion_Stock

*Cours : Methodologies_Gestion_Stock · difficulté : moyen · modèle : ollama qwen3:4b*

**1. Quelle est la principale caractéristique de la méthodologie Scrum appliquée dans ce système de gestion de stock ?**

- A. Privilégie les processus unifiés et les phases longues pour la livraison
- B. Concentré sur la gestion des rôles sans livraison incrémentale
- C. Organisé en Sprints de durée fixe (2 semaines) avec livraison continue de valeur ✔ (bonne réponse)
- D. Utilise des processus itératifs sans attention aux changements

*Explication : Selon le cours, Scrum est décrit comme "un cadre agile itératif organisé en Sprints de durée fixe (2 semaines). Il privilégie la livraison continue de valeur, la collaboration et l'adaptation rapide aux changements". La réponse correcte correspond à la description du cours.*

**2. Quel est l'objectif principal du cas d'utilisation "Établir un bon d'entrée" dans ce système de gestion de stock ?**

- A. Gérer les produits en stock et leurs informations
- B. Établir des demandes de fourniture pour les produits manquants
- C. Permettre la consultation du stock pour les différents acteurs
- D. Enregistrer l'arrivée de marchandises et mettre à jour les quantités en stock ✔ (bonne réponse)

*Explication : Le cours indique que le cas d'utilisation "Établir un bon d'entrée" a pour description : "En tant que chef magasin, je veux établir un bon d'entrée afin d'enregistrer l'arrivée de marchandises et mettre à jour les quantités en stock". L'objectif principal est donc de gérer l'arrivée de marchandises et les mises à jour des stocks.*

**3. Quel est le critère d'acceptation clé pour le cas d'utilisation "S'authentifier" dans le cadre de Scrum ?**

- A. La session expire après 30 minutes d'inactivité
- B. Un message d'erreur clair apparaît si les identifiants sont incorrects ✔ (bonne réponse)
- C. Le formulaire de connexion s'affiche dès l'accès à l'application
- D. L'utilisateur est redirigé vers son interface selon son profil

*Explication : Selon le cours, les critères d'acceptation pour "S'authentifier" incluent : "Un message d'erreur clair apparaît si les identifiants sont incorrects". C'est le critère d'acceptation clé mentionné dans la description technique du cas d'utilisation.*

**4. Dans quel sprint le cas d'utilisation "Gérer un produit" est-il livré selon le planning Scrum ?**

- A. Sprint 2 ✔ (bonne réponse)
- B. Sprint 4
- C. Sprint 3
- D. Sprint 1

*Explication : Le cours indique que dans le planning complet des Sprints, "Sprint 2 2 semaines UC2 – Gérer un produit". C'est donc le sprint 2 qui livre ce cas d'utilisation.*

**5. Quelle est la différence principale entre les méthodologies RUP et AUP selon le cours ?**

- A. AUP est une adaptation de RUP pour un contexte agile ✔ (bonne réponse)
- B. RUP est un cadre itératif et AUP est un cadre unifié
- C. RUP utilise des phases unifiées tandis que AUP est agile
- D. RUP est plus complexe que AUP

*Explication : Le cours mentionne que "5.1 Adaptation RUP → AUP" et décrit AUP comme "Agile Unifié", ce qui indique que AUP est une adaptation de RUP pour un contexte agile. La différence principale est donc que AUP est une adaptation de RUP pour un contexte agile.*

**6. Quel est le critère d'acceptation clé pour le cas d'utilisation 'S'authentifier' dans le cadre de l'AUP selon le cours ?**

- A. Un scénario alternatif documenté avec un cas de test négatif
- B. Un plan de test formel rédigé avant le développement
- C. Une condition de validation dans le code avec un test automatisé intégré au pipeline CI/CD ✔ (bonne réponse)
- D. Une description textuelle du cas d'utilisation et un diagramme de séquence (Fig. 2.12)

*Explication : Selon le cours, dans l'AUP, l'alternative [A1] (identifiants erronés) est gérée directement dans le code via une condition de validation, couverte par un test automatisé intégré au pipeline CI/CD. Aucune documentation papier supplémentaire n'est produite. Cela correspond à la description du critère d'acceptation clé pour 'S'authentifier' dans l'AUP.*

**7. Dans quel itérations de l'AUP le cas d'utilisation 'Gérer un produit' est-il livré selon le planning détaillé dans le cours ?**

- A. Itération 1
- B. Itération 4
- C. Itération 3 ✔ (bonne réponse)
- D. Itération 2

*Explication : Le cours indique que 'Gérer un produit (CRUD)' est livré lors de l'itération 3 de la phase Construction dans le plan des 6 itérations AUP. Cela correspond à l'itération 3 du planning détaillé.*

**8. Quel est l'objectif principal du cas d'utilisation 'Établir un bon d'entrée' dans le cadre de l'AUP selon le cours ?**

- A. Gérer les interactions avec le stock, les fournisseurs et la fiche de mouvement de stock
- B. Générer un bon PDF avec validation des champs [A1]
- C. Lier les fondations (authentification et gestion produits) pour une utilisation stable ✔ (bonne réponse)
- D. S'assurer que les champs obligatoires sont correctement remplis

*Explication : Selon le cours, le bon d'entrée est le cas métier central du système. En AUP, il est livré lors de l'itération 4, après que les fondations (authentification et gestion produits) soient stables. Cela indique que son objectif principal est de lier les fondations pour une utilisation stable.*

## Quiz - certifica data visualization

*Cours : certifica data visualization · difficulté : facile · modèle : ollama qwen3:4b*

**1. Quel est le titre du cours mentionné dans le texte ?**

- A. Introduction to Data Visualization ✔ (bonne réponse)
- B. Bejaoui Hadir
- C. Data Visualization 17th November 2024
- D. Certificate code : 7569563

*Explication : Le titre du cours est directement énoncé dans le texte : 'Bejaoui Hadir Introduction to Data Visualization 17th November 2024 Certificate code : 7569563'.*

**2. Quel est la date mentionnée dans le cours ?**

- A. 17th November 2024 ✔ (bonne réponse)
- B. Certificate code : 7569563
- C. Bejaoui Hadir
- D. Introduction to Data Visualization

*Explication : La date est explicitement indiquée dans le texte : 'Bejaoui Hadir Introduction to Data Visualization 17th November 2024 Certificate code : 7569563'.*

**3. Quel est le code de certificate mentionné dans le cours ?**

- A. 17th November 2024
- B. Bejaoui Hadir
- C. Introduction to Data Visualization
- D. 7569563 ✔ (bonne réponse)

*Explication : Le code de certificate est directement énoncé dans le texte : 'Bejaoui Hadir Introduction to Data Visualization 17th November 2024 Certificate code : 7569563'.*

**4. Qui est l'auteur du cours ?**

- A. 17th November 2024
- B. Introduction to Data Visualization
- C. Certificate code : 7569563
- D. Bejaoui Hadir ✔ (bonne réponse)

*Explication : L'auteur du cours est spécifié dans le texte : 'Bejaoui Hadir Introduction to Data Visualization 17th November 2024 Certificate code : 7569563'.*

**5. Quel est le format du cours mentionné dans le texte ?**

- A. Cours en ligne
- B. Texte
- C. Document PDF
- D. Document texte ✔ (bonne réponse)

*Explication : Le cours est décrit comme un document texte dans le contexte donné, car le texte ne mentionne pas de format spécifique mais indique un cours avec des informations structurées. Cependant, le texte ne spécifie pas de format explicite, donc la réponse la plus proche est 'Document texte'.*

## Quiz - Resume_Droit_des_Societes (1)

*Cours : Resume_Droit_des_Societes (1) · difficulté : moyen · modèle : ollama qwen3:4b*

**1. Quelle est la différence principale entre l'entreprise et la société selon le cours ?**

- A. Une entreprise est une notion économique et sociale, tandis qu'une société est une notion juridique ✔ (bonne réponse)
- B. Une entreprise est une personne morale, tandis qu'une société est une activité économique
- C. Une entreprise est une activité économique, tandis qu'une société est une personne morale
- D. Une entreprise est une structure juridique, tandis qu'une société est une activité économique

*Explication : Selon le cours, l'entreprise est définie comme une notion économique et sociale, tandis que la société est une notion juridique. C'est la distinction clé énoncée dans le chapitre 1.*

**2. Quel est le critère d'apport en industrie pour une société en participation ?**

- A. Les apports en industrie ne font pas partie du capital social mais donnent droit à des parts sociales et à une part des bénéfices ✔ (bonne réponse)
- B. Les apports en industrie sont autorisés uniquement pour les commandités
- C. Les apports en industrie sont obligatoires pour les sociétés en participation
- D. Les apports en industrie ne sont pas autorisés pour les sociétés en participation

*Explication : Le cours indique que pour une société en participation, l'apport en industrie ne fait pas partie du capital social, mais donne droit à des parts sociales et à une part des bénéfices et de l'actif selon les statuts.*

**3. Quel est le nombre minimum d'associés pour une SCS ?**

- A. 4 ✔ (bonne réponse)
- B. 5
- C. 2
- D. 3

*Explication : Selon le cours, une SCS (Société en Commandite Simple) comprend deux catégories d'associés (minimum 4 : 2 de chaque groupe, sans maximum).*

**4. Quelle est la responsabilité des associés dans une SNC ?**

- A. Responsabilité illimitée, personnelle et solidaire ✔ (bonne réponse)
- B. Responsabilité illimitée, personnelle mais non solidaire
- C. Responsabilité limitée à la part sociale
- D. Responsabilité limitée au montant des apports

*Explication : Le cours précise que dans une SNC, les associés ont une responsabilité personnelle, solidaire et indéfinie pour les dettes de la société.*

**5. Quel est le délai maximum pour transformer une SARL en société par actions si elle dépasse 50 associés ?**

- A. 1 mois
- B. 3 mois
- C. 1 an ✔ (bonne réponse)
- D. 6 mois

*Explication : Le cours indique que si une SARL dépasse 50 associés, elle doit se transformer en société par actions (ex. SA) dans un délai d'1 an, ou revenir à 50 associés maximum, sinon la dissolution judiciaire peut être demandée.*
