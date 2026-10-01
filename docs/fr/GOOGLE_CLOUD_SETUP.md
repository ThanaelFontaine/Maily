# Configuration Google Cloud : tes propres identifiants OAuth

[English version](../GOOGLE_CLOUD_SETUP.md)

**But :** obtenir un `client_id` et un `client_secret` de type *Application de bureau*, pour que Maily se connecte à tes boîtes Gmail via l'API Gmail.
**Coût :** gratuit, sans carte bancaire, sans compte de facturation.
**Durée :** une dizaine de minutes, une seule fois. Ensuite, ajouter une boîte prend un clic.

> Google a renommé l'espace de l'écran de consentement **Google Auth Platform** (onglets *Overview*, *Branding*, *Audience*, *Clients*, *Data Access*). Ce guide suit cette interface, avec les libellés anglais de la console. Ils peuvent varier un peu dans le temps ; la logique reste la même. Si ta console est en français, tu peux la passer en anglais depuis le menu du compte pour suivre plus facilement.

---

## Pourquoi tes propres identifiants ?

Maily n'a pas de serveur et ne fournit aucun identifiant Google. Chaque utilisateur crée un petit projet Google Cloud et un client OAuth qu'il est seul à utiliser (le modèle « bring your own credentials », comme rclone ou GAM). Avantages :

- personne d'autre que toi ne détient de clé vers ta boîte ;
- aucune dépendance à un tiers qui pourrait disparaître ou changer ses conditions ;
- gratuit, sans procédure de vérification Google pour un usage personnel.

La seule conséquence visible : un avertissement « application non vérifiée » la première fois que tu connectes une boîte (étape 8).

---

## 1. Créer un projet Google Cloud

> **Quel compte Google utiliser ?** N'importe lequel. Le compte qui crée le projet en devient simplement le propriétaire. Il ne limite **pas** les boîtes que tu pourras connecter ensuite : c'est le choix *External* de l'étape 3 qui en décide.

1. Va sur <https://console.cloud.google.com/> et connecte-toi.
2. Barre du haut, sélecteur de projet, **New project** (Nouveau projet).
3. **Project name :** ce que tu veux, par exemple `Maily`.
4. **Organization / Location :**
   - avec un compte Google Workspace, Google peut imposer ton organisation : c'est normal et sans importance ;
   - avec un compte `@gmail.com` classique, tu peux choisir **No organization**.
5. **Create**, puis vérifie que le nouveau projet est bien sélectionné en haut.

## 2. Activer l'API Gmail

1. Menu (☰), **APIs & Services**, **Library** (Bibliothèque).
2. Cherche **Gmail API**, ouvre-la, clique **Enable** (Activer).

## 3. Google Auth Platform : l'assistant « Get started »

Menu (☰), **APIs & Services**, **OAuth consent screen** (qui ouvre désormais **Google Auth Platform**).

Si tu vois « Google Auth Platform not configured yet », clique **Get started** :

1. **App information :** nom de l'app `Maily`, email d'assistance : une de tes adresses. **Next**.
2. **Audience : choisis External.** C'est l'étape clé.
   - *Internal* ne laisserait se connecter que les comptes de ton organisation Workspace (et n'est pas proposé aux comptes Gmail classiques).
   - *External* laisse se connecter **tous** tes comptes : Gmail, Workspace, plusieurs domaines.
   - **Next**.
3. **Contact information :** ton email. **Next**.
4. **Finish :** accepte la *Google API Services User Data Policy*, puis **Continue / Create**.

Si l'assistant a déjà été fait, règle chaque onglet comme décrit ci-dessous.

## 4. Onglet Branding

Menu de gauche, **Branding** : nom `Maily`, ton email d'assistance. Logo, domaines et liens sont facultatifs : laisse vide. **Save**.

## 5. Onglet Audience : type, utilisateurs de test, publication

Menu de gauche, **Audience**.

1. **User type :** vérifie que c'est bien **External**.
2. **Test users :** **Add users** et ajoute toutes les adresses que tu comptes connecter. **Save**. (Une fois l'app publiée, cette liste n'est plus nécessaire, mais elle ne gêne pas.)
3. **Publishing status :** il indique *Testing*. Clique **Publish app**, puis **Confirm**. Le statut passe à **In production**.

> **Pourquoi publier ?** La documentation de Google précise qu'un projet dont l'écran de consentement est *External* et au statut *Testing* reçoit des jetons de rafraîchissement qui **expirent au bout de 7 jours**. Il faudrait te reconnecter chaque semaine. En *In production*, la connexion dure.
>
> Publier ne référence ton app nulle part et ne donne à personne l'accès à tes mails : chaque boîte doit toujours être connectée par son propriétaire via l'écran de consentement, et l'app reste « non vérifiée » (voir l'étape 8). Note que pour un client *Desktop app*, la documentation de Google part du principe que le secret client ne peut pas rester secret (une app installée « ne peut pas garder de secrets ») : il identifie ton app mais ce n'est pas lui qui protège tes mails. Tes boîtes sont protégées par le consentement donné compte par compte et par les jetons que Maily garde chiffrés. Garde tout de même le fichier JSON pour toi. Google limite une app non vérifiée à 100 utilisateurs au total, bien plus qu'il n'en faut pour un usage personnel.

