# Instagram, Facebook and X: setup

The Competitive Tracker already contains the Instagram, Facebook and X integrations. They stay
**"Not configured"** until you add credentials, and nothing is sent to these platforms before then.
The app starts and works normally (YouTube, websites) without them.

Checked against the platforms' official documentation in October 2026. Platform rules change: check
the linked pages before applying.

## 1. Settings: where they go

All credentials go in **`backend\.env`** (copy `backend\.env.example`). That file is git-ignored and is
only read by the backend: the browser never sees a secret or a token. Restart the API after editing it.

| Setting | Needed for | Where to get it |
|---|---|---|
| `TOKEN_ENCRYPTION_KEY` | all three | Generate: `backend\env\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `META_APP_ID` | Instagram, Facebook | developers.facebook.com > your app > App settings > Basic |
| `META_APP_SECRET` | Instagram, Facebook | same page ("App secret") |
| `META_GRAPH_VERSION` | optional | default `v26.0` |
| `X_CLIENT_ID` | X | developer.x.com > your app > Keys and tokens > OAuth 2.0 Client ID |
| `X_CLIENT_SECRET` | X (Web App type) | same page |
| `X_MAX_POSTS_PER_ACCOUNT` | optional | posts read per account per refresh, default 20 |
| `PUBLIC_API_URL` | optional | default `http://localhost:8000` (used to build the redirect URIs) |
| `FRONTEND_URL` | optional | default `http://localhost:5173` (where you land after connecting) |

Stored access tokens are encrypted with `TOKEN_ENCRYPTION_KEY` (Fernet). If the key changes,
existing connections can't be read and must be reconnected.

Redirect (callback) URIs to register, with the default settings:

- Facebook: `http://localhost:8000/oauth/facebook/callback`
- Instagram: `http://localhost:8000/oauth/instagram/callback`
- X: `http://localhost:8000/oauth/x/callback`

Accounts > Platform connections shows the exact URIs for your settings. On a real domain, Meta requires https.

## 2. Instagram (Instagram API with Facebook Login)

**What it needs**

- A Meta developer app (type *Business*) with **Facebook Login for Business** and the
  **Instagram API with Facebook Login** product.
- Your Instagram account must be a **professional account (Business or Creator)** linked to a
  **Facebook Page you manage**. Personal Instagram accounts are not supported by the API.
- Permissions requested: `instagram_basic`, `instagram_manage_insights`, `pages_show_list`,
  `pages_read_engagement`, `business_management`.
- While the app is in development, only people with a role on the app can connect. For anyone else:
  **App Review** for those permissions plus **Business Verification**.

**What is collected**

- Your account: profile (username, followers, picture) and your recent posts: caption, date, link,
  type (Reel, photo, carousel, video), likes and comments.
- Competitors (add their username or profile link): through **Business Discovery**, which only works
  for other **public professional accounts**. You get the same public fields. Likes are missing when an
  account hides them (shown as "not available", never 0). Reach, impressions and views of other
  accounts are **not** available. Competitors never have to authorize anything.

Docs: https://developers.facebook.com/docs/instagram-platform/instagram-api-with-facebook-login

## 3. Facebook Pages

**What it needs**

- The same Meta app. Add the redirect URI above to Facebook Login.
- Permissions requested: `pages_show_list`, `pages_read_engagement`.
- You connect a **Page you manage**. A personal profile is not supported, and signing in does not
  give access to every Page: you choose one of the Pages your login manages.
- **Competitor Pages** need Meta's **Page Public Content Access** feature (App Review + Business
  Verification; Meta may ask for additional terms). Until it's approved, competitor Pages are saved as
  **Unverified** and their posts aren't read.

**What is collected**: Page name, followers, and posts: text, date, link, type (photo, video, album,
post), reactions (shown as likes), comments and shares, as public counts.

Docs: https://developers.facebook.com/docs/pages-api ,
https://developers.facebook.com/docs/features-reference/page-public-content-access

## 4. X

**What it needs**

- A project and app at developer.x.com. In *User authentication settings*: **OAuth 2.0**, app type
  **Web App** (gives a client secret), callback URL above.
- Scopes requested: `tweet.read`, `users.read`, `offline.access` (keeps the connection with refresh
  tokens; access tokens last 2 hours and are refreshed automatically).
- **Paid usage**: since February 2026 the X API is pay-per-use with prepaid credits. As of October 2026
  X lists $0.005 per post read and $0.010 per user read, with up to 3 million post reads a month. Check
  https://docs.x.com/x-api/getting-started/pricing before budgeting. Each Refresh reads at most
  `X_MAX_POSTS_PER_ACCOUNT` posts per account (default 20) plus one profile lookup for new accounts.
  When credits run out, X returns an error and the tracker shows it on the account.

**What is collected**: profiles (name, followers, picture) and each account's latest original posts
(no replies or reposts): text, date, link, media type, and the public metrics X returns: views
(impressions), likes, replies, reposts. Metrics depend on your API access; missing ones are shown as
"not available".

Docs: https://docs.x.com/resources/fundamentals/authentication/oauth-2-0/authorization-code

## 5. Connecting

1. Fill in `backend\.env`, restart the API.
2. Accounts > **Platform connections**: the platform now shows *Not connected*. Click **Connect**,
   sign in on the platform and approve.
3. Facebook / Instagram: if your login manages several Pages, choose one.
4. Add your own account (tick *Ours*) and competitors in the form below, then click **Refresh**.

Accounts added before a platform was connected are **Unverified**; they're checked on the next Refresh.

## 6. What happens when something goes wrong

| Situation | What you see |
|---|---|
| Settings missing | "Not configured — Add API credentials to enable this integration." No API calls. |
| Not connected yet | Accounts on that platform show "Waiting for connection"; Refresh skips them. |
| Token expired or revoked | Connection shows "Expired: reconnect"; Refresh skips the platform. |
| Rate limit | That platform stops for this Refresh; the others continue. |
| Missing permission / feature | The account shows the platform's reason (e.g. Page Public Content Access). |
| Temporary error (5xx, timeout) | Retried twice with a short wait, then shown on the account. |

## 7. Limits of this version

- The tracker has no user login of its own (as before): connections belong to a **workspace**, and
  anyone who can open the tracker can use that workspace. Run it only where that is acceptable.
- Instagram, Facebook and X don't make competitors' views or reach public, so on those platforms
  "× usual" is interactions (likes + comments + shares) ÷ the account's usual interactions. YouTube
  uses views. Likes and comments are shown as reported.
- No real connection has been tested yet: the sign-in and data flows are covered by automated tests
  with mocked platform responses only. Test with your own accounts once credentials are added.
