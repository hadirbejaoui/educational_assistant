# Bilan du projet : assistant pédagogique intelligent (version 1.0)

Document de synthèse pour la soutenance. Il décrit l'état **réel** de chaque
fonctionnalité, la preuve qui permet de le vérifier, les résultats mesurés et les
limites connues. L'installation et l'utilisation sont décrites dans `README.md`.

> Les fonctionnalités sont classées par thème. Pour suivre la numérotation exacte du
> cahier des charges (points 1 à 10), reporter chaque ligne sur le point correspondant.

## 1. Fonctionnalités : état et preuves

| Fonctionnalité | État | Preuve (test automatique ou vérification manuelle) |
|---|---|---|
| Inscription, connexion, profil | Fait | `accounts/tests.py` ; parcours d'inscription dans `core/test_end_to_end.py` |
| Isolation des données par étudiant | Fait | Un autre utilisateur reçoit 404 sur cours, fichier, résumés, quiz, résultats et conversations (`core/tests.py`, `core/test_end_to_end.py`) |
| Import PDF/TXT (glisser-déposer, validation navigateur + serveur) | Fait, sans OCR | Validation extension, taille et signature `%PDF-` (`core/tests.py`, `courses/tests.py`) ; import d'un vrai PDF en test de bout en bout |
| Extraction, nettoyage, découpage en passages | Fait | `courses/test_services.py`, `courses/test_rag_pipeline.py`, `courses/test_gaps.py` (sommaire, PDF protégé, encodages Windows) |
| Embeddings et recherche hybride (pgvector + BM25 + RRF) | Fait | `courses/test_embeddings.py` ; évaluation sur cours réels : passage attendu dans les 3 premiers pour 23 questions sur 23 |
| Résumés à 3 niveaux | Fait (fournisseur extractif testé ; Hugging Face non testé) | `summaries/tests.py` ; test de bout en bout |
| Quiz générés par LLM, corrigés, notés sur 20 | Fait | `quizzes/tests.py` ; quiz noté 20/20 en test de bout en bout ; complément automatique si le modèle produit trop peu de questions, avec avertissement |
| Chatbot RAG avec citations et refus | Fait, lent (≈ 1 min par réponse) | `chatbot/tests.py` ; 6 réponses réelles relues (section 3) |
| Tableau de bord et historiques (documents, résumés, quiz, notes, conversations) | Fait | `core/tests.py` (compteurs, moyenne, isolation, pagination) |
| Interface responsive et accessible | Fait | Mesures dans Chrome à 360, 768 et 1280 px (aucun débordement) ; contrastes WCAG AA ; menu au clavier (focus piégé, Échap) |
| Sécurité | Fait | `core/test_security.py` : fichiers privés, limitation de fréquence, en-têtes CSP, CSRF, injection de prompt |
| Déploiement en production | Préparé, non déployé (choix : démonstration sur `runserver`) | `config/settings_production.py`, sauvegarde testée (`scripts/backup.ps1`) |

## 2. Qualité du code

| Mesure | Valeur |
|---|---|
| Tests automatiques | 308, tous au vert |
| Couverture du code (coverage.py) | 93 % |
| `python manage.py check` | aucun problème |
| `check --deploy` (réglages de production, HTTPS) | aucun problème (2 avertissements HSTS désactivés volontairement) |

Les tests n'utilisent ni Internet, ni Ollama, ni le vrai modèle d'embeddings : de faux
modèles déterministes rendent les résultats reproductibles.

## 3. Résultats mesurés

### Recherche (`python manage.py rag_eval_courses`)

Sur 2 cours réels (droit des sociétés, méthodologies de gestion de stock), 23 questions
avec réponse et 8 questions hors cours :

| Mesure | Résultat | Intervalle de confiance à 95 % |
|---|---|---|
| Passage attendu dans les 3 premiers | 100 % (23/23) | — |
| MRR | 0,957 | — |
| Refus à tort | 0 % (0/23) | 0 % à 14 % |
| Acceptation à tort (question hors cours acceptée par le seuil) | 0 % (0/8) | 0 % à 32 % |
| Marge entre la plus faible question avec réponse et la plus forte hors cours | +0,010 de similarité cosinus | — |

Réglages retenus : `RETRIEVAL_LEXICAL_WEIGHT=1`, `RAG_MIN_SCORE=0.83`,
`RAG_SCORE_WINDOW=0.08`. L'outil n'a recommandé aucun changement : aucun autre réglage
ne gagne nettement (au moins 2 questions).

