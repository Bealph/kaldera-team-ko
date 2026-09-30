# Connecter GitHub Actions à Azure — sans mot de passe (OIDC), pas à pas

Suivre ce guide **après** `deploiement_azure_portail.md` (le groupe de ressources
`rg-kaldera-demo` doit déjà exister). Objectif : que la CI GitHub Actions puisse déployer sur
Azure sans qu'aucun secret longue durée (mot de passe, clé, JSON de credentials) ne soit stocké
dans GitHub. GitHub prouve son identité à chaque exécution via un jeton signé (OIDC), Azure le
vérifie, et n'accorde l'accès qu'à la branche `main` de ce dépôt précis.

## 1. Créer l'inscription d'application (App Registration)

1. [portal.azure.com](https://portal.azure.com) → barre de recherche → « Microsoft Entra ID »
   (anciennement Azure Active Directory) → ouvrir.
2. Menu de gauche → **Inscriptions d'applications (App registrations)**.
3. **+ Nouvelle inscription**.
4. Nom : `kaldera-github-actions`. Types de comptes pris en charge : « Comptes dans cet annuaire
   organisationnel uniquement ». URI de redirection : laisser vide.
5. **Inscrire**.
6. Sur la page qui s'ouvre (Vue d'ensemble), noter deux valeurs affichées en haut :
   - **ID d'application (client)** → ce sera `AZURE_CLIENT_ID`.
   - **ID d'annuaire (locataire)** → ce sera `AZURE_TENANT_ID`.

## 2. Ajouter l'identité fédérée (Federated credential)

1. Toujours sur cette App Registration → menu de gauche → **Certificats et secrets**.
2. Onglet **Informations d'identification fédérées (Federated credentials)**.
3. **+ Ajouter des informations d'identification**.
4. Scénario : **GitHub Actions déployant des ressources Azure**.
5. Organisation : `sofiane-git`. Dépôt : `kaldera-team-ko`.
   Type d'entité : **Branch**. Nom de la branche : `main`.
6. Nom de l'information d'identification : `kaldera-main-deploy`.
7. **Ajouter**.

Ceci autorise *uniquement* les workflows qui s'exécutent sur la branche `main` de ce dépôt précis
à s'authentifier en tant que cette App Registration — pas les PR, pas les autres branches, pas
les autres dépôts.

## 3. Donner à l'App Registration le droit de déployer

1. Aller sur le groupe de ressources `rg-kaldera-demo` (barre de recherche → « Groupes de
   ressources » → l'ouvrir).
2. Menu de gauche → **Contrôle d'accès (IAM)**.
3. **+ Ajouter** → **Ajouter une attribution de rôle**.
4. Rôle : **Contributor** (Contributeur) → Suivant.
5. Attribuer l'accès à : **Utilisateur, groupe ou principal de service**.
6. **+ Sélectionner des membres** → rechercher `kaldera-github-actions` (le nom donné à l'étape
   1) → le sélectionner.
7. **Vérifier + attribuer**.

## 4. Récupérer l'ID d'abonnement

1. Barre de recherche → « Abonnements (Subscriptions) » → ouvrir ton abonnement.
2. Copier la valeur **ID abonnement (Subscription ID)** → ce sera `AZURE_SUBSCRIPTION_ID`.

## 5. Ajouter les 3 secrets dans GitHub

1. Sur github.com, ouvrir le dépôt `kaldera-team-ko` → **Settings** → **Secrets and variables**
   → **Actions**.
2. **New repository secret**, trois fois :
   - `AZURE_CLIENT_ID` → la valeur notée à l'étape 1.
   - `AZURE_TENANT_ID` → la valeur notée à l'étape 1.
   - `AZURE_SUBSCRIPTION_ID` → la valeur notée à l'étape 4.

Aucun de ces trois secrets n'est un mot de passe : ce sont des identifiants publics (l'App
Registration ne peut rien faire sans le jeton OIDC signé que GitHub génère à chaque run, jamais
stocké nulle part).

## 6. Rendre l'image ghcr.io publique (évite un secret de registre en plus)

Une fois que le workflow `.github/workflows/ci-cd.yml` a tourné au moins une fois avec succès sur
`main` (il aura poussé une image vers `ghcr.io`) :

1. Sur github.com → compte `sofiane-git` → onglet **Packages**.
2. Ouvrir le package `kaldera-webapp`.
3. **Package settings** (en bas de la page du package).
4. **Change visibility** → **Public** → confirmer en tapant le nom du package.

Ceci évite d'avoir à configurer un identifiant de registre côté Container App (Task 7, étape 2) :
une image publique se tire sans authentification.

## Vérification finale

Faire un commit vide sur `main` (ou merger une PR) pour déclencher le workflow, puis :
github.com → onglet **Actions** du dépôt → ouvrir le run le plus récent → vérifier que le job
`deploy` passe au vert. En cas d'échec sur l'étape « Connexion à Azure », revérifier que les 3
secrets GitHub (étape 5) correspondent exactement aux valeurs des étapes 1 et 4, et que
l'identité fédérée (étape 2) cible bien `refs/heads/main` de ce dépôt.
