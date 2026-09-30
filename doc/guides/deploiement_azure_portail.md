# Déployer Kaldera sur Azure — pas à pas dans le portail

Guide pour un compte Azure déjà actif (abonnement avec carte liée ou crédits). Les noms de menus
sont ceux du portail à la date de rédaction (30/09/2026) ; l'interface Azure change de temps en
temps, mais les ressources et leur logique restent les mêmes si un libellé a bougé.

Ressources créées : un groupe de ressources, un environnement Container Apps, un Container App.
Tout se fait en une seule fois via l'assistant de création du Container App.

## 1. Groupe de ressources

1. Aller sur [portal.azure.com](https://portal.azure.com).
2. Barre de recherche en haut → taper « Groupes de ressources » → ouvrir.
3. **+ Créer**.
4. Abonnement : le tien. Nom du groupe de ressources : `rg-kaldera-demo`. Région : une région
   proche (ex. « France Central »).
5. **Vérifier + créer**, puis **Créer**.

## 2. Container App (et son environnement, créé au même moment)

1. Barre de recherche → « Container Apps » → ouvrir le service (pas une ressource existante).
2. **+ Créer** → **Container App**.
3. Onglet **Bases (Basics)** :
   - Abonnement : le tien. Groupe de ressources : `rg-kaldera-demo`.
   - Nom du Container App : `kaldera-webapp-demo`.
   - Région : la même que le groupe de ressources.
   - Environnement Container Apps : **Créer nouveau** → nom `env-kaldera-demo` → Créer (ferme la
     sous-fenêtre, revient à l'assistant).
4. Onglet **Conteneur (Container)** :
   - Décocher/désélectionner l'option d'image de démonstration (« Utiliser une image
     d'exemple ») si elle est cochée par défaut.
   - Nom du conteneur : `kaldera-webapp`.
   - Source de l'image : **Autres registres de conteneurs** (ou « Docker Hub ou autre registre »
     selon le libellé affiché).
   - URL de l'image : `ghcr.io/sofiane-git/kaldera-webapp:latest`.
   - Type d'authentification du registre : si le package `ghcr.io` a été rendu **public** (voir
     Task 8 du plan, dernière étape), choisir « Aucune » / laisser vide — pas d'identifiant
     nécessaire. S'il reste privé, il faudra un identifiant de registre (non couvert ici : rendre
     le package public évite cette complication).
   - Ressources : 0.25 vCPU / 0.5 Gi suffisent largement pour cette démo.
5. Onglet **Ingress** :
   - Activer l'ingress : **Activé**.
   - Trafic accepté : **Anywhere / N'importe où** (ingress externe).
   - Port cible (Target port) : `7860`.
6. Onglet **Mise à l'échelle (Scale)** (si présent séparément, sinon dans l'onglet Bases) :
   - Nombre de réplicas minimal : `0` (scale-to-zero — c'est ce qui garde le coût quasi nul entre
     deux démos).
   - Nombre de réplicas maximal : `1`.
7. **Vérifier + créer**, vérifier qu'aucune erreur n'est signalée, puis **Créer**. La création
   prend une à deux minutes.

## 3. Ajouter les secrets Azure AI

Une fois la ressource créée, l'ouvrir (« Accéder à la ressource » ou la retrouver dans le groupe
de ressources `rg-kaldera-demo`).

1. Menu de gauche → **Secrets** (sous la section Paramètres/Settings).
2. **+ Ajouter** trois fois, pour créer :
   - `azure-ai-endpoint` → valeur : l'URL de l'endpoint Azure AI (celle de ton fichier `.env`
     local, `AZURE_AI_ENDPOINT`).
   - `azure-ai-api-key` → valeur : la clé (`AZURE_AI_API_KEY`).
   - `azure-ai-model` → valeur : le nom du modèle (`AZURE_AI_MODEL`).
3. Menu de gauche → **Variables d'environnement et conteneurs** (« Containers » → onglet
   « Variables d'environnement »).
4. Ajouter trois variables, chacune en mode **Référence à un secret** :
   - `AZURE_AI_ENDPOINT` → référence le secret `azure-ai-endpoint`.
   - `AZURE_AI_API_KEY` → référence le secret `azure-ai-api-key`.
   - `AZURE_AI_MODEL` → référence le secret `azure-ai-model`.
5. **Enregistrer** (ou **Créer**) : ceci déclenche une nouvelle révision du Container App, qui
   redémarre avec les variables en place — normal, attendre que le statut redevienne « En cours
   d'exécution » (30 secondes à 1 minute).

## 4. Retrouver l'URL publique

Menu de gauche → **Vue d'ensemble (Overview)** → champ **URL de l'application (Application
URL)**. C'est l'adresse `https://kaldera-webapp-demo.<suffixe-aléatoire>.<région>.azurecontainerapps.io`
à ouvrir dans un navigateur et à projeter en classe.

## 5. Lire les logs en cas de souci

Menu de gauche → **Flux de journal (Log stream)** : affiche la sortie du conteneur en direct (ce
que `uv run python -m kaldera.webapp.app` écrit sur la sortie standard). Utile si la GUI ne
répond pas ou si un déploiement récent a cassé quelque chose.

## 6. Rappel : démarrage à froid

Le scale-to-zero veut dire que si personne n'a utilisé la GUI depuis un moment, le conteneur est
arrêté. La première requête après une inactivité prend quelques secondes de plus (le temps que le
conteneur redémarre). **Avant de présenter en classe, ouvrir l'URL une minute à l'avance** pour
« réveiller » le conteneur.
