# Bilan du projet 2 : assistant pédagogique (résumés, quiz, chatbot)

Document de synthèse pour la soutenance, organisé selon le cahier des charges du
projet 2. Pour chaque exigence : état **réel**, preuve vérifiable, et ce qui manque.
L'installation et l'utilisation sont décrites dans `README.md`.

Légende : ✅ fait et vérifié · ⚠️ fait partiellement · ❌ à faire

## 1. Contexte général (section 1)

| Exigence | État | Preuve |
|---|---|---|
| Un LLM | ✅ | Qwen3 4B local via Ollama (`llm/`), interchangeable avec Gemini et Anthropic par `.env` ; tests `llm/tests.py` |
| Un chatbot interactif | ✅ | `chatbot/` : conversation avec historique, réponses citées, refus hors cours |
| Un pipeline RAG | ✅ | Extraction → nettoyage → découpage → embeddings e5 → pgvector + BM25 → fusion RRF → seuil → LLM (`courses/services/`, `chatbot/services/rag.py`) |
| Un corpus adapté au thème | ⚠️ | Cours réels de l'étudiante (droit des sociétés, gestion de stock, Big Data…) + corpus synthétique multi-matières (`courses/services/eval_corpus.py`). Aucun document des sources recommandées (MIT OCW, OpenStax, arXiv, OER Commons) n'est encore utilisé. |

## 2. Livrables obligatoires (section 3.1)

