# Présentation orale · Diagnostic Kaldera

Kaldera est un orchestrateur multi-agents : un chef confie chaque étape d'une tâche à un agent
spécialisé, qui la traite et rend la main au chef. La tâche se découpe en quatre étapes :
`RESEARCH` (rechercher), `DRAFT` (rédiger), `REVIEW` (relire/corriger), `FINALIZE` (clore). Quatre
agents leur correspondent : `Researcher`, `Writer`, `Reviewer`, `Finalizer`.

Le bug central : quand l'étape `REVIEW` arrive, le chef l'envoie au `Writer`, pas au `Reviewer`. Le
`Writer` accepte n'importe quelle étape, se relit lui-même, et le `Reviewer` n'est jamais appelé.
Le flux se termine `done` sans qu'aucune relecture ait eu lieu, et rien ne le signale.

En une phrase : le chef délègue mais ne vérifie jamais ce qu'on lui rend. La suite montre où ça se
voit dans le code, comment ça a été détecté, et comment ça se corrige.

Méthode de détection : lecture complète du dépôt, puis exécution des tests fournis, avec 14 échecs
sur 14. Les défauts se cachaient les uns les autres : le premier plantage empêchait de voir les
suivants. Il a fallu les lever un par un, en mémoire, sans toucher au dépôt, pour voir la suite.
Une fois tout levé, le scénario principal se terminait `done`, dans le budget, sans qu'aucune
relecture n'ait eu lieu. C'est ce résultat qui a mis le doigt sur le vrai problème.

---

## 1. L'état actuel

```mermaid
%%{init: {"theme": "base", "themeVariables": {"fontFamily": "Helvetica", "fontSize": "15px", "primaryColor": "#FFFFFF", "lineColor": "#64748B", "edgeLabelBackground": "#FFFFFF"}, "flowchart": {"wrappingWidth": 240, "curve": "basis"}}}%%
flowchart TD
  DEM("Demande du client<br/>sujet + liste d'étapes"):::besoin --> CHEF

  subgraph SG_CHEF[" "]
    CHEF("Le chef<br/>fait avancer sans jamais vérifier<br/>ce qu'on lui rend"):::pilot
  end

  CHEF -- "RESEARCH" --> RES("Researcher"):::v1
  CHEF -- "DRAFT" --> WRI("Writer"):::v1
  CHEF -. "REVIEW, envoyée par erreur" .-> WRI
  CHEF -. "REVIEW, jamais envoyée ici" .-> REV("Reviewer<br/>existe, mais n'est jamais appelé"):::v1
  CHEF -. "FINALIZE, agent absent de l'équipe" .-> FIN("Finalizer"):::v1

  RES --> CHEF
  WRI --> CHEF
  FIN --> CHEF

  subgraph SG_DEFAUTS["Cinq défauts observés"]
    direction LR
    D1("① Boucle latente<br/>la limite d'étapes est calculée,<br/>jamais lue"):::gate
    D2("② Fin de flux cassée<br/>le chef plante après la dernière étape ;<br/>il passe lui-même le statut à fait"):::gate
    D3("③ Conflit sur la relecture<br/>le writer occupe le poste du reviewer<br/>et réécrit son propre brouillon"):::gate
    D4("④ Angle mort<br/>le journal ne dit pas qui a agi ;<br/>le budget de jetons n'arrête personne"):::gate
    D5("⑤ Défauts masquants<br/>la demande n'est pas lue ; la relecture<br/>est mal nommée ; le finalizer manque"):::gate
  end

  CHEF -.-> D1
  CHEF -.-> D2
  WRI -.-> D3
  CHEF -.-> D4
  DEM -.-> D5

  subgraph SG_LEGEND["Légende"]
    direction LR
    LBESOIN("demande d'entrée"):::besoin
    LPILOT("le chef"):::pilot
    LV1("code actuel"):::v1
    LGATE("défaut constaté"):::gate
  end

  classDef besoin fill:#E8F1FC,stroke:#2563EB,color:#1E3A5F
  classDef v1 fill:#EEF1F5,stroke:#64748B,color:#334155
  classDef chaine fill:#F1ECFB,stroke:#7C3AED,color:#4C1D95
  classDef gate fill:#FEF6E7,stroke:#D97706,color:#7C4A03
  classDef data fill:#E9F8F0,stroke:#059669,color:#065F46
  classDef obs fill:#E7F8FA,stroke:#0891B2,color:#164E5C
  classDef pilot fill:#FDECF3,stroke:#DB2777,color:#831843

  style SG_CHEF fill:none,stroke:#D1D5DB,stroke-dasharray: 4 4
  style SG_DEFAUTS fill:none,stroke:#D1D5DB,stroke-dasharray: 4 4
  style SG_LEGEND fill:none,stroke:#D1D5DB,stroke-dasharray: 4 4
```

