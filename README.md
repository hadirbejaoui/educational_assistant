# Assistant pédagogique intelligent

Application web Django qui aide un étudiant à réviser **ses propres cours** (PDF ou TXT) :
résumés à trois niveaux, quiz à choix multiples corrigés et notés sur 20, et un chatbot
qui répond **uniquement à partir du cours**, en citant les pages utilisées.

Tout fonctionne en local, sans service payant : PostgreSQL + pgvector pour la recherche,
Sentence Transformers pour les embeddings, Ollama (Qwen3) pour le LLM. Le fournisseur de
LLM reste interchangeable (Ollama, Gemini ou Anthropic, une ligne dans `.env`).

Bilan pour la soutenance (état de chaque fonctionnalité, résultats mesurés, limites) : [`BILAN.md`](BILAN.md).

**Démarrage rapide** (une fois les prérequis de la section 3 installés) :

```powershell
git clone https://github.com/hadirbejaoui/educational_assistant. educational_assistant
cd educational_assistant
python -m venv .venv ; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env          # puis compléter .env (section 4)
python manage.py migrate
python manage.py demo --sans-llm     # démonstration en ligne de commande (section 3.6)
python manage.py runserver           # puis http://127.0.0.1:8000
```

---

## 1. Fonctionnalités

| Fonction | Ce qu'elle fait |
|---|---|
| Comptes | Inscription, connexion, profil. Chaque compte a son propre espace : ses cours, résumés, quiz, notes et conversations ; ceux d'un autre compte donnent 404. L'administrateur (`is_staff`) gère les comptes dans l'admin Django (`/admin/`) et a lui aussi son espace privé. |
| Cours | Import PDF/TXT par chaque compte (glisser-déposer), extraction PyMuPDF, nettoyage, découpage en passages, indexation vectorielle dès l'import ; réindexation, retraitement et suppression de ses propres cours. |
| Résumés | Court, moyen, détaillé : longueur proportionnelle au cours et consignes propres à chaque niveau (voir ci-dessous). Résumé abstractif par LLM (Qwen3 4B instruct) avec génération contrôlée ; mT5 et extractif disponibles et comparés. |
| Quiz | QCM générés par le LLM, JSON validé, complément automatique si des questions manquent, note sur 20, correction expliquée. |
| Chatbot | RAG : recherche hybride (vecteurs + BM25, fusion RRF), réponse citée, refus si le cours ne contient pas la réponse. |
| Tableau de bord | Compteurs, moyenne aux quiz, derniers cours, dernières notes, dernières conversations ; historiques paginés. |

## 2. Architecture

```
config/          réglages (settings.py = développement, settings_production.py = production), URLs
core/            accès aux cours (permissions.py), tableau de bord, pagination, limitation de fréquence, en-têtes de sécurité, balises d'interface, commandes demo et export_examples
accounts/        utilisateurs (modèle User personnalisé, e-mail unique)
courses/         documents, pages, passages ; services : extraction, nettoyage, découpage, embeddings, recherche
summaries/       résumés ; services : sections, fournisseurs (LLM, Hugging Face mT5, extractif)
quizzes/         quiz, questions, choix, tentatives ; services : génération, validation JSON, correction
chatbot/         conversations, messages ; service RAG ; commandes d'évaluation
llm/             clients Ollama / Gemini / Anthropic derrière une interface commune, protection anti-injection
templates/       gabarits Django (aucun CSS ni JS dans les gabarits) ; templates/admin/ habille l'admin Django (static/css/admin.css)
static/css/      design system : tokens, base, layout, components, pages
static/js/       JavaScript classique : main (menu, chargements), chat, quiz, upload
evaluation/      questions d'évaluation sur les cours réels, grilles de relecture
scripts/         sauvegarde et restauration (PowerShell)
demo/            cours d'exemple utilisé par la commande de démonstration
```

Règle suivie partout : **la logique métier est dans `services/`**, les vues ne font que
lire la requête, appeler un service et choisir la réponse.

### Les trois niveaux de résumé

Un cours est découpé en sections qui tiennent dans le contexte du modèle
(`SUMMARY_LLM_SECTION_CHARS`, 6 000 caractères pour le LLM), puis résumé en map-reduce
(`summaries/services/summarization.py`) :

