# Spec · GUI pédagogique Kaldera, déploiement Azure, CI/CD

Brainstorming du 30/09/2026. Fait suite à la résolution des 3 limites connues de la PR
« Corrige l'orchestration » (branche `developpement/orchestration-cible`) et aux 4 livrables du
brief (fiche des schémas, cas réel annoté, note de diagnostic + schéma cible — tous les trois déjà
livrés — et l'URL de test fonctionnel, objet de cette spec).

## 1. Contexte et objectif

Kaldera est un orchestrateur multi-agents (`researcher`, `writer`, `reviewer`, `finalizer`) piloté
par un superviseur déterministe, avec un chemin « live » branché sur un vrai LLM (Azure AI,
endpoint compatible OpenAI). Le projet existe aujourd'hui comme bibliothèque Python + CLI, testée
(59 tests, grille de preuve 21/21), mais rien n'est accessible sans cloner le dépôt.

**Objectif** : une URL publique, une petite GUI pédagogique qui fait vivre à une classe ce que le
projet a appris sur l'orchestration multi-agents (rôles, garde-fous, déterministe vs vrai LLM), et
un pipeline qui la redéploie automatiquement. L'utilisateur du dépôt (débutant sur Azure) doit
pouvoir refaire la création des ressources lui-même via le portail, pas seulement lire une
commande CLI qu'il ne comprend pas.

## 2. Portée

**Dans le scope** :
- Une GUI Gradio à 3 onglets (Exécuter / Casser un garde-fou / Comparer).
- Le déploiement sur Azure Container Apps, avec un guide pas-à-pas portail (livrable, pas
  seulement de l'IaC).
- Un pipeline CI/CD GitHub Actions (tests sur PR, build + déploiement sur `main`), avec
  authentification OIDC vers Azure et un guide pas-à-pas portail pour le créer.

**Hors scope** :
- Multi-utilisateurs, authentification, isolation de session — un seul opérateur en projection
  (décidé au brainstorming).
- Comptage réel des tokens consommés par le LLM (limite déjà documentée dans le README du projet).
- Staging séparé de la production — un seul environnement, déploiement direct sur `main`.
- Nom de domaine personnalisé — l'URL `*.azurecontainerapps.io` fournie par défaut suffit.

## 3. Architecture de la GUI

Nouveau module dans le dépôt existant, réutilise tout le code d'orchestration sans le modifier :

```
src/kaldera/webapp/
  __init__.py
  app.py                 # Gradio Blocks, 3 onglets, point d'entrée
  broken_registries.py    # registres d'agents cassés en mémoire, pour l'onglet garde-fous
Dockerfile.web             # conteneur dédié à la GUI (le Dockerfile existant reste pour le CLI)
```

`gradio` est ajouté comme groupe de dépendances optionnel (`pyproject.toml`,
`[project.optional-dependencies] webapp = [...]`) — le cœur de la bibliothèque et le CLI restent
installables sans lui.

### Pourquoi aucun changement à `runner.py` / `graph.py` / `orchestrator.py`

Le point technique validé au brainstorming : `StateGraph.compile()` expose déjà `.stream(state)`,
qui renvoie un chunk après chaque nœud exécuté (vérifié à la main : deux nœuds → deux chunks, dans
l'ordre). La GUI appelle `build_graph(llm, limit).stream(state)` directement pour le suivi en
direct ; `run_scenario()` reste appelé tel quel pour le chemin déterministe (déjà instantané, rien
à streamer). Aucun de ces deux modules n'a donc besoin d'être touché pour cette spec.

### Onglet 1 — Exécuter

- Formulaire : sujet (texte libre), étapes à cocher (`RESEARCH`, `DRAFT`, `REVIEW`, `FINALIZE`,
  dans l'ordre choisi), bascule Déterministe / Vrai LLM.
- Déterministe : appelle `run_scenario()` avec un scénario construit depuis le formulaire, affiche
  le résultat final (statut, artefacts, `stop_reason` le cas échéant) — instantané, pas de
  streaming nécessaire.
- Vrai LLM : construit l'état initial, appelle `build_graph(build_llm(), limit).stream(state)`,
  pousse une ligne dans l'UI à chaque chunk reçu (« chef confie DRAFT à writer… reçu »), affiche
  chaque artefact dès qu'il apparaît dans le chunk.
- Bascule Vrai LLM désactivée pendant un court délai après chaque déclenchement (garde-fou de
  coût, cf. section 5) ; ce délai résiste à un rechargement de page (calculé côté serveur, pas
  seulement désactivé côté client).

### Onglet 2 — Casser un garde-fou

Quatre boutons pré-câblés, chacun appelle **`run_scenario()`** (le chef déterministe, pas
`build_graph`/`.stream()`) avec un `agents_by_name` substitué en mémoire — exactement le paramètre
que `runner.run_scenario()` expose déjà et que `tests/test_runner.py` utilise pour son propre
agent factice. Jamais de modification de fichier source, même esprit que
`scripts/grille_de_preuve.py` mais réutilisable en direct plutôt que par patch-and-revert. Appel
synchrone, instantané, gratuit — pas de streaming nécessaire ici.

C'est un choix délibéré, pas seulement de simplicité : la logique qui détecte une progression
invalide (réception stricte, relance unique, annulation) vit dans `runner.py`
(`_artifacts_ok`/`progression_ok`), pas dans `graph.py`, dont chaque nœud avance après l'appel à
l'agent sans revérifier ce qu'il a produit (cf. le commentaire `ponytail` déjà présent dans
`graph.py`). Rejouer ces quatre défauts demande donc le chef déterministe, pas le chemin live.

Chaque registre cassé garde un nom et un `handles` cohérents avec le poste qu'il occupe : la
première vérification de `check_demand` (`getattr(agent, "name", key) != key`) refuserait sinon la
demande *avant* de démarrer (`invalid_demand:team_incomplete`) — instructif, mais pas ce que ce
bouton précis doit montrer. Seul l'`act()` du sous-agent est cassé :

| Bouton | Registre cassé | `stop_reason` attendu |
|---|---|---|
| Rôle hors périmètre | sous-classe de `Researcher` dont `act()` lève `RoleViolation` directement (contourne son propre `accepts()`, qui reste correct) | `role_violation` |
| Budget de tokens dépassé | sous-classe de `Researcher` avec `token_budget = 0` | `budget_exceeded` |
| Limite d'étapes atteinte | registre inchangé, `run_scenario(scenario, max_iterations=0)` | `step_limit_reached` |
| Agent bloqué (ne progresse pas) | sous-classe de `Researcher` dont `act()` ne fait rien (n'écrit pas l'artefact attendu) | `reception_refused`, après une relance unique — visible dans `state.log` |

Chaque bouton affiche le `stop_reason` final en évidence, et le journal complet du run
(`state.log`, déjà produit par `logging_utils.record`) pour montrer où le chef a refusé.

### Onglet 3 — Comparer

Deux colonnes, même sujet/étapes : la colonne déterministe se lance automatiquement (gratuite,
instantanée) ; la colonne vrai LLM a son propre bouton (le garde-fou de coût de l'onglet 1
s'applique aussi ici). Objectif pédagogique : mêmes garde-fous des deux côtés, seul le contenu des
artefacts diffère.

## 4. Erreurs

Une panne réseau ou une erreur de l'API LLM pendant `.stream()` est captée au niveau de la GUI
(try/except autour de la boucle de consommation du générateur), affichée comme un message
utilisateur clair avec `stop_reason=llm_error`, sans crash de la page Gradio. Les erreurs de
validation du formulaire (aucune étape cochée, sujet vide) sont bloquées avant l'appel, avec un
message dans l'UI — pas de nouvelle règle métier, `check_demand()` existant fait déjà ce travail
côté orchestrateur ; la GUI relaie simplement son motif de refus (`invalid_demand:*`).

## 5. Garde-fou de coût (vrai LLM)

Un verrou côté serveur (variable en mémoire du process, horodatage du dernier déclenchement réel)
impose un délai minimal (proposé : 15 secondes, ajustable) entre deux runs vrai-LLM. Le bouton
correspondant est visuellement désactivé pendant ce délai, et l'appel serveur est de toute façon
refusé si le délai n'est pas écoulé (protège contre un double-clic ou un F5). Aucune limite de ce
type sur l'onglet « Casser un garde-fou » (toujours déterministe, donc gratuit).

## 6. Déploiement Azure

### Choix et raisons

- **Azure Container Apps** (plan Consumption), pas App Service : scale-to-zero quand personne ne
  l'utilise, donc coût quasi nul entre deux démos. C'est le service Azure actuel recommandé pour
  un conteneur unique sans besoin de VM dédiée.
- **Registre d'images : GitHub Container Registry (`ghcr.io`)**, pas Azure Container Registry :
  gratuit, zéro ressource Azure de plus à créer/payer, authentification via le `GITHUB_TOKEN`
  déjà fourni par GitHub Actions. Container Apps sait tirer une image publique ou privée depuis
  ghcr.io.
- Secrets `AZURE_AI_ENDPOINT` / `AZURE_AI_API_KEY` / `AZURE_AI_MODEL` : stockés comme **secrets du
  Container App** (Azure les chiffre au repos), jamais dans l'image ni dans le dépôt.

### Ressources à créer (portail Azure)

1. Un **groupe de ressources** (Resource Group) dédié, ex. `rg-kaldera-demo`.
2. Un **environnement Container Apps** (Container Apps Environment) dans ce groupe — le portail
   crée automatiquement un espace de travail Log Analytics associé, pas d'étape séparée.
3. Un **Container App** dans cet environnement, configuré pour :
   - tirer l'image depuis `ghcr.io/<owner>/kaldera-team-ko-webapp:latest` ;
   - exposer le port Gradio (7860 par défaut) en ingress externe ;
   - `min replicas = 0` (scale-to-zero) ;
   - les 3 secrets Azure AI, référencés comme variables d'environnement du conteneur.

**Livrable** : un guide `doc/guides/deploiement_azure_portail.md`, rédigé pendant
l'implémentation, qui déroule ces trois créations écran par écran (noms exacts des menus et
boutons du portail Azure, pas de capture d'écran — l'interface change trop souvent pour que des
images restent à jour ; le texte décrit précisément où cliquer). Couvre aussi : où retrouver l'URL
publique une fois le Container App créé, et comment lire les logs depuis le portail en cas de
souci.

### Limite connue à documenter

Le scale-to-zero implique un temps de démarrage à froid (quelques secondes à la première requête
après une période d'inactivité). Le guide recommandera d'ouvrir l'URL une minute avant de présenter
en classe, pour « réveiller » le conteneur.

## 7. CI/CD (GitHub Actions)

### Pipeline

Un seul fichier `.github/workflows/ci-cd.yml`, deux jobs :

- **`test`** (toujours, sur PR et sur push) : `ruff check`, `mypy src`, `pytest` (le test vrai-LLM
  se saute automatiquement via `kaldera.llm.available()` — aucun secret nécessaire aux PR de
  forks), puis `docker build` de `Dockerfile.web` sans push (vérifie que l'image se construit).
- **`deploy`** (seulement sur push vers `main`, après succès de `test`) : build + push de l'image
  vers `ghcr.io` (tags `sha` et `latest`), puis `az containerapp update --image ...` pour
  redéployer le Container App existant.

### Authentification GitHub → Azure : OIDC fédéré

Pas de secret Azure longue durée stocké dans GitHub (pas de `AZURE_CREDENTIALS` JSON, pas de mot
de passe d'application). À la place :

1. Une **App Registration** Azure AD (portail : *Microsoft Entra ID* → *Inscriptions
   d'applications*), sans secret généré.
2. Une **identité fédérée** (*Federated credentials*) sur cette App Registration, scopée au repo
   et à la branche `main` (`repo:sofiane-git/kaldera-team-ko:ref:refs/heads/main`) — GitHub prouve
   son identité à Azure via un jeton OIDC signé à chaque run, sans secret partagé à faire fuiter.
3. Un **rôle attribué** (*IAM* → *Ajouter une attribution de rôle*) sur le groupe de ressources,
   scopé à cette App Registration (rôle `Contributor`, ou plus fin :
   `Container Apps Contributor` + `AcrPull` si un ACR est ajouté plus tard).
4. Trois secrets GitHub (pas de mot de passe parmi eux, juste des identifiants publics) :
   `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`.

**Livrable** : un guide `doc/guides/github_actions_azure_oidc_portail.md`, rédigé pendant
l'implémentation, qui déroule ces quatre étapes écran par écran dans le portail Azure et dans les
Settings GitHub du repo.

## 8. Tests

- `tests/test_webapp_guardrails.py` — les 4 registres cassés, testés par import direct (pas de
  subprocess), vérifient le `stop_reason` attendu de chaque case du tableau section 3.
- `tests/test_webapp_app.py` — test de fumée : l'objet `gr.Blocks` se construit sans lever
  d'exception. Pas de test end-to-end de rendu (hors de portée, faible valeur pour un outil à un
  seul opérateur).
- La suite existante (59 tests, `ruff`, `mypy`, grille de preuve) reste inchangée et doit continuer
  de passer : aucun fichier du cœur de l'orchestration n'est modifié par cette spec.
- Le job CI `test` n'exécute jamais le test vrai-LLM (`kaldera.llm.available()` renvoie faux sans
  les secrets, absents des PR de forks par construction) : le pipeline reste gratuit et
  déterministe.

## 9. Risques et limites assumées

- **Démarrage à froid** (section 6) — assumé, documenté, contourné par un « réveil » avant la
  démo plutôt que par un `min replicas ≥ 1` qui ferait tourner (et payer) le conteneur en continu.
- **Coût du vrai LLM en GUI** — limité par le garde-fou de la section 5, mais pas nul : chaque clic
  reste un vrai appel facturé par Azure AI.
- **Un seul environnement** — un déploiement cassé sur `main` casse la démo publique jusqu'au
  correctif suivant. Acceptable pour un outil pédagogique à faible enjeu ; à revisiter si l'usage
  s'étend au-delà d'une démo en classe.