Trois points portent l'essentiel du diagnostic :

1. La boucle possible sur l'étape en cours : rien ne compte le nombre de fois où un agent est
   rappelé. La limite (`max_steps`) est calculée dans `runner.py` mais jamais lue.
2. Le routage cassé sur `REVIEW` : la table `STEP_TO_AGENT`, dans `orchestrator.py`, associe
   `REVIEW` à `"writer"` au lieu de `"reviewer"`. Le `Reviewer` existe, gère bien `REVIEW`, mais
   n'est jamais routé vers.
3. L'absence de contrôle du chef : il fait avancer l'étape sans vérifier quel artefact a été écrit,
   ni par quel agent.

Un niveau plus bas : le rôle d'un agent est déclaré à trois endroits différents dans le code : la
table de routage (`orchestrator.py`), la liste des étapes qu'il gère et sa propre fonction
d'acceptation (`writer.py`). Rien ne vérifie que ces trois déclarations concordent. Pour `REVIEW`,
elles se contredisent, et c'est cette contradiction qui casse le flux. Le code a écrit les
garde-fous, mais ne les applique jamais.

Trois causes racines expliquent les cinq défauts, pas cinq causes indépendantes. Premièrement, les
garde-fous existent à moitié : la limite d'étapes est calculée mais pas lue, le budget de jetons est
additionné mais jamais comparé, le refus hors rôle existe mais le `Writer` le contourne.
Deuxièmement, le rôle de chaque agent est déclaré trois fois sans qu'aucune vérification ne les
recoupe. Troisièmement, le chef délègue sans réceptionner : il ne vérifie ni que l'étape a avancé,
ni ce qui a été produit, ni qui l'a produit. Corriger ces trois causes suffit à corriger les cinq
défauts : ce n'est pas cinq correctifs séparés à écrire.

Ce diagnostic recoupe exactement les symptômes du brief de départ : deux sub-agents qui semblent se
renvoyer la balle, c'est le conflit sur `REVIEW` ; l'orchestration qui boucle, c'est la limite non
lue et la fin de flux cassée ; un sub-agent qui fait le travail d'un autre, c'est encore `REVIEW` ;
le flux qui ne respecte plus la spécification, c'est la combinaison des trois.

---

## 2. Les rôles cibles

```mermaid
%%{init: {"theme": "base", "themeVariables": {"fontFamily": "Helvetica", "fontSize": "15px", "primaryColor": "#FFFFFF", "lineColor": "#64748B", "edgeLabelBackground": "#FFFFFF"}, "flowchart": {"wrappingWidth": 260, "curve": "basis"}}}%%
flowchart TD
  CHEF("Le chef<br/>ne produit jamais rien<br/>confie, réceptionne, fait avancer"):::pilot

  subgraph SG_POSTES["Quatre postes, chacun son étape"]
    direction LR
    RES("Researcher<br/>étape : recherche<br/>lit : le sujet<br/>écrit : la recherche<br/>ne fait jamais : rédiger, relire, clore"):::chaine
    WRI("Writer<br/>étape : rédaction<br/>lit : la recherche<br/>écrit : le brouillon<br/>ne fait jamais : se relire"):::chaine
    REV("Reviewer<br/>étape : relecture<br/>lit : le brouillon<br/>écrit : la version corrigée<br/>ne fait jamais : renvoyer au writer"):::chaine
    FIN("Finalizer<br/>étape : clôture<br/>lit : la version corrigée<br/>écrit : le résultat final<br/>seul à déclarer le travail fait"):::chaine
  end

  CHEF <-- "confie l'étape / rend la main" --> RES
  CHEF <-- "confie l'étape / rend la main" --> WRI
  CHEF <-- "confie l'étape / rend la main" --> REV
  CHEF <-- "confie l'étape / rend la main" --> FIN

  subgraph SG_REGLES["Quatre règles qui tiennent la frontière"]
    direction LR
    R1("Une étape,<br/>un seul agent responsable"):::gate
    R2("Un résultat,<br/>un seul propriétaire qui l'écrit"):::gate
    R3("Un rôle déclaré<br/>à un seul endroit du code"):::gate
    R4("Aucun transfert<br/>d'un agent à un autre"):::gate
  end

  CHEF --- SG_REGLES

  subgraph SG_LEGEND["Légende"]
    direction LR
    LPILOT("le chef"):::pilot
    LCHAINE("agent et son étape"):::chaine
    LGATE("règle de frontière"):::gate
  end

  classDef besoin fill:#E8F1FC,stroke:#2563EB,color:#1E3A5F
  classDef v1 fill:#EEF1F5,stroke:#64748B,color:#334155
  classDef chaine fill:#F1ECFB,stroke:#7C3AED,color:#4C1D95
  classDef gate fill:#FEF6E7,stroke:#D97706,color:#7C4A03
  classDef data fill:#E9F8F0,stroke:#059669,color:#065F46
  classDef obs fill:#E7F8FA,stroke:#0891B2,color:#164E5C
  classDef pilot fill:#FDECF3,stroke:#DB2777,color:#831843

  style SG_POSTES fill:none,stroke:#D1D5DB,stroke-dasharray: 4 4
  style SG_REGLES fill:none,stroke:#D1D5DB,stroke-dasharray: 4 4
  style SG_LEGEND fill:none,stroke:#D1D5DB,stroke-dasharray: 4 4
```