| Niveau | Longueur visée (`SUMMARY_LEVELS`) | Consignes données au LLM | Fusion |
|---|---|---|---|
| Court | 5 % du cours, entre 40 et 150 mots | idées essentielles, un paragraphe, sans détails ni exemples | résumés partiels fusionnés, puis synthèse finale |
| Moyen | 12 % du cours, entre 120 et 600 mots | notions importantes expliquées brièvement, un paragraphe par notion, définitions essentielles | résumés partiels fusionnés, puis synthèse finale |
| Détaillé | 25 % du cours, entre 250 et 2 500 mots | toutes les parties dans l'ordre du cours, intertitres, définitions, exemples, chiffres, listes | aucune synthèse finale (elle perdrait des détails) : une partie par section, sous un intertitre de pages |

Chaque section reçoit une part de la longueur visée proportionnelle à sa taille. Les
tours de fusion réduisent le texte jusqu'à ce qu'il tienne dans une section : aucune
requête ne dépasse le contexte du modèle (`LLM_NUM_CTX`). Un résumé n'est jamais plus
long que le cours lui-même. Les intertitres et listes produits par le LLM sont affichés
par le filtre `rich_text` (`core/templatetags/ui.py`), qui échappe tout le reste du texte.

### Le chemin d'une question au chatbot

1. La question est transformée en vecteur (`multilingual-e5-small`, 384 dimensions).
2. **Recherche vectorielle** : pgvector classe les passages du cours par similarité cosinus.
3. **Recherche lexicale BM25** sur les mêmes passages (termes exacts, sigles, nombres).
4. **Fusion RRF** des deux classements (Reciprocal Rank Fusion, k = 60).
5. **Sélection** : si la meilleure similarité est sous `RAG_MIN_SCORE`, refus immédiat
   sans appeler le LLM ; sinon les passages proches du meilleur sont gardés.
6. **Génération** : le LLM reçoit les passages numérotés et doit citer [1], [2]...
   ou répondre `NON_TROUVE`. Les citations inventées sont retirées.

## 3. Installation sous Windows (pas à pas)

### 3.1 Prérequis

| Logiciel | Version testée | Remarque |
|---|---|---|
| Python | 3.13 | cocher « Add python.exe to PATH » |
| PostgreSQL | 18 | installeur EnterpriseDB |
| pgvector | 0.8.2 | extension PostgreSQL, à compiler sous Windows (voir 3.2) |
| Ollama | 0.40 | https://ollama.com/download |
| Git | — | |

Matériel de référence : 16 Go de RAM, GPU NVIDIA RTX 2050 (4 Go). Sans GPU, tout
fonctionne mais le LLM est nettement plus lent.

### 3.2 pgvector sur PostgreSQL 18 (Windows)

pgvector n'est pas fourni par l'installeur PostgreSQL. Il faut le compiler une fois :

1. Installer **Visual Studio Build Tools** (charge de travail « Développement Desktop en C++ »).
2. Ouvrir **« x64 Native Tools Command Prompt for VS »** en administrateur, puis :
   ```bat
   set "PGROOT=C:\Program Files\PostgreSQL\18"
   cd %TEMP%
   git clone --branch v0.8.2 https://github.com/pgvector/pgvector.git
   cd pgvector
   nmake /F Makefile.win
   nmake /F Makefile.win install
   ```
3. L'extension est ensuite créée automatiquement par la migration
   `courses/0003_vector_extension` (l'utilisateur PostgreSQL doit avoir le droit
   `CREATE` sur la base ; avec l'utilisateur `postgres`, c'est le cas).

### 3.3 Projet

```powershell
git clone https://github.com/hadirbejaoui/educational_assistant. educational_assistant
cd educational_assistant
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt          # requirements-dev.txt pour les tests et la couverture

Copy-Item .env.example .env              # puis remplir .env (voir section 4)
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

& "C:\Program Files\PostgreSQL\18\bin\createdb.exe" -U postgres educational_assistant
python manage.py migrate
python manage.py createsuperuser         # compte administrateur : accès à l'admin Django (/admin/)
```

Les étudiants créent leur compte depuis la page d'inscription.

### 3.4 Ollama

```powershell
ollama pull qwen3:4b            # 2,5 Go : chatbot et quiz
ollama pull qwen3:4b-instruct   # 2,5 Go : résumés (sans raisonnement, rapide)
ollama list                   # vérifie que le modèle est présent
```

Le premier calcul d'embeddings télécharge `intfloat/multilingual-e5-small` (~470 Mo)
depuis Hugging Face ; ensuite tout fonctionne hors ligne.

### 3.5 Lancer

```powershell
python manage.py runserver
```