## 6. Onglet Data Access : les scopes (facultatif)

Menu de gauche, **Data Access**, **Add or remove scopes**.

Le tableau filtrable du haut n'affiche généralement pas les scopes Gmail (« No rows to display » est normal). Utilise **Manually add scopes** en bas et colle ces deux lignes :

```
https://www.googleapis.com/auth/gmail.modify
https://www.googleapis.com/auth/gmail.send
```

**Add to table**, **Update**, **Save**.

Cette étape est facultative : Maily demande de toute façon ces scopes au moment de connecter une boîte. Les déclarer ici rend juste l'écran de consentement plus clair. Google les classe *restricted* : c'est attendu pour un accès Gmail, et sans conséquence pour un usage personnel non vérifié.

Ce qu'ils permettent :

- `gmail.modify` : lire les messages et libellés, marquer comme lu, archiver, mettre à la corbeille. Il ne permet **pas** la suppression définitive.
- `gmail.send` : envoyer des messages.

## 7. Onglet Clients : créer le client « Application de bureau »

Menu de gauche, **Clients**, **Create client** (ou, dans la page classique *Credentials*, **Create credentials > OAuth client ID**).

1. **Application type :** **Desktop app** (Application de bureau).
2. **Name :** `Maily Desktop`.
3. **Create**.
4. La fenêtre affiche le **Client ID** et le **Client secret**. Clique **Download JSON**.

Garde ce fichier **hors de tout dossier git** et ne le partage pas.

### Confier le client à Maily

Depuis le dossier de Maily :

```bash
uv run python scripts/store_client_config.py ~/Downloads/client_secret_XXXX.json
```

Le script lit le fichier, range l'identifiant et le secret **chiffrés** dans `secrets.enc` (dans le dossier de données de Maily) et n'affiche jamais le secret. Tu peux ensuite supprimer le JSON téléchargé.

Sans fichier, le script demande les deux valeurs (le secret se tape sans s'afficher) :

```bash
uv run python scripts/store_client_config.py
```

## 8. Connecter une boîte

Dans l'app, **+ Ajouter un compte** en bas à gauche, puis **Compte Google**. Ou depuis un terminal :

```bash
uv run python scripts/connect_account.py
```

Ce qui se passe :

1. Maily ouvre ton navigateur sur l'écran de consentement Google et attend la réponse sur `127.0.0.1` (une boucle locale, rien ne passe par un serveur).
2. Choisis le compte à connecter.
3. Google affiche **« Google n'a pas validé cette application »**. Clique **Paramètres avancés**, puis **Accéder à Maily (non sécurisé)**. C'est attendu : l'app est la tienne, les identifiants aussi.
4. Autorise les accès demandés (gestion et envoi des emails).
5. Le navigateur indique que c'est terminé ; Maily range le jeton chiffré et ajoute le compte. La première synchronisation démarre.

Répète pour chaque boîte. Dans l'app, le consentement doit être donné dans les 3 minutes, sinon la tentative est annulée (il suffit de recommencer).

---

## Dépannage

**« Identifiants client (client_id/secret) absents ».**
L'étape 7 n'a pas été faite sur cet ordinateur : lance `scripts/store_client_config.py`.

**« Accès bloqué : Maily n'a pas terminé la procédure de validation de Google ».**
L'écran de consentement est en *Testing* et cette adresse n'est pas dans les utilisateurs de test. Ajoute-la (étape 5.2) ou publie l'app (étape 5.3).

**Compte Google Workspace : « Accès bloqué » par une règle d'administration.**
Ton administrateur Workspace restreint les applications tierces. Dans la console d'administration : **Sécurité > Accès et contrôle des données > Commandes des API > Gérer l'accès des applications tierces**, ajoute l'app par son **Client ID** et autorise-la. Si tu n'es pas administrateur, demande-le-lui.

**« redirect_uri_mismatch » ou « invalid client ».**
Le client n'a pas été créé en **Desktop app**. Crée un nouveau client de ce type et enregistre-le à nouveau.

**La connexion expire au bout d'une semaine.**
L'app est encore en *Testing* : publie-la (étape 5.3), puis reconnecte le compte une fois.

**Je veux retirer l'accès de Maily.**
Dans Maily : *Réglages > Comptes > Déconnecter*. Côté Google : <https://myaccount.google.com/connections>, choisis Maily, supprime l'accès. Pour tout arrêter, tu peux aussi supprimer le client OAuth ou le projet Cloud entier.
