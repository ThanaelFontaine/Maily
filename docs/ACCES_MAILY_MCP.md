# Accéder à Maily depuis un agent Claude (serveur MCP)

Maily expose tes boîtes mail (Gmail + Orange) à une session Claude qui tourne
**sur ce Mac**, via un serveur MCP local. Aucun réseau, aucun port : transport
`stdio`. La lecture des secrets ne demande **pas** Touch ID (la porte biométrique
ne protège que l'app graphique) - c'est voulu, pour que l'agent local travaille
sans friction.

> ⚠️ Ça marche dans **Claude Code** et **Claude Desktop** uniquement.
> **Cowork / claude.ai ne peuvent pas** utiliser un serveur MCP local (ils
> n'acceptent que des connecteurs distants).

---

## 1. Activer le serveur (à faire une fois)

### Claude Code
Le repo contient déjà un [`.mcp.json`](../.mcp.json) prêt à l'emploi. Il suffit
d'ouvrir une session Claude Code **dans le dossier du projet** :

```bash
cd /Users/you/Documents/GitHub/fetch-multi-mail-viewer-sender
claude
```

Claude Code détecte le `.mcp.json` et demande d'approuver le serveur `maily`
(sinon, taper `/mcp` pour le gérer). Une fois approuvé, les outils `maily_*` sont
disponibles.

### Claude Desktop
Ajouter ce bloc dans la config MCP (Réglages → Développeur → Modifier la config),
puis redémarrer Claude Desktop :

```json
{
  "mcpServers": {
    "maily": {
      "command": "uv",
      "args": ["--directory",
               "/Users/you/Documents/GitHub/fetch-multi-mail-viewer-sender",
               "run", "python", "-m", "app.mcp_server"]
    }
  }
}
```

---

## 2. Message prêt à coller à un autre Claude

> Tu as accès à mes boîtes mail via le serveur MCP **`maily`** (outils `maily_*`).
> Pour cibler un compte, utilise le paramètre `profile` = l'email **ou** le nom
> du profil (ex. `Europe`, `Perso`, `moi@orange.fr`). Commence toujours par
> `maily_list_accounts` pour voir les profils. Les identifiants de message
> (`message_id`) viennent de `maily_list_messages` / `maily_search`.
> Avant d'**envoyer** (`maily_send`) ou de **supprimer** (`maily_trash`),
> demande-moi confirmation. Les comptes Orange sont en **lecture seule**
> (pas d'envoi).

---

## 3. Les outils disponibles

| Outil | Paramètres | Ce qu'il fait |
|---|---|---|
| `maily_list_accounts` | - | Liste les profils (id, email, nom, couleur). |
| `maily_list_messages` | `profile`, `category="inbox"`, `limit=20`, `unread_only=False` | Messages récents d'un profil. `category` : `inbox` / `primary` / `promotions` / `social` / `updates` / `forums` / `archived` / `all`. |
| `maily_get_message` | `message_id`, `include_html=False` | Contenu complet d'un message (expéditeur, date, sujet, corps texte ; + HTML si demandé). |
| `maily_search` | `query`, `profile=None`, `limit=20` | Recherche plein-texte locale (sujet, corps, expéditeur). Sans `profile` : tous les comptes. |
| `maily_sync` | `profile=None` | Récupère les nouveaux mails. Sans `profile` : tous les comptes. |
| `maily_export_eml` | `message_id`, `dest_path=None` | Enregistre un message en `.eml` (défaut : `~/Downloads`). Renvoie le chemin. |
| `maily_download_attachment` | `message_id`, `attachment_id`, `dest_path=None` | Télécharge une pièce jointe sur le disque. |
| `maily_trash` | `message_id` | Met un message à la corbeille (**réversible**). Confirmer avant. |
| `maily_send` | `profile`, `to`, `subject`, `body_text`, `cc=None` | Envoie un mail **depuis un compte Gmail**. Irréversible → confirmer avant. |

Notes :
- **`profile`** accepte l'id numérique, l'email, ou le nom du profil (insensible
  à la casse).
- **`message_id`** est l'identifiant interne renvoyé par `list_messages` /
  `search` (pas l'id Gmail/IMAP).
- **Orange** = lecture + gestion (lire, chercher, PJ, corbeille, .eml). Pas
  d'envoi.

---

## 4. Recettes courantes

- **« Mes non-lus sur Perso »**
  `maily_list_messages(profile="Perso", unread_only=True)`
- **« Cherche les mails de facture partout »**
  `maily_search(query="facture")`
- **« Résume ce mail »**
  `maily_get_message(message_id=123)` puis résumer.
- **« Sauvegarde ce mail en .eml sur le Bureau »**
  `maily_export_eml(message_id=123, dest_path="~/Desktop")`
- **« Télécharge la pièce jointe »**
  `maily_list_messages` → `maily_get_message` (repère la PJ) →
  `maily_download_attachment(message_id, attachment_id)`
- **« Mets ce mail à la corbeille »** (après confirmation)
  `maily_trash(message_id=123)`
- **« Réponds à Untel depuis Europe »** (Gmail, après confirmation)
  `maily_send(profile="Europe", to="untel@x.co", subject="…", body_text="…")`

---

## 5. Dépannage

- **Les outils `maily_*` n'apparaissent pas** → serveur non approuvé : `/mcp`
  dans Claude Code, ou vérifier la config Claude Desktop puis redémarrer.
- **« profil introuvable »** → lancer `maily_list_accounts` et réutiliser
  exactement un email ou un nom listé.
- **Rien de récent** → `maily_sync(profile="…")` d'abord.
- **`uv` introuvable** → installer `uv`, ou mettre le chemin complet
  (`which uv`) dans `command`.