Puis ouvrir http://127.0.0.1:8000. Après une mise à jour du CSS, un seul **Ctrl+F5**
suffit : les fichiers statiques portent ensuite une version dans leur URL (`?v=...`).

### 3.6 Démonstration

La commande `demo` déroule tout le pipeline dans le terminal, sur un cours d'exemple
fourni (`demo/cours_exemple.txt`), sans passer par l'interface :

```powershell
python manage.py demo --sans-llm            # sans Ollama : prétraitement, indexation, recherche, résumés extractifs
python manage.py demo                       # complet : résumés par LLM, QCM corrigé, chatbot (≈ 5 à 10 min)
python manage.py demo --fichier cours.pdf   # sur votre propre document (PDF ou TXT)
python manage.py demo --question "..."      # avec votre question au chatbot
```

Étapes affichées : import et découpage, indexation, recherche hybride (3 meilleurs
passages avec pages et scores), résumés court / moyen / détaillé, QCM de 3 questions
avec la bonne réponse et l'explication, puis deux questions au chatbot (l'une sur le
cours, citée ; l'autre hors cours, refusée). Un compte temporaire est créé puis supprimé
avec tout ce qu'il contient ; `--garder` le conserve pour l'ouvrir ensuite dans
l'interface.

Parcours conseillé dans l'interface : créer un compte, importer un cours, ouvrir
« Résumés » (trois onglets), générer un quiz et le passer, poser une question au chatbot
(sources dépliables), puis une question hors cours (refus immédiat).

## 4. Variables d'environnement (`.env`)

Le fichier `.env.example` liste et commente toutes les variables. Les principales :

| Variable | Rôle | Valeur par défaut |
|---|---|---|
| `DJANGO_SECRET_KEY` | clé secrète, unique, jamais commitée | — (obligatoire) |
| `DJANGO_DEBUG` | mode développement | `False` |
| `DJANGO_ALLOWED_HOSTS` | noms d'hôte autorisés | — |
| `DJANGO_SETTINGS_MODULE` | `config.settings_production` en production | `config.settings` |
| `DJANGO_HTTPS` | active cookies sécurisés, redirection HTTPS, HSTS | `False` |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | PostgreSQL | — |
| `LLM_PROVIDER` | `ollama`, `gemini` ou `anthropic` | — |
| `LLM_MODEL`, `LLM_API_KEY`, `LLM_BASE_URL` | modèle, clé (cloud), adresse d'Ollama | — |
| `LLM_TIMEOUT` | délai maximal d'une réponse (s) | `90` |
| `SUMMARY_PROVIDER` | `llm`, `huggingface` (mT5) ou `extractive` | `extractive` (`.env.example` : `llm`) |
| `SUMMARY_LLM_MODEL` | modèle Ollama réservé aux résumés (vide = `LLM_MODEL`) | — (`.env.example` : `qwen3:4b-instruct`) |
| `EMBEDDING_MODEL_NAME` | modèle d'embeddings (384 dimensions) | `intfloat/multilingual-e5-small` |
| `RETRIEVAL_LEXICAL_WEIGHT` | poids de BM25 dans la fusion (0 = vecteurs seuls) | `1` |
| `RAG_MIN_SCORE`, `RAG_SCORE_WINDOW` | seuil de refus et fenêtre de sélection | `0.83`, `0.08` |
| `RATE_LIMIT_CHAT`, `RATE_LIMIT_QUIZ`, `RATE_LIMIT_SUMMARY` | limites par utilisateur | `6`/min, `10`/h, `10`/h |

## 5. Commandes de gestion

| Commande | Usage |
|---|---|
| `python manage.py demo [--sans-llm] [--fichier F] [--garder]` | démonstration de bout en bout sur un cours d'exemple (section 3.6) |
| `python manage.py index_documents [--document ID] [--force]` | calcule les embeddings des passages |
| `python manage.py reprocess_documents [--document ID]` | ré-extrait, re-découpe et réindexe (après un changement du découpage) |
| `python manage.py rag_grep ID "texte"` | liste les passages contenant un texte |
| `python manage.py rag_diagnose ID "question" [--find "texte"]` | scores cosinus, RRF et rangs de chaque passage |
| `python manage.py rag_evaluate [--pooled] [--weights 0,1,2]` | compare vecteurs / BM25 / hybride sur un corpus synthétique multi-matières |
| `python manage.py rag_eval_courses [--details]` | évaluation et calibration sur **vos cours** (`evaluation/rag_questions.json`) |
| `python manage.py rag_faithfulness --sample 10` puis `--score fichier.csv` | fidélité des réponses, relue à la main |
| `python manage.py compare_summaries --document ID [--level short]` | compare extractif, mT5 et LLM sur un cours (sans rien enregistrer) |
| `python manage.py export_examples` puis `--score-summaries` / `--score-quiz` | exemples de résumés et de quiz pour le rapport, grilles d'évaluation qualitative |

