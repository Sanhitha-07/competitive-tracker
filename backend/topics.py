"""Topic coverage map: which topics competitors post about, and how much of that we cover.

Works for any niche: topics come from the words and phrases in titles and creator tags
(nothing is pre-defined per industry), plus the topics/keywords the user configured.

A post may belong to several topics. This is keyword matching, not understanding: two posts
about the same thing in different words are not joined, and that is shown as a limitation.

Works on any objects with these attributes:
  account: id, name, is_us
  post:    id, competitor_id, title, tags, published_at
"""
import re
from collections import defaultdict

# Generic words that say nothing about the topic, in any niche.
STOPWORDS = set("""
a an the and or of in on at to for from by with as is are was were be been being after before over under into
onto its it this that these those there here new says said amid live updates update news today watch video videos
vs versus not no yes you your yours we our ours they their them he she his her him i me my mine us
will would can could should may might must do does did done just only also very more most much many
how why what when where which who whom whose all any some every each other another than then so too
get got gets make makes made take takes took go goes going went full official part episode ep vlog shorts short
reel reels clip clips day days week weeks month year years time times one two three first last best top
ever really need know thing things way ways like about out up down off back still now
beautiful amazing awesome insane crazy ultimate epic shocking finally actually honest real big small good bad
great better worst never always try tried trying using use used here's every everything something nothing
hai ki ka ke se mein aur ko bhi
""".split())

MIN_ACCOUNTS = 2       # a discovered topic needs posts from at least 2 different accounts...
MIN_POSTS_ONE = 3      # ...or at least 3 posts from one competitor
MAX_TOPICS = 60
BOILERPLATE_SHARE = 0.6   # a term on more than 60% of one account's posts is its branding...
BOILERPLATE_MIN_POSTS = 5  # ...judged only for accounts with at least 5 posts in the period


def _words(text):
    return [w for w in re.findall(r"[^\W_]+", text.lower()) if len(w) >= 3 and not w.isdigit()]


def _account_words(accounts):
    """Words from account names, so 'NDTV' or a creator's own name doesn't become a 'topic'."""
    out = set()
    for a in accounts:
        out.update(_words(a.name))
    return out


def post_terms(post, skip):
    """Single words and two-word phrases from the title, plus the creator's tags."""
    title, tags = _title_and_tag_terms(post, skip)
    return title | tags


def _title_and_tag_terms(post, skip):
    words = [w for w in _words(post.title) if w not in STOPWORDS and w not in skip]
    title = set(words)
    title.update(f"{a} {b}" for a, b in zip(words, words[1:]))
    tags = set()
    for tag in (getattr(post, "tags", None) or []):
        tag_words = [w for w in _words(tag) if w not in STOPWORDS and w not in skip]
        if 1 <= len(tag_words) <= 3:
            tags.add(" ".join(tag_words))
    return title, tags - title


def _matches(phrase, post):
    text = " ".join([post.title, *(getattr(post, "tags", None) or [])]).lower()
    return re.search(r"(?<![^\W_])" + re.escape(phrase.lower()) + r"(?![^\W_])", text) is not None


def confidence(competitor_posts, competitor_accounts, our_total):
    """How much to trust a topic comparison, from the sample size alone."""
    if competitor_posts >= 8 and competitor_accounts >= 3 and our_total >= 20:
        return "high"
    if competitor_posts >= 4 and competitor_accounts >= 2 and our_total >= 5:
        return "medium"
    return "low"