Quatre règles ferment les frontières entre agents : une étape n'a qu'un seul agent responsable ; un
résultat n'a qu'un seul propriétaire qui a le droit de l'écrire ; un agent refuse toute étape qui
n'est pas la sienne, sans exception ; le chef ne produit rien, il confie l'étape, réceptionne le
résultat attendu, et fait avancer.

Le `Reviewer` produit lui-même la version corrigée (`reviewer.py`). Le flux ne revient jamais au
`Writer` après relecture : la spécification demande une relecture *et* des corrections, pas un
simple signalement.

---

## 3. Le flux cible

```mermaid
%%{init: {"theme": "base", "themeVariables": {"fontFamily": "Helvetica", "fontSize": "15px", "primaryColor": "#FFFFFF", "lineColor": "#64748B", "edgeLabelBackground": "#FFFFFF"}, "flowchart": {"wrappingWidth": 260, "curve": "basis"}}}%%
flowchart TD
  DEM("Demande<br/>sujet + liste d'étapes"):::besoin --> A

  subgraph SG_A["A · Avant de démarrer"]
    A{{"Le chef vérifie la demande<br/>sujet, libellés, doublons,<br/>clôture en dernier, équipe complète"}}:::pilot
  end

  A -- "invalide" --> X1("Arrêt<br/>demande invalide + motif"):::gate
  A -- "valide" --> B

  subgraph SG_B["B · Pendant, une étape à la fois"]
    B{{"reste-t-il<br/>une étape ?"}}:::pilot
    B -- "oui" --> CONFIE("le chef confie l'étape<br/>à son unique propriétaire"):::chaine
    CONFIE --> AGENT("l'agent lit ce qu'il faut,<br/>écrit son résultat,<br/>rend la main"):::chaine
    AGENT --> JOURNAL[("journal : agent,<br/>étape, action")]:::obs
    JOURNAL --> RECEP{{"le chef réceptionne<br/>le bon résultat est-il écrit,<br/>et rien d'autre ?"}}:::pilot
    RECEP -- "conforme" --> SUIVANT("avance à l'étape suivante"):::data
    SUIVANT --> B
  end

  RECEP -- "hors rôle" --> X2("Arrêt<br/>rôle non respecté"):::gate
  RECEP -- "budget dépassé" --> X3("Arrêt<br/>budget dépassé"):::gate
  RECEP -- "non conforme, 1re fois :<br/>une seule relance" --> CONFIE
  RECEP -- "non conforme, 2e fois" --> X4("Arrêt<br/>réception refusée"):::gate
  CONFIE -- "limite d'étapes atteinte" --> X5("Arrêt<br/>limite atteinte"):::gate

  B -- "non" --> C

  subgraph SG_C["C · À la fin"]
    C{{"le travail a-t-il été<br/>clos par le bon agent ?"}}:::pilot
  end

  C -- "oui" --> FIN("Fin normale<br/>le chef répond terminé"):::data
  C -- "non" --> X6("Arrêt<br/>clôture manquante"):::gate

  subgraph SG_LEGEND["Légende"]
    direction LR
    LBESOIN("demande d'entrée"):::besoin
    LPILOT("vérification / décision du chef"):::pilot
    LCHAINE("travail confié à l'agent"):::chaine
    LOBS("journal"):::obs
    LDATA("progression acceptée"):::data
    LGATE("arrêt, avec son code"):::gate
  end

  classDef besoin fill:#E8F1FC,stroke:#2563EB,color:#1E3A5F
  classDef v1 fill:#EEF1F5,stroke:#64748B,color:#334155
  classDef chaine fill:#F1ECFB,stroke:#7C3AED,color:#4C1D95
  classDef gate fill:#FEF6E7,stroke:#D97706,color:#7C4A03
  classDef data fill:#E9F8F0,stroke:#059669,color:#065F46
  classDef obs fill:#E7F8FA,stroke:#0891B2,color:#164E5C
  classDef pilot fill:#FDECF3,stroke:#DB2777,color:#831843

  style SG_A fill:none,stroke:#D1D5DB,stroke-dasharray: 4 4
  style SG_B fill:none,stroke:#D1D5DB,stroke-dasharray: 4 4
  style SG_C fill:none,stroke:#D1D5DB,stroke-dasharray: 4 4
  style SG_LEGEND fill:none,stroke:#D1D5DB,stroke-dasharray: 4 4
```