## 6. Tests et qualité

```powershell
pip install -r requirements-dev.txt
python manage.py check
python manage.py test                              # toute la suite
python -m coverage run manage.py test
python -m coverage report                          # couverture par fichier (voir .coveragerc)
```

Les tests n'appellent ni Internet, ni Ollama, ni le vrai modèle d'embeddings : ils
utilisent de faux modèles déterministes. Ils couvrent l'isolation entre comptes
(404, identifiants forgés, RAG limité aux cours du compte : `core/test_isolation.py`), les trois niveaux de résumé sur des cours courts
et longs, l'échappement du HTML venant du LLM, la sécurité, et des parcours de bout en
bout (`core/test_end_to_end.py`).

## 7. Sécurité

- **Isolation des comptes, côté serveur** : toutes les vues passent par
  `user_documents(user)` (`core/permissions.py`) ; quiz, tentatives et conversations sont en
  plus filtrés par utilisateur. Un identifiant forgé (URL ou formulaire) donne 404 (pas 403,
  pour ne pas révéler l'existence de l'objet). Masquer un bouton n'est pas une sécurité.
- **RAG cloisonné** : la recherche (vecteurs pgvector et BM25) ne porte que sur les passages
  du cours de la conversation, lui-même vérifié comme appartenant au compte.
- **Fichiers privés** : `media/` n'est jamais servi directement ; le fichier original
  passe par la vue `courses:file`, qui vérifie la propriété.
- **Validation des imports** : extension, taille (`MAX_UPLOAD_SIZE_MB`), signature `%PDF-`,
  côté serveur (le contrôle du navigateur n'est qu'un confort).
- **Limitation de fréquence** sur le chat, les quiz et les résumés (`core/ratelimit.py`).
- **En-têtes** : Content-Security-Policy stricte (aucun script inline), X-Frame-Options,
  nosniff, Permissions-Policy ; CSRF sur tous les formulaires.
- **Injection de prompt** : le texte des cours est traité comme une donnée, les faux
  délimiteurs (`===`, jetons de rôle) sont neutralisés (`llm/safety.py`), les réponses
  sont affichées comme du texte, les citations vérifiées, le JSON des quiz validé.
  Limite : aucune technique n'empêche à coup sûr un LLM de suivre une consigne cachée.
- **Production** : `config/settings_production.py` refuse de démarrer sans
  `DJANGO_ALLOWED_HOSTS` ou avec une clé secrète faible. `python manage.py check --deploy`
  ne signale plus que les réglages HTTPS si le site est servi en HTTP local.

## 8. Production et sauvegarde

```powershell
$env:DJANGO_SETTINGS_MODULE = "config.settings_production"
python manage.py collectstatic --noinput
python manage.py check --deploy
```

Journaux : `logs/app.log` (rotation 5 × 5 Mo). Sauvegarde et restauration :

```powershell
.\scripts\backup.ps1 -Keep 7          # base (pg_dump) + fichiers importés, horodatés, dans .\backups\
.\scripts\restore.ps1 -Dump .\backups\db_AAAAMMJJ_HHMM.dump -Media .\backups\media_AAAAMMJJ_HHMM.zip
```

### Choix retenu pour le projet : `runserver` en local

L'application est présentée avec le serveur de développement de Django
(`python manage.py runserver`, réglages `config.settings`, `DJANGO_DEBUG=True`) sur le
PC qui héberge aussi PostgreSQL et Ollama (GPU). C'est suffisant pour une démonstration
mono-utilisateur, mais **ce n'est pas un serveur de production** : un seul processus,
pas de fichiers statiques optimisés, pages d'erreur détaillées en mode DEBUG.

Ce qui est prêt pour passer en production plus tard, sans le refaire :

- `config/settings_production.py` (DEBUG désactivé, clé et hôtes vérifiés, cookies
  sécurisés en HTTPS, fichiers statiques versionnés, journaux) ;
