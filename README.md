# Kaldera Team KO

Orchestrateur d'une équipe d'agents LLM (`researcher`, `writer`, `reviewer`,
`finalizer`) coordonnés par un superviseur, pour traiter une demande métier
étape par étape jusqu'à un résultat final.

## Features

- Superviseur qui confie chaque étape à l'agent responsable via une table de routage.
- Sous-agents spécialisés, chacun avec un périmètre de rôle explicite.
- Exécution déterministe et rejouable à partir de scénarios JSON.
- Garde-fous d'exécution : budget d'étapes, budget de tokens par agent, journalisation traçable.
- Chemin d'exécution « live » branché sur Azure AI (Kimi-K2.6) via LangChain + LangGraph.

## Stack

- Python 3.11 (uv)
- LangChain / langchain-core 0.3.x
- langchain-azure-ai 0.1.x (Kimi-K2.6)
- LangGraph 0.2.x
- pytest 8.x

## Setup

```bash
make install              # uv sync — installe les dépendances
cp .env.example .env      # puis renseigner les clés Azure AI
make up                   # docker compose up -d (conteneur d'exécution)
make test                 # lance la suite de tests
```

Sans Docker, `make install` puis `make test` suffisent : le cœur de
l'orchestration tourne sans dépendance réseau.

## Layout

- `src/kaldera/` — superviseur, sous-agents, état partagé, garde-fous d'exécution
- `src/kaldera/agents/` — `researcher`, `writer`, `reviewer`, `finalizer`
- `src/kaldera/graph.py`, `src/kaldera/llm.py` — chemin d'exécution branché sur le LLM
- `specs/flow_spec.md` — spécification du flux métier attendu
- `scenarios/scenarios_test.json` — scénarios d'exécution rejouables
- `tests/` — tests unitaires et d'intégration
- `docker-compose.yml`, `Dockerfile` — service d'exécution conteneurisé

## Useful commands

```bash
make fmt        # ruff format + autofix
make lint       # ruff check
make typecheck  # mypy
make down       # stoppe le service docker
```

## Known issues

- L'orchestration et le routage présentent encore des comportements à fiabiliser
  sur certains scénarios ; le rejeu via `scenarios/` reste la référence de comportement.
- Les garde-fous d'exécution (budget d'étapes, budget de tokens, journalisation)
  demandent une passe de validation supplémentaire avant un usage réel.

## License

Usage interne — tous droits réservés.
