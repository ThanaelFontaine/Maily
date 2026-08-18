# Guide : créer tes identifiants Google (BYO credentials) - gratuit, ~10 min

> But : obtenir un `client_id` + `client_secret` de type "Application de bureau" pour que Maily se connecte à tes boîtes Gmail via l'API Gmail. C'est **gratuit**, sans carte bancaire, et **sans vérification Google** (usage personnel). Tu fais ça **une seule fois** ; ensuite tu connecteras chaque boîte d'un clic dans l'app.
>
> Note : l'interface de Google Cloud Console évolue ; les libellés peuvent varier légèrement. La logique reste la même.

## 1. Créer un projet Google Cloud (gratuit)

1. Va sur https://console.cloud.google.com/ (connecte-toi avec un de tes comptes Google, par ex. `work@example.com`).
2. En haut, ouvre le sélecteur de projet, puis **Nouveau projet**.
3. Nom : `Maily` (ou ce que tu veux). Pas besoin d'organisation. **Créer**.
4. Sélectionne bien ce projet dans le sélecteur en haut avant la suite.

## 2. Activer l'API Gmail

1. Menu ☰ → **APIs & Services** → **Library** (Bibliothèque).
2. Cherche **Gmail API**, clique dessus, puis **Enable** (Activer).

## 3. Configurer l'écran de consentement OAuth

1. Menu ☰ → **APIs & Services** → **OAuth consent screen** (Écran de consentement OAuth).
2. Type d'utilisateur : choisis **External** (Externe). *(C'est obligatoire car tu veux connecter aussi des Gmail hors Workspace ; "Internal" ne marcherait que pour un seul domaine Workspace.)* → **Create**.
3. Renseigne le minimum :
   - **App name** : `Maily`
   - **User support email** : ton email
   - **Developer contact** : ton email
   - (Logo, domaines : facultatifs, laisse vide.)
   - **Save and Continue**.
4. **Scopes** : tu peux **Save and Continue** sans rien ajouter ici (l'app demandera les scopes elle-même au moment de la connexion). 
5. **Test users** : ajoute ici **chacune de tes adresses** que tu veux connecter (`work@example.com`, `you@example.com`, ton Gmail perso, etc.). **Save and Continue**.

## 4. Passer l'app "En production" (important)

> Pourquoi : en mode "Testing", les connexions expirent au bout de **7 jours** (il faudrait te reconnecter chaque semaine). En "Production", c'est durable. Pour un usage perso (< ~100 utilisateurs), **aucune vérification n'est requise**.

1. Toujours dans **OAuth consent screen**, repère le statut de publication (**Publishing status**).
2. Clique **Publish App** → **Confirm**. Le statut passe à **In production**.
3. Si Google affiche "vérification requise / non nécessaire" : ignore, tu peux rester non vérifié pour un usage perso. (Tu verras juste un écran d'avertissement à la première connexion, voir étape 6.)

## 5. Créer l'identifiant OAuth "Application de bureau"

1. Menu ☰ → **APIs & Services** → **Credentials** (Identifiants).
2. **+ Create Credentials** → **OAuth client ID**.
3. **Application type** : **Desktop app** (Application de bureau). Nom : `Maily Desktop`. → **Create**.
4. Une fenêtre affiche ton **Client ID** et **Client secret**. **Télécharge le JSON** (bouton "Download JSON") et/ou copie les deux valeurs.
   - ⚠️ Garde ce fichier **hors de tout dossier Git** et ne le partage pas. (Dans Maily, tu le colleras dans les réglages ; il sera stocké dans le Trousseau macOS.)

## 6. Ce qui se passera à la première connexion dans Maily

- Maily ouvrira ton navigateur sur l'écran de consentement Google.
- Comme l'app n'est pas "vérifiée" (normal pour un projet perso), Google affichera **"Google n'a pas validé cette application"**. Clique sur **Paramètres avancés** → **Accéder à Maily (non sécurisé)**. C'est **attendu** et sans risque (c'est **ta** propre app, tes propres identifiants).
- Tu autorises les accès (lecture/gestion + envoi), et c'est fini. À répéter une fois par boîte.

## Récapitulatif de ce que tu me fourniras

Quand tu auras le `client_id` et le `client_secret` (ou le fichier JSON téléchargé), on les mettra dans les réglages de Maily au moment du test live. **Rien à me coller ici dans le chat** (surtout pas le secret) : on le fera dans l'app, en local, quand elle saura les recevoir.
