# Google Cloud setup: your own OAuth credentials

[Version française](fr/GOOGLE_CLOUD_SETUP.md)

**Goal:** get a `client_id` and `client_secret` of type *Desktop app*, so that Maily can connect to your Gmail mailboxes through the Gmail API.
**Cost:** free, no credit card, no billing account.
**Time:** about 10 minutes, once. Afterwards, adding a mailbox takes one click.

> Google renamed the consent screen area **Google Auth Platform** (tabs *Overview*, *Branding*, *Audience*, *Clients*, *Data Access*). This guide follows that interface. Labels can change slightly over time; the logic stays the same. If your console is in another language, you can switch it to English from the account menu to match this guide.

---

## Why your own credentials?

Maily has no server and ships no Google credentials. Each user creates a small Google Cloud project and an OAuth client that only they use (the "bring your own credentials" model, as with rclone or GAM). Benefits:

- nobody but you holds a key to your mailbox;
- no dependency on a third party that could disappear or change its terms;
- free, and no Google verification process for personal use.

The only visible consequence is an "unverified app" warning the first time you connect a mailbox (step 8).

---

## 1. Create a Google Cloud project

> **Which Google account?** Any. The account that creates the project simply becomes its owner. It does **not** limit which mailboxes you can connect later: that is decided by the *External* choice in step 3.

1. Go to <https://console.cloud.google.com/> and sign in.
2. Top bar, project selector, **New project**.
3. **Project name:** anything, for example `Maily`.
4. **Organization / Location:**
   - with a Google Workspace account, Google may require your organization. That is normal and does not matter;
   - with a regular `@gmail.com` account you can pick **No organization**.
5. **Create**, then make sure the new project is selected in the top bar.

## 2. Enable the Gmail API

1. Menu (☰), **APIs & Services**, **Library**.
2. Search for **Gmail API**, open it, click **Enable**.

## 3. Google Auth Platform: the "Get started" wizard

Menu (☰), **APIs & Services**, **OAuth consent screen** (this now opens **Google Auth Platform**).

If you see "Google Auth Platform not configured yet", click **Get started**:

1. **App information:** app name `Maily`, user support email: one of your addresses. **Next**.
2. **Audience: choose External.** This is the key step.
   - *Internal* would only allow accounts of your Workspace organization (and is not offered to plain Gmail accounts).
   - *External* allows **all** your accounts: Gmail, Workspace, several domains.
   - **Next**.
3. **Contact information:** your email. **Next**.
4. **Finish:** accept the Google API Services User Data Policy, then **Continue / Create**.

If the wizard was already completed, set each tab as described below.

## 4. Branding tab

Left menu, **Branding**: app name `Maily`, your support email. Logo, domains and links are optional; leave them empty. **Save**.

## 5. Audience tab: user type, test users, publishing

Left menu, **Audience**.

1. **User type:** check that it is **External**.
2. **Test users:** **Add users** and add every address you plan to connect. **Save**. (Once the app is published this list is no longer required, but it does no harm.)
3. **Publishing status:** it says *Testing*. Click **Publish app**, then **Confirm**. The status becomes **In production**.

> **Why publish?** Google's documentation states that a project with an External consent screen in *Testing* status is issued refresh tokens that **expire after 7 days**. You would have to reconnect every week. Once *In production*, the connection lasts.
>
> Publishing does not list your app anywhere and does not give anyone access to your mail: every mailbox still has to be connected by its owner through the consent screen, and the app stays "unverified" (see step 8). Note that for a *Desktop app* client, Google's documentation assumes the client secret cannot be kept secret (installed apps "cannot keep secrets"): it identifies your app but is not what protects your mail. Your mailboxes are protected by the per-account consent and the tokens Maily keeps encrypted. Still, keep the JSON file private. Google limits unverified apps to 100 users in total, far more than personal use needs.

## 6. Data Access tab: scopes (optional)

Left menu, **Data Access**, **Add or remove scopes**.

The filterable table at the top usually does not list Gmail scopes ("No rows to display" is normal). Use **Manually add scopes** at the bottom and paste these two lines:

```
https://www.googleapis.com/auth/gmail.modify
https://www.googleapis.com/auth/gmail.send
```

**Add to table**, **Update**, **Save**.

This step is optional: Maily requests these scopes anyway when you connect a mailbox. Declaring them here only makes the consent screen clearer. Google labels them *restricted*: that is expected for Gmail access, and it is fine for personal, unverified use.

What they allow:

- `gmail.modify`: read messages and labels, mark as read, archive, move to trash. It does **not** allow permanent deletion.
- `gmail.send`: send messages.

## 7. Clients tab: create the Desktop app client

Left menu, **Clients**, **Create client** (or, in the classic *Credentials* page, **Create credentials > OAuth client ID**).

1. **Application type:** **Desktop app**.
2. **Name:** `Maily Desktop`.
3. **Create**.
4. The dialog shows the **Client ID** and **Client secret**. Click **Download JSON**.

Keep this file **outside any git folder** and do not share it.

### Give the client to Maily

From the Maily folder:

```bash
uv run python scripts/store_client_config.py ~/Downloads/client_secret_XXXX.json
```

The script reads the file, stores the client id and secret **encrypted** in `secrets.enc` (in Maily's data folder), and never prints the secret. You can then delete the downloaded JSON.

Without a file, the script asks for both values interactively (the secret is typed without being displayed):

```bash
uv run python scripts/store_client_config.py
```

## 8. Connecting a mailbox

In the app, **+ Ajouter un compte** (add an account) at the bottom left, then **Compte Google**. Or from a terminal:

```bash
uv run python scripts/connect_account.py
```

What happens:

1. Maily opens your browser on Google's consent screen, and listens on `127.0.0.1` for the answer (a local loopback, nothing goes through a server).
2. Choose the account to connect.
3. Google shows **"Google hasn't verified this app"**. Click **Advanced**, then **Go to Maily (unsafe)**. This is expected: the app is yours and the credentials are yours.
4. Allow the requested access (manage and send email).
5. The browser says the flow is complete; Maily stores the token encrypted and adds the account. The first sync starts.

Repeat for each mailbox. In the app, the consent must be given within 3 minutes, otherwise the attempt is cancelled (just try again).

---

## Troubleshooting

**"Identifiants client (client_id/secret) absents" (client credentials missing).**
Step 7 was not completed on this machine: run `scripts/store_client_config.py`.

**"Access blocked: Maily has not completed the Google verification process".**
The consent screen is in *Testing* and this address is not in the test users. Add it (step 5.2) or publish the app (step 5.3).

**Google Workspace account: "Access blocked" by an administrator policy.**
Your Workspace administrator restricts third-party apps. In the Admin console: **Security > Access and data control > API controls > Manage third-party app access**, add the app by its **Client ID** and allow it. If you are not the administrator, ask them.

**"redirect_uri_mismatch" or "invalid client".**
The client was not created as **Desktop app**. Create a new client of that type and store it again.

**The connection expires after a week.**
The app is still in *Testing*: publish it (step 5.3), then reconnect the account once.

**I want to revoke Maily's access.**
In Maily: *Réglages > Comptes > Déconnecter*. On Google's side: <https://myaccount.google.com/connections>, select Maily, remove access. To stop everything, you can also delete the OAuth client or the whole Cloud project.
