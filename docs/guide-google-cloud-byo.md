# Guide : créer tes identifiants Google (BYO credentials) - gratuit, ~10 min

> But : obtenir un `client_id` + `client_secret` de type "Application de bureau" pour que Maily se connecte à tes boîtes Gmail via l'API Gmail. C'est **gratuit**, sans carte bancaire, **sans vérification Google** (usage personnel). Tu fais ça **une seule fois** ; ensuite tu connecteras chaque boîte d'un clic dans l'app.
>
> ⚠️ Google a récemment renommé cet espace en **"Google Auth Platform"** (au lieu de l'ancien "OAuth consent screen"). Ce guide suit la **nouvelle interface** (onglets : Overview, Branding, Audience, Clients, Data Access). Les libellés exacts peuvent varier légèrement ; la logique reste la même. Tu peux basculer l'interface en anglais (menu en haut à droite) si tes captures ne correspondent pas aux miennes.

---

## 1. Créer un projet Google Cloud (gratuit)

> **Quel compte utiliser ?** Celui que tu veux, ça n'a pas d'importance. Le compte qui crée le projet en est juste le **propriétaire** (l'admin du projet Cloud) ; ça ne limite **pas** quelles boîtes tu pourras connecter ensuite (c'est le choix **External**, plus bas, qui ouvre l'accès à tous tes comptes). Tu peux très bien tout faire depuis `you@example.com`.

1. Va sur https://console.cloud.google.com/ et connecte-toi avec **le compte de ton choix** (par ex. `you@example.com`).
2. En haut, sélecteur de projet → **New project / Nouveau projet**.
3. **Project name** : ce que tu veux (par ex. `Maily`).
4. **Organization / Parent** :
   - Si tu es connecté avec un compte **Workspace** (`thanaelfontaine.eu` ou `example.org`, tous deux dans la même org), Google t'**imposera** de choisir ton organisation (affichée `example.org`). C'est **normal**, tu n'as pas le choix, et ça ne gêne rien.
   - Si tu utilisais un **Gmail perso** (`@gmail.com`), tu pourrais choisir **No organization**. C'est bien aussi.
   - En clair : **aucune obligation d'utiliser un compte précis** ; l'organisation qui s'affiche dépend juste du compte avec lequel tu es connecté.
5. **Create**. Puis assure-toi que ce projet est bien sélectionné en haut.

## 2. Activer l'API Gmail

1. Menu ☰ → **APIs & Services** → **Library** (Bibliothèque).
2. Cherche **Gmail API** → clique → **Enable** (Activer).

---

## 3. Google Auth Platform : l'assistant "Get started"

Va dans Menu ☰ → **APIs & Services** → **OAuth consent screen** (qui ouvre désormais **Google Auth Platform**).

### 3.1 Si tu vois "Google Auth Platform not configured yet"
Clique **Get started**. Un petit assistant en 4 étapes s'ouvre :

1. **App Information**
   - **App name** : `Maily`
   - **User support email** : choisis **un de tes emails** (n'importe lequel, c'est juste un contact affiché).
   - **Next**.
2. **Audience** ← ÉTAPE CLÉ
   - Choisis **External** (Externe). **Surtout pas Internal.**
   - Pourquoi : *Internal* ne laisserait se connecter que les comptes de l'org `example.org`. *External* laisse se connecter **tous** tes comptes, y compris ton **Gmail perso** (qui n'est pas dans l'org) et `thanaelfontaine.eu`.
   - **Next**.
3. **Contact Information**
   - Mets ton email. **Next**.
4. **Finish**
   - Coche l'acceptation de la *Google API Services User Data Policy*.
   - **Continue / Create**.

### 3.2 Si l'assistant est déjà passé (tu vois directement les onglets)
Pas grave, on va régler chaque onglet ci-dessous (Branding, Audience, Data Access, Clients).

---

## 4. Onglet "Branding" (rapide)

Menu de gauche → **Branding**.
- **App name** : `Maily` (déjà rempli sûrement).
- **User support email** : ton email.
- Logo, domaines autorisés, liens : **facultatifs**, laisse vide.
- **Save**.

---

## 5. Onglet "Audience" : type + test users + passage en Production

Menu de gauche → **Audience**.

1. **User type** : vérifie que c'est bien **External**. (S'il est sur Internal, repasse-le en External.)
2. **Test users** : clique **Add users** et ajoute **toutes les adresses que tu veux utiliser dans Maily** (quel que soit le compte propriétaire du projet), par exemple :
   - `you@example.com`
   - `work@example.com`
   - ton Gmail perso
   - toute autre boîte à connecter
   - **Save**.
   - *(Après passage en Production à l'étape suivante, cette liste devient facultative ; mais l'ajouter ne coûte rien.)*
3. **Publishing status** : tu verras "Testing".
   - Clique **Publish app** → **Confirm**. Le statut passe à **In production**.
   - Pourquoi c'est important : en "Testing", les connexions **expirent au bout de 7 jours** (tu devrais te reconnecter chaque semaine). En "In production", c'est **durable**.
   - Pour un usage perso (< ~100 utilisateurs), **aucune vérification n'est requise**. Si Google mentionne la vérification, tu peux l'ignorer et rester non vérifié (tu verras juste un écran d'avertissement à la 1re connexion, voir §8).

> Si tu préfères ne pas publier tout de suite : tu peux rester en "Testing" pour un premier test, mais prévois de re-cliquer "Autoriser" toutes les semaines. Le passage en Production est recommandé.

---

## 6. Onglet "Data Access" : les scopes (facultatif mais propre)

Menu de gauche → **Data Access** → **Add or remove scopes**.

- Dans la barre de filtre, cherche et coche :
  - `https://www.googleapis.com/auth/gmail.modify` (lire, ranger, libellés, corbeille)
  - `https://www.googleapis.com/auth/gmail.send` (envoyer)
- **Update** puis **Save**.

> Ces scopes apparaissent comme **restricted/sensitive** : normal. Pour un usage perso non vérifié, ça reste gratuit et fonctionnel (avertissement à la 1re connexion, §8). Cette étape est **facultative** : si tu la sautes, l'app demandera de toute façon ces autorisations au moment de connecter une boîte. La faire ici rend juste l'écran de consentement plus explicite.

---

## 7. Onglet "Clients" : créer l'identifiant "Application de bureau"

Menu de gauche → **Clients** → **Create client** (ou **+ Create credentials → OAuth client ID** dans l'onglet "Credentials" classique).

1. **Application type** : **Desktop app** (Application de bureau).
2. **Name** : `Maily Desktop`.
3. **Create**.
4. Une fenêtre affiche ton **Client ID** et **Client secret**.
   - Clique **Download JSON** (recommandé) et garde le fichier **hors de tout dossier Git**, ne le partage pas.
   - Tu peux aussi juste copier les 2 valeurs.

> Dans Maily, tu colleras ce `client_id` + `client_secret` (ou importeras le JSON) dans les **réglages** ; ils seront stockés dans le **Trousseau macOS**, jamais dans le code ni dans git.

---

## 8. Ce qui se passera à la 1re connexion dans Maily

- Maily ouvrira ton navigateur sur l'écran de consentement Google.
- Comme l'app n'est **pas "vérifiée"** (normal pour un projet perso), Google affichera **"Google n'a pas validé cette application"**.
  - Clique **Paramètres avancés** (Advanced) → **Accéder à Maily (non sécurisé)** (Go to Maily (unsafe)).
  - C'est **attendu** et sans risque : c'est **ta** propre app, **tes** identifiants.
- Tu autorises les accès (gestion + envoi). À répéter **une fois par boîte**.
- Cas particulier compte Workspace : si un compte `@example.org`/`@thanaelfontaine.eu` est bloqué par une **règle d'administration** ("Accès bloqué"), va dans **Admin console → Sécurité → Contrôles des API → Gérer l'accès des applications tierces**, et autorise l'app par son **Client ID**. (Tu es admin, donc tu peux ; une seule fois pour les deux domaines.)

---

## Récapitulatif : ce dont on aura besoin

Le `client_id` + `client_secret` (ou le fichier JSON téléchargé). On les mettra dans les **réglages de Maily**, en local, quand l'app saura les recevoir.

⚠️ **Ne colle jamais le `client_secret` dans le chat.** Dis-moi simplement **"c'est fait"** quand tu l'as, et on le branchera dans l'app.