| Livrable | État | Remarque |
|---|---|---|
| Rapport PDF détaillé | ❌ | À rédiger : problème, pipeline, choix techniques, architecture avec schémas, résultats, exemples de conversations, limites, lien GitHub. La matière existe (README, ce bilan, sorties des commandes d'évaluation). |
| Code source sur GitHub, organisé et commenté | ⚠️ | Code poussé, 11 phases commitées, docstrings en français. **Le dépôt s'appelle `educational_assistant.` (point final)** : à renommer avant de donner le lien. |
| README : prérequis, installation, exécution | ✅ | `README.md` : Windows pas à pas, pgvector, Ollama, variables, commandes, tests |
| Script ou notebook de démonstration | ⚠️ | Facultatif. Le parcours de démonstration est décrit (section 7 ci-dessous) mais il n'existe pas de script dédié. |

## 3. Fonctionnalités attendues (section 6.3)

| Fonctionnalité | État | Preuve |
|---|---|---|
| Téléversement PDF et texte | ✅ | Glisser-déposer, validation navigateur + serveur (extension, taille, signature `%PDF-`) ; test de bout en bout avec un vrai PDF |
| Résumé court, moyen, détaillé | ✅ | `summaries/` : trois niveaux, résumé hiérarchique par sections (map → reduce) ; tests `summaries/tests.py` |
| QCM avec réponses attendues | ✅ | 4 choix, une seule bonne réponse garantie par la base, explication de la réponse ; correction notée sur 20 |
| Niveau de difficulté adaptable | ✅ | Facile, moyen, difficile (consignes différentes dans le prompt) |
| Chatbot questions-réponses avec citations de passages | ✅ | Passages numérotés [1], [2], pages et extraits affichés ; citations inventées retirées |

## 4. Architecture technique (section 6.4)

| Exigence | État | Preuve ou remarque |
|---|---|---|
| Extraction de texte | ✅ | PyMuPDF ; PDF protégé ou scanné refusé avec un message clair |
| Segmentation par sections | ✅ | Chapitres détectés (sommaire du PDF ou titres « Chapitre 3 »), titres gardés avec leur contenu, coupure sur fins de phrase, chevauchement de 100 caractères |
| Gestion des figures et équations | ⚠️ | Équations : symboles, exposants et indices conservés (`10³`, `σ²`, `P(A∩B)`). Figures : non traitées (pas d'OCR ni de description d'image). |
| Embeddings pour documents longs (mémoire, temps) | ✅ | `multilingual-e5-small` (384 dim., CPU), calcul par lots, index HNSW, seuls les passages non indexés sont recalculés |
| Modèle spécialisé pour la summarization (T5, BART, GPT, Llama…) | ⚠️ | Le fournisseur mT5 (`csebuetnlp/mT5_multilingual_XLSum`) est codé (`summaries/services/providers/huggingface.py`) mais **jamais exécuté sur cette machine** (modèle non téléchargé, non testé). Tous les résumés existants sont **extractifs** (sélection de phrases du cours). |
| LLM pour les quiz et les réponses | ✅ | Qwen3 4B (Ollama) ; JSON des quiz validé, complément si des questions manquent |
| Interface web conviviale | ✅ | Django Templates + CSS + JS classique (Streamlit ou Gradio n'étaient que des exemples) : tableau de bord, quiz question par question, chat avec minuteur, responsive et accessible |

## 5. Livrables spécifiques (section 6.6)

| Livrable | État | Remarque |
|---|---|---|
| Exemples de résumés pour différents documents | ❌ | Des résumés existent dans la base (3 cours), mais ils ne sont pas exportés pour le rapport et sont tous extractifs. |
| Exemples de quiz générés avec correction | ❌ | 5 quiz existent dans la base, non exportés pour le rapport. |
| Évaluation qualitative des résumés et des quiz | ❌ | Seule la fidélité du **chatbot** est évaluée (`rag_faithfulness`). Il manque une grille de relecture pour les résumés (fidélité, concision, clarté) et pour les quiz (cohérence, pertinence). |

## 6. Critères d'évaluation (sections 4 et 6.7)

| Critère | Où en est le projet |
|---|---|
| Qualité technique du pipeline | Recherche hybride évaluée : passage attendu dans les 3 premiers pour 23 questions sur 23 (MRR 0,957), refus hors cours 8/8 |
| Pertinence et robustesse du chatbot | 6 réponses relues : 5 appuyées par leurs sources, 1 partiellement (à confirmer par la relecture de l'étudiante) ; marge du seuil de refus faible (0,010) |
| Qualité du code | 308 tests, 93 % de couverture, services séparés des vues, docstrings |
| Qualité du rapport PDF | ❌ à rédiger |
| Qualité du dépôt GitHub | README complet ; renommage du dépôt à faire |
| Originalité et extensions | Évaluation chiffrée avec intervalles de confiance, recherche hybride, sécurité (CSP, limitation de fréquence, anti-injection), tableau de bord et historique des notes, interface accessible |
| Qualité des résumés (fidélité, concision, clarté) | ⚠️ non évaluée ; extractif uniquement |
| Cohérence et pertinence des quiz | ⚠️ non évaluée formellement |
| Facilité d'utilisation pour un étudiant | ✅ interface vérifiée à 360, 768 et 1280 px |

## 7. Résultats mesurés

| Mesure | Résultat |
|---|---|
| Tests automatiques | 308, tous au vert ; couverture 93 % |
| Recherche : passage attendu dans les 3 premiers | 100 % (23/23) |
| Refus à tort / acceptation à tort (seuil 0,83) | 0/23 [IC95 0-14 %] / 0/8 [IC95 0-32 %] |
| Temps de recherche | ≈ 10 ms |
| Temps de réponse du chatbot (Qwen3 4B, RTX 2050) | 72,9 s en moyenne, 102 s au maximum |

## 8. Limites connues

1. **Chatbot lent** : la variante « thinking » de Qwen3 raisonne avant de répondre
   (≈ 1 min). La variante instruct serait plus rapide ; non retenue.
2. **Petit échantillon d'évaluation** : 23 questions et 8 hors cours ; marge du seuil
   faible (0,010).
3. **Résumés extractifs** : fidèles par construction (phrases du cours), mais moins
   fluides et moins concis qu'un résumé abstractif.
4. **Requêtes bloquantes** pendant les traitements d'IA (minuteur affiché).
5. **Pas d'OCR**, figures non traitées.
6. **Démonstration sur `runserver`** ; réglages de production prêts mais non déployés.

## 9. Démonstration conseillée (≈ 5 minutes)

1. Connexion, tableau de bord.
2. Import d'un PDF par glisser-déposer ; détail du cours (pages, passages).
3. Résumés court, moyen et détaillé.
4. Chatbot : une question avec réponse (montrer sources et pages), puis une question hors
   cours (refus immédiat). Lancer la première **en premier** et parler pendant la
   génération (≈ 1 min).
5. Quiz préparé à l'avance : le passer, montrer la note sur 20 et la correction.
6. Second compte : aucune donnée du premier n'est visible.