def coverage_map(posts, accounts, tracked=(), relative=None, questions=None):
    """Return topic rows sorted by how much competitors post about them.

    tracked:   topics/keywords the user configured; always included, even with no posts.
    relative:  {post_id: views ÷ that account's median}, when the platform has views.
    questions: list of objects with .text, used to count audience questions per topic.
    """
    relative = relative or {}
    questions = questions or []
    by_id = {a.id: a for a in accounts}
    us_ids = {a.id for a in accounts if a.is_us}
    skip = _account_words(accounts)
    our_total = sum(1 for p in posts if p.competitor_id in us_ids)

    term_posts = defaultdict(set)
    account_terms = defaultdict(lambda: defaultdict(int))
    account_posts = defaultdict(int)
    post_terms_of = {}
    for p in posts:
        if p.competitor_id not in by_id:
            continue
        title, tags = _title_and_tag_terms(p, skip)
        post_terms_of[p.id] = title | tags
        account_posts[p.competitor_id] += 1
        for t in tags:
            account_terms[p.competitor_id][t] += 1
    # Tags an account puts on almost every post (its name, "vlog", its city) are branding,
    # not topics: don't count them for that account. Title words are never dropped, so an
    # account's real core topic still counts.
    boilerplate = {
        (aid, t) for aid, counts in account_terms.items() if account_posts[aid] >= BOILERPLATE_MIN_POSTS
        for t, n in counts.items() if n / account_posts[aid] > BOILERPLATE_SHARE
    }
    for p in posts:
        for t in post_terms_of.get(p.id, ()):
            if (p.competitor_id, t) not in boilerplate:
                term_posts[t].add(p.id)
    tracked_l = {t.strip().lower(): t.strip() for t in tracked if t and t.strip()}
    for low in tracked_l:
        term_posts[low] = {p.id for p in posts if p.competitor_id in by_id and _matches(low, p)}

    post_by_id = {p.id: p for p in posts}

    def build(term, ids):
        rows = [post_by_id[i] for i in ids]
        ours = [p for p in rows if p.competitor_id in us_ids]
        theirs = [p for p in rows if p.competitor_id not in us_ids]
        # Count by name, so one competitor's website + YouTube channel count as one competitor.
        comp_names = sorted({by_id[p.competitor_id].name for p in theirs})
        rel = sorted(relative[p.id] for p in theirs if relative.get(p.id) is not None)
        q = [x for x in questions if re.search(r"(?<![^\W_])" + re.escape(term) + r"(?![^\W_])", x.text.lower())]
        return {
            "topic": tracked_l.get(term, term),
            "tracked": term in tracked_l,
            "our_posts": len(ours),
            "competitor_posts": len(theirs),
            "competitors": comp_names,
            "per_competitor": round(len(theirs) / len(comp_names), 1) if comp_names else 0,
            "median_relative": rel[len(rel) // 2] if rel else None,
            "relative_sample": len(rel),
            "questions": len(q),
            "latest": max((p.published_at for p in rows), default=None),
            "post_ids": [p.id for p in sorted(rows, key=lambda p: p.published_at, reverse=True)],
        }

    topics = []
    for term, ids in term_posts.items():
        if term in tracked_l:
            topics.append(build(term, ids))
            continue
        accounts_here = {by_id[post_by_id[i].competitor_id].name for i in ids}
        comp_counts = defaultdict(int)
        for i in ids:
            if post_by_id[i].competitor_id not in us_ids:
                comp_counts[post_by_id[i].competitor_id] += 1
        if not comp_counts:
            continue  # only we post about it: not a competitive topic
        if len(accounts_here) >= MIN_ACCOUNTS or max(comp_counts.values()) >= MIN_POSTS_ONE:
            topics.append(build(term, ids))

    # Prefer the phrase over its single words when the phrase explains most of the word's posts.
    phrases = [t for t in topics if " " in t["topic"] and not t["tracked"]]
    drop = set()
    for t in topics:
        if " " in t["topic"] or t["tracked"]:
            continue
        n = len(t["post_ids"])
        for ph in phrases:
            if t["topic"] in ph["topic"].split() and len(ph["post_ids"]) >= 0.7 * n:
                drop.add(t["topic"])
                break
    topics = [t for t in topics if t["topic"] not in drop]

    for t in topics:
        t["status"] = _status(t)
        t["confidence"] = confidence(t["competitor_posts"], len(t["competitors"]), our_total)
    topics.sort(key=lambda t: (not t["tracked"], -(t["competitor_posts"] * len(t["competitors"])), t["topic"]))
    tracked_rows = [t for t in topics if t["tracked"]]
    return tracked_rows + [t for t in topics if not t["tracked"]][:MAX_TOPICS], our_total


def _status(t):
    """Plain description of coverage IN THE TRACKED DATA. Never 'untapped'."""
    comp = len(t["competitors"])
    if t["our_posts"] == 0 and comp == 0:
        return "no_posts_tracked"          # tracked keyword nobody in the dataset posted about
    if t["our_posts"] == 0:
        return "not_covered_by_you"
    if comp == 0:
        return "limited_competitor_coverage"
    if comp == 1 and t["competitor_posts"] <= 1:
        return "limited_competitor_coverage"
    if t["our_posts"] < 0.5 * t["per_competitor"]:
        return "covered_less"
    return "covered"


STATUS_LABELS = {
    "not_covered_by_you": "No posts from you in the tracked data",
    "covered_less": "You post about this less than competitors",
    "covered": "Covered",
    "limited_competitor_coverage": "Few tracked competitors cover this",
    "no_posts_tracked": "No tracked posts yet",
}