### Fidélité des réponses (`python manage.py rag_faithfulness`)

6 réponses réelles de Qwen3 4B, relues en comparant la réponse aux sources citées :
**5 appuyées, 1 partiellement appuyée, 0 non appuyée**. Avec 6 réponses, l'intervalle
de confiance du taux « appuyée » va de 44 % à 97 % : c'est une indication.

> Avant la soutenance : remplacer cette ligne par le résultat de **votre** relecture
> (`evaluation/fidelite_qwen3-4b-thinking.csv`, colonne « appuyee »).

### Temps de réponse

| Étape | Durée |
|---|---|
| Recherche des passages | ≈ 10 ms |
| Génération d'une réponse par Qwen3 4B (GPU RTX 2050) | 72,9 s en moyenne, 102 s au maximum (6 questions, machine au repos) |
| Refus d'une question hors cours sous le seuil | immédiat (le LLM n'est pas appelé) |

## 4. Limites connues (à présenter honnêtement)

1. **Lenteur du chatbot.** Le modèle installé (`qwen3:4b`) est la variante « thinking » :
   il raisonne longuement avant de répondre. La variante `qwen3:4b-instruct` serait plus
   rapide ; elle n'a pas été retenue pour ce projet.
2. **Évaluation sur un petit échantillon.** 23 questions et 8 hors cours : les
   intervalles de confiance sont larges et la marge du seuil de refus est faible
   (0,010). Une question proche du cours mais sans réponse peut passer le seuil ; le
   refus repose alors sur le LLM (réponse `NON_TROUVE`).
3. **Requêtes bloquantes.** Résumé, quiz et chat occupent la requête pendant le
   traitement ; l'interface affiche un minuteur. Une file de tâches a été écartée : le
   GPU ne traite qu'une génération à la fois, l'attente ne serait pas plus courte.
4. **Injection de prompt.** Les faux délimiteurs dans les cours sont neutralisés, mais
   aucune technique n'empêche à coup sûr un LLM de suivre une consigne cachée.
5. **Pas d'OCR** : un PDF scanné (images) est refusé avec un message clair.
6. **Démonstration sur `runserver`** : serveur de développement, mono-processus. Les
   réglages de production sont prêts mais non déployés.

## 5. Choix techniques à défendre

| Question probable du jury | Réponse courte |
|---|---|
| Pourquoi une recherche hybride ? | Les vecteurs comprennent les reformulations ; BM25 retrouve les termes exacts (sigles, nombres). RRF fusionne des rangs, sans devoir comparer des scores de natures différentes. |
| Pourquoi un seuil avant le LLM ? | Une question hors cours est refusée en 10 ms au lieu d'une minute de génération, et le modèle n'a aucune occasion d'inventer. |
| Pourquoi un LLM local ? | Gratuit, hors ligne, et les cours des étudiants ne sont jamais envoyés à un service tiers. Le fournisseur reste interchangeable (Gemini ou Anthropic par une ligne dans `.env`). |
| Comment savez-vous que ça marche ? | 308 tests automatiques, 93 % de couverture, une évaluation chiffrée sur des cours réels et une relecture des réponses, avec les intervalles de confiance. |
| Comment les données sont-elles protégées ? | Filtre par propriétaire sur chaque requête (404 sinon), fichiers servis par une vue authentifiée, CSRF, CSP stricte, limitation de fréquence. |
| Qu'amélioreriez-vous ? | Le modèle instruct pour la vitesse, plus de questions d'évaluation pour calibrer le seuil, l'OCR pour les PDF scannés, un déploiement waitress + WhiteNoise. |

## 6. Démonstration conseillée (≈ 5 minutes)

1. Connexion, tableau de bord.
2. Import d'un PDF par glisser-déposer ; détail du cours (pages, passages, statut).
3. Résumé court (instantané, fournisseur extractif).
4. Chatbot : une question avec réponse (montrer les sources et les pages), puis une
   question hors cours (refus immédiat). Lancer la question avec réponse **en premier**
   et parler pendant la génération (≈ 1 min).
5. Quiz préparé à l'avance (la génération est longue) : le passer, montrer la note sur
   20 et la correction expliquée.
6. Second compte : montrer qu'aucune donnée du premier n'est visible.
