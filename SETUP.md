# Competitive Tracker: setup and API keys

Competitive Tracker compares a business's social media with its competitors' on **YouTube, Instagram, Facebook
and websites (RSS)**. It finds what's trending on the internet that fits the business, and turns all of it into
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
| `META_ACCESS_TOKEN` + `META_IG_USER_ID` | Instagram accounts | Free (needs a Meta app) |
| `META_ACCESS_TOKEN` | Facebook Pages | Free (needs Meta App Review for competitors' Pages) |
| *(none)* | Google Trends + Google News trends | Free |
| `ANTHROPIC_API_KEY` | AI-written briefing and content ideas on the Dashboard | Pay per use |

### YouTube

1. Go to https://console.cloud.google.com/, then create a project.
2. Open **APIs & Services → Library**, search for **YouTube Data API v3**, and click **Enable**.
3. Open **APIs & Services → Credentials → Create credentials → API key**.
4. Put it in `backend\.env` as `YOUTUBE_API_KEY=...`.

One refresh uses about 5 units per channel. The app stops by itself at `YOUTUBE_DAILY_BUDGET`.

### Instagram (Business Discovery)

Instagram doesn't let apps read other accounts directly. Competitors are read **through your own Instagram
professional account**, using Meta's Business Discovery API. Only **Business and Creator** accounts can be
tracked; personal and age-restricted accounts can't.

1. Make your own Instagram account a **Professional** account (Business or Creator) and link it to a **Facebook Page**
   (Instagram app → Settings → Account type and tools).
2. At https://developers.facebook.com/apps, create an app of type **Business**.
3. Add the **Instagram** product (choose *API setup with Facebook login*).
4. Get a token with these permissions: `instagram_basic`, `pages_show_list`, `pages_read_engagement`.
   Graph API Explorer can generate one for testing. For production, create a **System User** in
   Meta Business Settings and generate a token for it; system-user tokens don't expire.
   Meta changes permission names from time to time, so check the current
   [Business Discovery guide](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-facebook-login/business-discovery)
   before App Review.
5. Find your Instagram account ID: in Graph API Explorer, run
   `me/accounts?fields=instagram_business_account{id,username}` and copy `instagram_business_account.id`.
6. In `backend\.env`, set:
   ```
   META_ACCESS_TOKEN=...
   META_IG_USER_ID=1784...
   ```
7. While the app is in **Development mode**, it only works for people with a role on the app. Before other people
   use it, submit the permissions for **App Review**.

**What Instagram shows for competitors:** followers, and for each post the likes, comments and type
(Reel, photo, carousel). It also shows views for Reels only. Reach, saves and story data are private, so
Instagram posts are compared by **interactions** and **engagement per follower**, not by views.

### Facebook Pages

1. Use the same Meta app and token as above (add `pages_read_engagement`).
2. Your own Pages work right away. **Other businesses' Pages** need the **Page Public Content Access** feature:
   request it in App Review. Meta also requires **business verification**.
3. Until it's approved, adding a competitor Page shows "Meta refused access". This is expected.

**What Facebook shows for public Pages:** followers, and for each post the reactions (counted as likes),
comments and shares. Reach and video views are private Page Insights.

### Internet trends (no key)

- **Google Trends**: Google's daily "Trending now" searches for the workspace's country (set in Workspace settings).
- **Google News**: how much is being published about each workspace topic in the last 7 days, and whether it's rising.
  Google's RSS terms allow personal and non-commercial use only. For a commercial product, set `TRENDS_GOOGLE_NEWS=0`
  and add a licensed news API later.
- **YouTube Trending**: the official chart for the country and the industry's video category. Needs the YouTube key.

Trends are checked on every Refresh (at most once an hour) or with **Check trends now** on the Trends page.

### AI briefing (optional)

Set `ANTHROPIC_API_KEY` (from https://console.anthropic.com/). A **Write AI briefing** button then appears on
the Dashboard. Claude only receives the numbers already on the page and is told not to add anything else.
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
  This makes a small shop and a big brand comparable. YouTube uses views; Instagram and Facebook use interactions.
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