- les scripts de sauvegarde et de restauration ci-dessus ;
- options étudiées : **waitress + WhiteNoise** sous Windows (recommandée : même machine
  que le GPU), Docker Compose (GPU sous WSL2 + NVIDIA Container Toolkit, images de
  plusieurs Go), VPS Linux (pas de GPU abordable : LLM sur CPU, très lent).

Attention : `runserver` avec `config.settings_production` ne sert pas les fichiers
statiques (DEBUG désactivé) ; l'interface s'afficherait sans CSS. Pour la démonstration,
rester sur les réglages de développement.

## 9. Choix techniques justifiés

| Choix | Pourquoi |
|---|---|
| Django Templates + JS classique | exigence du projet ; pas d'étape de compilation, fonctionne hors ligne |
| Vues Django, sans Django REST Framework | l'interface est rendue côté serveur et seul le chat appelle une vue JSON : une API REST n'aurait aucun client. Les permissions sont appliquées dans les vues (`core/permissions.py`), sans dépendance supplémentaire |
| Un espace privé par compte | chaque étudiant étudie ses propres cours ; un résumé appartient à son cours, donc à un seul compte, sans champ propriétaire redondant |
| PostgreSQL + pgvector | vecteurs et données métier dans la même base, filtrage par document en SQL |
| `multilingual-e5-small` (384 dim.) | français + anglais, léger (CPU), qualité suffisante mesurée par `rag_evaluate` |
| Recherche hybride RRF | les vecteurs comprennent les reformulations, BM25 retrouve les termes exacts ; RRF fusionne des rangs, sans calibrer des scores incomparables |
| Seuil de refus avant le LLM | une question hors cours est refusée en 10 ms au lieu d'une minute de génération |
| Ollama + Qwen3 4B | gratuit, local, tient dans 4 Go de VRAM ; données des étudiants jamais envoyées à un tiers |
| Résumés par LLM « instruct » avec génération contrôlée | comparaison mesurée sur des cours réels (`compare_summaries`) : mT5 XLSum, entraîné sur des articles de presse, **invente des faits** (« annoncée vendredi par le président de l'Assemblée nationale ») ; Qwen3 reste fidèle au texte. La variante instruct résume une section en 10 à 16 s, contre 7 à 8 min pour la variante « thinking » |
| Extractif conservé en secours | instantané, sans GPU, ne peut pas inventer (phrases du cours) |

## 10. Limites connues

- **Lenteur du LLM local** : le tag `qwen3:4b` installé correspond à la variante
  « thinking » (même empreinte que `qwen3:4b-thinking-2507-q4_K_M` sur ollama.com).
  Elle raisonne 500 à 1 700 tokens avant chaque réponse, ignore `think: false`, et le
  raisonnement est retiré avant affichage (`llm/ollama.py`). Mesuré sur 6 questions de
  cours réels, machine au repos : **72,9 s en moyenne, 102 s au maximum** ; sous
  charge, une réponse a dépassé 300 s. La variante sans raisonnement
  `qwen3:4b-instruct` est utilisée pour les **résumés** (10 à 16 s par section) ; le
  chatbot et les quiz restent sur `qwen3:4b`.
- **Fidélité des résumés** : même avec un prompt contrôlé, un petit LLM peut simplifier
  à l'excès une règle (ex. « dissolution si plus de 50 associés » au lieu de
  « transformation en SA dans un délai d'un an, sinon dissolution judiciaire possible »).
  D'où la grille de relecture (`export_examples`) et le maintien de l'extractif en secours.
- **Requêtes bloquantes (choix assumé)** : résumé, quiz et chat occupent la requête
  HTTP pendant le traitement. L'interface affiche un minuteur, prévient au-delà de
  90 s, et le navigateur abandonne après `LLM_TIMEOUT` + 30 s en le disant. Une file de
  tâches (thread + polling, ou Celery + Redis) a été étudiée et écartée : le goulot est
  le GPU, qui ne traite qu'une génération à la fois, donc l'attente ne serait pas plus
  courte ; elle ajouterait des composants à installer et à maintenir.
- **Serveur de démonstration** : `runserver`, mono-processus (voir section 8). La
  limitation de fréquence utilise le cache en mémoire, exact pour un seul processus.
- **Seuil de refus** : calibré sur peu de questions ; la marge entre questions avec et
  sans réponse est faible (≈ 0,01 de cosinus sur les cours testés).
- **PDF scannés** : pas d'OCR, le texte doit être sélectionnable.
- **Fidélité** : un modèle de 4 milliards de paramètres peut déformer une source ; les
  pages citées permettent à l'étudiant de vérifier.