Le flux se déroule en trois temps. Avant de démarrer, le chef vérifie la demande (étapes valides,
pas de doublon, entrées présentes) ; une demande invalide ne démarre pas. Pendant, une étape à la
fois, dans l'ordre demandé, avec un budget de jetons par agent. À la fin, seul le `Finalizer` fait
passer le statut à `done`.

La règle qui ferme la boucle observée dans l'état actuel : une étape qui échoue ne revient jamais
vers le même agent. Soit le flux avance, soit il s'arrête en `aborted` avec un code précis
(`role_violation`, `budget_exceeded`, `reception_refused`, `step_limit_reached`,
`missing_closure`).

---

## 4. Un parcours complet

La demande contient quatre étapes : `RESEARCH`, `DRAFT`, `REVIEW`, `FINALIZE`.

1. Le chef vérifie la demande : quatre étapes valides, pas de doublon, entrées présentes. Elle
   passe.
2. `RESEARCH` part vers le `Researcher`, qui écrit l'artefact `research`. Le chef réceptionne, fait
   avancer.
3. `DRAFT` part vers le `Writer`, qui lit `research` et écrit `draft`. Le chef réceptionne, fait
   avancer.
4. `REVIEW` part vers le `Reviewer`, pas vers le `Writer`. Il lit `draft`, écrit `review`. Le chef
   réceptionne, fait avancer.
5. `FINALIZE` part vers le `Finalizer`, qui construit `final` à partir de `review` (`finalizer.py`),
   et passe le statut à `done`. Le chef répond `END`.

À aucun moment un agent ne reçoit deux fois la même étape (la seule exception serait une relance
unique après un résultat non conforme, qui n'arrive pas dans ce scénario), et à aucun moment un artefact n'est écrit
par quelqu'un d'autre que son propriétaire. C'est ce parcours exact que les tests reproduisent pour
vérifier que la correction tient.

Un second scénario existe, plus court : `RESEARCH` puis `FINALIZE`, sans rédaction ni relecture.
Le `Researcher` écrit `research`, puis le `Finalizer` clôt directement à partir de cet artefact,
faute de version rédigée ou corrigée. Ce cas confirme que le finalizer ne dépend pas d'un chemin
figé à quatre étapes : il construit son résultat sur l'artefact de contenu le plus abouti
disponible, la version corrigée, sinon le brouillon, sinon la recherche brute.

---

## 5. Comment la correction se prouve

Un test qui prouve une correction doit remplir trois conditions : provoquer la situation qu'il
vise, au lieu d'attendre qu'elle survienne ; l'observer dans une trace exploitable, comme le
journal des agents ou le registre d'écriture des artefacts ; et échouer précisément pour la raison
qu'il cible, pas pour une erreur annexe.

Le protocole retenu réintroduit chaque défaut un par un, une fois le code corrigé. À chaque
réintroduction, au moins un test doit échouer sur sa propre vérification, avec un message qui nomme
le défaut. Le défaut retiré, tout doit repasser. Un défaut qu'aucun test n'attrape est un trou de la
suite, à combler avant de conclure. Cette grille couvre les douze défauts relevés sur les trois
points du diagnostic, plus le risque de relance sans fin.

---

## Annexe · Fichiers sources

Code étudié : dépôt `kaldera-team-ko`, commit `37c2cb3`. Fichiers cités dans cette présentation :

- `src/kaldera/steps.py` — étapes métier (`Step`) et résolution des libellés de scénario
- `src/kaldera/orchestrator.py` — table de routage `STEP_TO_AGENT` et fonction `route`
- `src/kaldera/runner.py` — boucle d'exécution, limite d'étapes (`HARD_CAP`)
- `src/kaldera/agents/base.py` — classe de base `Agent`, `accepts`, `run`
- `src/kaldera/agents/researcher.py` — agent `Researcher`
- `src/kaldera/agents/writer.py` — agent `Writer`
- `src/kaldera/agents/reviewer.py` — agent `Reviewer`
- `src/kaldera/agents/finalizer.py` — agent `Finalizer`
