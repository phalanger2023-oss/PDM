# Mettre Personal Document Modifier en ligne (sur le même serveur que vos autres sites)

Ce site suit la **même architecture que `recettes-app`** : un projet Docker Compose, branché sur Traefik
(réseau `traefik-public`), avec un certificat HTTPS Let's Encrypt automatique. Il n'a pas besoin de base de
données : ses documents sont gardés dans un volume Docker (`annotateur_pdf_documents`).

Adresse prévue : **https://pdm.louisharicuisine.com** (modifiable dans `.env`).

## Comment la connexion fonctionne

Le site a **sa propre page de connexion** (un seul compte). Quand vous cochez « Rester connecté », le
navigateur garde un cookie pendant **90 jours** et il se prolonge à chaque visite : vous ne retapez le mot de
passe que si vous restez 90 jours sans venir, si vous cliquez sur « Se déconnecter » ou si vous changez de
mot de passe.

Ce que le site fait pour rester sûr :
- le mot de passe n'est stocké nulle part, seulement sa version hachée (illisible) dans `.env` ;
- le cookie est invisible pour le JavaScript, envoyé uniquement en HTTPS et jamais par un autre site ;
- après 5 essais ratés, l'adresse est bloquée 15 minutes ;
- **le site refuse de démarrer en production sans mot de passe** : il ne peut pas être public par erreur.

> Sur un ordinateur partagé, décochez « Rester connecté » : la connexion s'arrête alors à la fermeture du
> navigateur. Si un appareil est perdu, changez le mot de passe (étape 1) : cela déconnecte tout le monde.

## Ce qu'il faut avoir au départ

