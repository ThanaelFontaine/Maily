# Google Cloud setup: your own OAuth credentials

**Goal:** get a `client_id` and `client_secret` of type *Desktop app*, so that Maily can connect to your Gmail mailboxes through the Gmail API.
**Cost:** Google states that "all standard use of the Gmail API is available at no additional cost" ([Gmail API quotas](https://developers.google.com/workspace/gmail/api/reference/quota)); the same page announces charges, later in 2026, only for usage beyond the quota limits.
**Time:** about 10 minutes, once. Afterwards, adding a mailbox takes one click.

> Google now calls the consent screen area **Google Auth Platform**, with sections such as *Branding*, *Audience*, *Clients* and *Data Access* ([Google's guide](https://developers.google.com/workspace/guides/configure-oauth-consent)). This guide follows that interface. Labels can change slightly over time; the logic stays the same.

---

## Why your own credentials?

Maily has no server and ships no Google credentials. Each user creates a small Google Cloud project and an OAuth client that only they use (the "bring your own credentials" model). Benefits:

- nobody but you holds a key to your mailbox;
- no dependency on a third party that could disappear or change its terms;
- no Google verification process for personal use: Google says that an app for your personal use (fewer than 100 users) can keep being used without verification ([source](https://support.google.com/cloud/answer/13464323)).

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

Menu (☰), **Google Auth Platform** (in older menus: **APIs & Services**, **OAuth consent screen**, which opens the same page).

If the page offers a **Get started** button (the platform is not configured yet), click it:

1. **App information:** app name `Maily`, user support email: one of your addresses. **Next**.
2. **Audience: choose External.** This is the key step.
   - *Internal* limits authorization to members of the Google Cloud organization the project belongs to, so it would shut out your other addresses.
   - *External* makes the app "available to any user with a Google Account" ([source](https://support.google.com/cloud/answer/15549945)): Gmail, Workspace, several domains.
   - **Next**.
3. **Contact information:** your email. **Next**.
4. **Finish:** accept the Google API Services User Data Policy, then **Continue / Create**.

If the wizard was already completed, set each tab as described below.

## 4. Branding tab

Left menu, **Branding**: app name `Maily`, your support email. Logo, domains and links are optional; leave them empty. **Save**.

## 5. Audience tab: user type, test users, publishing

Left menu, **Audience**.

1. **User type:** check that it is **External**.
2. **Test users:** **Add users** and add every address you plan to connect. **Save**. While the app is in *Testing*, only these addresses (up to 100) can connect; once it is published the list is no longer required, but it does no harm.
3. **Publishing status:** it says *Testing*. Click **Publish app**, then **Confirm**. The status becomes **In production**.

> **Why publish?** Google's documentation states that a project with an External consent screen in *Testing* status "is issued a refresh token expiring in 7 days" ([source](https://developers.google.com/identity/protocols/oauth2)). You would have to reconnect every week. A project is *In production* once you click **Publish app** ([source](https://support.google.com/cloud/answer/15549945)), and the connection then lasts.
>
> Publishing does not list your app anywhere and does not give anyone access to your mail: every mailbox still has to be connected by its owner through the consent screen, and the app stays "unverified" (see step 8). Note that for installed applications such as a *Desktop app* client, Google's documentation says the client secret "is obviously not treated as a secret" ([source](https://developers.google.com/identity/protocols/oauth2)): it identifies your app but is not what protects your mail. Your mailboxes are protected by the per-account consent and the tokens Maily keeps encrypted. Still, keep the JSON file private. Apps that show the unverified app screen are limited to 100 new users in total ([source](https://support.google.com/cloud/answer/15549945)), far more than personal use needs.

## 6. Data Access tab: scopes (optional)

Left menu, **Data Access**, **Add or remove scopes**.

The filterable table at the top usually does not list Gmail scopes ("No rows to display" is normal). Use **Manually add scopes** at the bottom and paste these two lines:

```
https://www.googleapis.com/auth/gmail.modify
https://www.googleapis.com/auth/gmail.send
```

**Add to table**, **Update**, **Save**.

This step is optional: Maily requests these scopes anyway when you connect a mailbox. Declaring them here only makes the consent screen clearer. Google classifies `gmail.modify` as *restricted* and `gmail.send` as *sensitive* ([Gmail API scopes](https://developers.google.com/workspace/gmail/api/auth/scopes)): that is expected for Gmail access, and it is fine for personal, unverified use.

What they allow:

- `gmail.modify`: Google's description is "Read, compose, and send emails from your Gmail account. This scope does not allow immediate, permanent deletion of threads and messages, bypassing the trash." Maily uses it to read messages and labels, mark as read, archive and move to the trash.
- `gmail.send`: "Send email on your behalf." Maily uses it to send the messages you write.

## 7. Clients tab: create the Desktop app client

Left menu, **Clients**, **Create client** (or, in the classic *Credentials* page, **Create credentials > OAuth client ID**). Google's own steps: [Create access credentials](https://developers.google.com/workspace/guides/create-credentials).

1. **Application type:** **Desktop app**.
2. **Name:** `Maily Desktop`.
3. **Create**.
4. The dialog shows the **Client ID** and **Client secret**, with a button to download them as a JSON file: click it. (If you closed the dialog, open the client from the *Clients* list to download the JSON.)

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

In the app, click **+ Add account** at the bottom of the left column, then **Google account**. Or from a terminal:

```bash
uv run python scripts/connect_account.py
```

What happens:

1. Maily opens your browser on Google's consent screen, and listens on `127.0.0.1` for the answer (a local loopback, nothing goes through a server).
2. Choose the account to connect.
3. Google shows **"Google hasn't verified this app"**. Click **Advanced**, then **Go to Maily (unsafe)** (Google documents this way past the screen for personal-use projects, for example in its [Device Access guide](https://developers.google.com/nest/device-access/reference/errors/authorization)). This is expected: the app is yours and the credentials are yours.
4. Allow the requested access (manage and send email).
5. The browser says the flow is complete; Maily stores the token encrypted and adds the account. The first sync starts.

Repeat for each mailbox. In the app, the consent must be given within 3 minutes, otherwise the attempt is cancelled (just try again).

---

## Troubleshooting

**"Google needs you to sign in again (or the OAuth client is missing)" in the app, or "OAuth client credentials (client_id/secret) are missing" in a terminal.**
Step 7 was not completed on this computer: run `uv run python scripts/store_client_config.py path/to/client_secret.json` from the Maily folder.

**"Access blocked: Maily has not completed the Google verification process".**
The consent screen is in *Testing* and this address is not in the test users. Add it (step 5.2) or publish the app (step 5.3).

**Google Workspace account: "Access blocked" by an administrator policy.**
Your Workspace administrator restricts third-party apps. The administrator can allow the app in the Google Admin console: **Security > Access and data control > API controls**, **Manage App Access**, **Configure new app**, search by your **OAuth client ID**, then choose the access level **Trusted** ([Google's instructions](https://knowledge.workspace.google.com/admin/apps/control-which-apps-access-google-workspace-data)). If you are not the administrator, ask them.

**"redirect_uri_mismatch" or "invalid client".**
The client was not created as **Desktop app**. Create a new client of that type and store it again.

**The connection expires after a week.**
The app is still in *Testing*: publish it (step 5.3), then reconnect the account once.

**I want to revoke Maily's access.**
In Maily: *Settings > Accounts > Disconnect*. On Google's side: <https://myaccount.google.com/connections>, select Maily, remove access. To stop everything, you can also delete the OAuth client or the whole Cloud project.
