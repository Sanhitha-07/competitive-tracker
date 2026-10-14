# Competitive Tracker: setup and API keys

Competitive Tracker compares a business's social media with its competitors' on **YouTube, Instagram, Facebook,
X and websites (RSS)**. It finds what's trending on the internet that fits the business, and turns all of it into
a plain-language dashboard with suggestions. It works for small shops, restaurants, brands, agencies, creators,
publishers and news channels.

## 1. Run it

1. Double-click **`START_APP.bat`**. It opens the API and the UI in two windows and then opens
   http://localhost:5173.
2. Optional: double-click **`backend\seed_sample.bat`** to add three made-up "Sample:" workspaces
   (a bakery, a news channel and a fitness creator). You can explore every dashboard without any API key.
   Your real workspaces are never touched. Clicking Refresh on a sample workspace shows read errors, because
   its accounts don't exist.

First-time install (once):

```
cd backend
python -m venv env
env\Scripts\pip install -r requirements.txt
cd ..\frontend
npm install
```

## 2. Add your keys

Copy `backend\.env.example` to **`backend\.env`** and fill in what you have, then restart the API window.
Every key is optional: each platform turns on when its key is present. **Never share or commit `backend\.env`.**

| Key | Turns on | Cost |
|---|---|---|
| `YOUTUBE_API_KEY` | YouTube channels, comments (audience questions), YouTube Trending | Free, 10,000 units/day |
| `TOKEN_ENCRYPTION_KEY` + `META_APP_ID` + `META_APP_SECRET` | Instagram and Facebook sign-in | Free (needs a Meta app; competitors' Facebook Pages need App Review) |
| `TOKEN_ENCRYPTION_KEY` + `X_CLIENT_ID` + `X_CLIENT_SECRET` | X sign-in | Pay per use (X API credits) |
| *(none)* | Google Trends + Google News trends | Free |
| `ANTHROPIC_API_KEY` | AI-written briefing and content ideas on the Overview tab | Pay per use |

### YouTube

1. Go to https://console.cloud.google.com/, then create a project.
2. Open **APIs & Services → Library**, search for **YouTube Data API v3**, and click **Enable**.
3. Open **APIs & Services → Credentials → Create credentials → API key**.
4. Put it in `backend\.env` as `YOUTUBE_API_KEY=...`.

One refresh uses about 5 units per channel. The app stops by itself at `YOUTUBE_DAILY_BUDGET`.

### Instagram, Facebook and X

Each workspace connects its own accounts by signing in (Accounts → Platform connections), and tokens are
stored encrypted. Competitors are then read through that connection. The keys (`TOKEN_ENCRYPTION_KEY`,
`META_APP_ID`, `META_APP_SECRET`, `X_CLIENT_ID`, `X_CLIENT_SECRET`) and the Meta/X app setup are explained
step by step in **[SOCIAL_SETUP.md](SOCIAL_SETUP.md)**.

Competitors' views and reach aren't public on Instagram, Facebook or X, so posts there are compared by
**interactions** (likes, comments, shares) and **engagement per follower**, and each post is compared with
its own account's usual.

### Internet trends (no key)

- **Google Trends**: Google's daily "Trending now" searches for the workspace's country (set in Workspace settings).
- **Google News**: how much is being published about each workspace topic in the last 7 days, and whether it's rising.
  Google's RSS terms allow personal and non-commercial use only. For a commercial product, set `TRENDS_GOOGLE_NEWS=0`
  and add a licensed news API later.
- **YouTube Trending**: the official chart for the country and the industry's video category. Needs the YouTube key.

Trends are checked on every Refresh (at most once an hour) or with **Check trends now** on the Trends page.

### AI briefing (optional)

Set `ANTHROPIC_API_KEY` (from https://console.anthropic.com/). A **Write AI briefing** button then appears on
the Overview tab. Claude only receives the numbers already on the page and is told not to add anything else.
Each click is one paid API call, and identical data is cached. Without a key, the rule-based briefing still works.

## 3. Set up a workspace

1. **+ New workspace** (sidebar): name, type (small business, brand, creator, news channel…) and industry.
   The type fills in sensible defaults: starting goals, brand safety, and a comparison window
   (24 hours for news, 30 days for most businesses).
2. **Workspace** page: niche, audience, **topics/keywords** (these drive coverage gaps and trend searches),
   **country**, and **brand safety**.
3. **Accounts** page: add your own accounts (tick **Ours**) and 3–5 competitors. Give one competitor's
   accounts on different platforms **the same name**, so they're combined in share of voice.
4. Click **Refresh data**.

## 4. How the analysis works (in short)

- **Your posts vs your usual**: each post is compared with its own account's typical post (median of the last 90 days).
  This makes a small shop and a big brand comparable. YouTube uses views; Instagram, Facebook and X use interactions.
- **Share of voice**: each account's share of all posts, and of all public likes, comments and shares, among the
  accounts you track.
- **Coverage gaps**: topics (from titles, captions and hashtags) that competitors post about and you don't.
- **Trends**: matched to your topics, niche, audience, industry and competitors' topics. Each trend is checked for
  **sensitivity** (death, disasters, violence, war, politics, religion, health scares, legal cases):
  - **Strict** (brands, businesses): sensitive or divisive trends are never suggested.
  - **Standard** (creators): divisive topics only if they fit your niche; tragedies are avoided.
  - **Newsroom** (news organisations): sensitive news comes with guidance for covering it responsibly.
- Every suggestion opens **Evidence**: the posts, numbers, sample size, confidence and limitations behind it.

## 5. Tests

```
cd backend
env\Scripts\python -m pytest -q
```

The tests never call YouTube, Meta, Google or Anthropic.