- Le serveur où tourne déjà Traefik (le même que pour `recettes-app`), avec le réseau Docker `traefik-public`.
- Un accès SSH à ce serveur (le même que d'habitude).
- Docker et Docker Compose sur le serveur (déjà le cas si `recettes-app` y tourne).

## Étape 1 — Créer l'identifiant et le mot de passe (sur votre PC)

Dans le dossier du projet, pour fabriquer les réglages de connexion (le mot de passe ne s'affiche pas quand
vous le tapez) :

```bash
.venv\Scripts\python.exe outils\mot_de_passe.py
```

Choisissez un mot de passe **d'au moins 12 caractères**, difficile à deviner et utilisé nulle part ailleurs.
L'outil affiche **trois lignes** (`AUTH_USER`, `AUTH_HASH`, `SECRET_KEY`) : gardez-les sous la main pour l'étape 4.
Ce sont des secrets : ne les envoyez à personne.

## Étape 2 — Ajouter l'adresse dans le DNS

Chez votre gestionnaire de domaine, créez pour `pdm.louisharicuisine.com` le **même enregistrement** que
celui de `dev.louisharicuisine.com` (type A, vers l'adresse IP de votre serveur). Si vous avez déjà un
enregistrement « joker » (`*.louisharicuisine.com`), il n'y a rien à faire.

## Étape 3 — Envoyer le site sur le serveur

Sur votre PC, créez une archive **sans** le dossier `.venv` ni vos documents :

```bash
tar --exclude=.venv --exclude="Mes documents" --exclude=uploads --exclude=__pycache__ --exclude=.env -czf annotateur-pdf.tgz .
```

Envoyez-la au serveur (remplacez `utilisateur` et `serveur` par vos valeurs habituelles) :

```bash
scp annotateur-pdf.tgz utilisateur@serveur:~/
```

Sur le serveur, dépliez-la dans un dossier à part, à côté de `recettes-app` :

```bash
mkdir -p ~/annotateur-pdf && tar -xzf annotateur-pdf.tgz -C ~/annotateur-pdf && cd ~/annotateur-pdf
```

## Étape 4 — Réglages et démarrage (sur le serveur)

```bash
cp .env.example .env
nano .env
```

Dans `.env`, vérifiez `PDF_HOST` et **remplacez les trois lignes `AUTH_USER`, `AUTH_HASH` et `SECRET_KEY`** par
celles de l'étape 1 (gardez les apostrophes autour de `AUTH_HASH`). Enregistrez (Ctrl+O, Entrée) puis quittez
(Ctrl+X). Protégez ensuite le fichier :

```bash
chmod 600 .env
```

Démarrez le site (la première fois, la construction prend quelques minutes) :

```bash
docker compose up -d --build
```

## Étape 5 — Vérifier

```bash
docker compose ps
```

Le service `pdf` doit passer à l'état **healthy** après quelques secondes. Puis ouvrez
https://pdm.louisharicuisine.com : la page de connexion s'affiche. Connectez-vous en laissant « Rester connecté »
coché, fermez le navigateur, rouvrez le site : vous devez arriver directement sur vos documents.
Le certificat HTTPS peut mettre une minute à apparaître la toute première fois.

En cas de souci, regardez les journaux :

```bash
docker compose logs -f pdf
```

## Au quotidien

**Mettre à jour le site** après des changements sur votre PC : refaites l'étape 3 (archive, envoi, dépliage
dans le même dossier) puis :

```bash
docker compose up -d --build
```

Vos documents ne sont pas touchés (ils sont dans le volume, pas dans le dossier du site) et vous restez connecté.

**Changer le mot de passe** : refaites l'étape 1, remplacez les trois lignes dans `.env`, puis :

```bash
docker compose up -d
```

**Sauvegarder vos documents** (les PDF d'origine, et vos modifications en cours, qui sont des « brouillons »
enregistrés automatiquement dans le dossier caché `.brouillons`) :

```bash
docker run --rm -v annotateur_pdf_documents:/donnees -v "$PWD":/sauvegarde alpine tar czf /sauvegarde/pdf-documents.tgz -C /donnees .
```

**Arrêter le site** (les documents restent) :

```bash
docker compose down
```

## Si quelque chose ne marche pas

- **Le conteneur redémarre en boucle, journaux : « AUTH_USER, AUTH_HASH et SECRET_KEY sont obligatoires »** :
  le fichier `.env` est incomplet ou n'est pas dans le même dossier que `docker-compose.yml`.
- **« Identifiant ou mot de passe incorrect » alors qu'ils sont bons** : les apostrophes autour de `AUTH_HASH`
  ont disparu, ce qui abîme les signes `$`. Recopiez la ligne telle qu'affichée par l'outil.
- **Vous devez vous reconnecter à chaque visite** : le navigateur bloque les cookies pour ce site, ou « Rester
  connecté » est décoché, ou la `SECRET_KEY` change à chaque démarrage (vérifiez qu'elle est bien dans `.env`).
- **Page « 404 » ou site introuvable** : le DNS n'est pas encore à jour, ou le réseau `traefik-public` n'est pas
  celui de Traefik. Vérifiez avec `docker network ls`.
- **Erreur « security-headers » dans les journaux de Traefik** : ce réglage existe sur votre serveur pour
  `recettes-app`. S'il manque, retirez `security-headers@file` de la ligne `middlewares` dans `docker-compose.yml`.
- **Le site s'affiche mais les PDF ne se dessinent pas** : si vos en-têtes de sécurité contiennent une politique
  stricte (CSP), autorisez au minimum `script-src 'self'`, `worker-src 'self' blob:`, `img-src 'self' data: blob:`,
  `style-src 'self' 'unsafe-inline'` et `connect-src 'self'`.
- **Fichier de plus de 100 Mo refusé** : c'est la limite du site (`MAX_CONTENT_LENGTH` dans `app.py`).

## Ajouter d'autres sites sur le même modèle

Chaque site a son propre dossier et son propre `docker-compose.yml`, avec :

1. le réseau externe `traefik-public` ;
2. des labels Traefik **dont le nom de routeur est unique** (ici `pdf`, ailleurs `recettes-dev-web`, etc.) ;
3. une règle `Host(...)` différente par site (un sous-domaine chacun) ;
4. `loadbalancer.server.port` = le port interne du conteneur ;
5. une protection pour tout site qui n'a pas sa propre connexion.

Aucun port n'est ouvert sur le serveur par ce site : tout passe par Traefik.
