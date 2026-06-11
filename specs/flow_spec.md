# Spécification du flux — équipe Kaldera

L'équipe traite une demande en enchaînant des étapes dans l'ordre fourni par la
demande. Le superviseur lit l'étape courante et la confie à l'agent responsable.

## Étapes métier

| Étape      | Description                                              |
|------------|----------------------------------------------------------|
| `RESEARCH` | Collecte des informations sur le sujet.                  |
| `DRAFT`    | Rédaction d'un premier jet à partir de la recherche.     |
| `REVIEW`   | Relecture et corrections du jet.                         |
| `FINALIZE` | Assemblage du résultat final et clôture du traitement.   |

## Rôles et frontières

- `researcher` — traite uniquement `RESEARCH`. Ne traite pas `DRAFT`, `REVIEW`, `FINALIZE`.
- `writer` — traite uniquement `DRAFT`. Ne traite pas la recherche ni la relecture.
- `reviewer` — traite uniquement `REVIEW`. Produit l'artefact `review`.
- `finalizer` — traite uniquement `FINALIZE`, assemble l'artefact `final` et clôt le flux.

Chaque agent refuse toute étape hors de son périmètre.

## Orchestration

- Le superviseur confie l'étape courante à l'agent désigné par la table de routage.
- Une étape ne peut être confiée qu'à un seul agent responsable.
- Quand toutes les étapes requises sont traitées, le flux se termine explicitement (`END`).
- Le flux ne doit jamais dépasser le budget d'étapes (`max_steps`) de la demande.

## Contraintes d'exécution

- Chaque agent dispose d'un budget de tokens par exécution ; un dépassement
  interrompt l'agent (`BudgetExceeded`).
- Chaque action est journalisée avec l'identifiant de l'agent qui l'a réalisée,
  afin de tracer qui a fait quoi.
