"""How sensitive a trending topic is, and what that means for THIS workspace.

A keyword check, not understanding: it looks for words about death, disasters, violence,
war, politics, religion, health scares, crime and legal cases (English plus common Hindi and
other Indian-language words). It errs on the side of caution: when in doubt a topic is flagged,
and the user decides.

What to do about a sensitive topic depends on who you are (workspace brand safety):
  newsroom  news organisations cover it, with verification and care
  standard  creators only with real expertise, never monetised or sensationalised
  strict    brands and businesses stay away: no posts or promotions tied to it
"""
import textutil

# category: (level, label, words). "sensitive" topics involve harm to people; "caution" ones divide people.
CATEGORIES = {
    "tragedy": ("sensitive", "Death or tragedy", """
        death deaths dead died dies dying killed kills rip condolences condolence mourns
        mourning funeral tragedy tragic demise suicide victim victims injured
        मौत निधन मृत्यु हादसा श्रद्धांजलि मृतक
    """),
    "disaster": ("sensitive", "Disaster or accident", """
        earthquake quake flood floods flooding cyclone hurricane typhoon tsunami landslide wildfire
        blaze crash crashes collapse collapsed explosion blast stampede derailed derailment
        drowned sinking accident accidents cloudburst drought heatwave
        बाढ़ भूकंप तूफान आग विस्फोट दुर्घटना
    """),
    "violence": ("sensitive", "Violence or crime", """
        murder murdered attack attacked attacks terror terrorist terrorism shooting gunfire stabbing
        stabbed rape raped assault assaulted kidnap kidnapped kidnapping abuse lynching riot riots
        hostage bomb bombing massacre
        हत्या आतंकी आतंकवाद बलात्कार हमला दंगा
    """),
    "conflict": ("sensitive", "War or conflict", """
        war wars missile missiles airstrike airstrikes invasion troops army military ceasefire
        clash clashes shelling militants insurgents hamas hezbollah nato
        युद्ध सेना
    """),
    "politics": ("caution", "Politics", """
        election elections polls vote votes voting voter minister ministers president
        parliament mla candidate protest protests
        opposition government governor ordinance cabinet bjp congress aap tmc dmk
        चुनाव मंत्री सरकार विपक्ष
    """),
    "religion": ("caution", "Religion", """
        religious religion communal temple mosque church gurdwara blasphemy hindu muslim christian sikh
        mandir masjid
    """),
    "health": ("caution", "Health scare", """
        outbreak pandemic epidemic virus covid infection infections dengue malaria cholera hospitalised
        hospitalized icu cancer recall recalled poisoning poisoned contaminated contamination adulteration
        adulterated toxic unsafe expired
    """),
    "legal": ("caution", "Legal case or scandal", """
        court verdict arrested arrest arrests fir chargesheet bail jail lawsuit sued scam fraud raid raids
        probe investigation allegations alleged accused scandal controversy controversial banned ban
        गिरफ्तार घोटाला
    """),
}
_WORDS = {cat: [w for w in textutil.words(spec[2])] for cat, spec in CATEGORIES.items()}
# Two-word phrases that must match together
_PHRASES = {"tragedy": ["passed away", "passes away", "pass away", "death toll"], "disaster": ["fire accident", "fire breaks", "caught fire"],
            "politics": ["lok sabha", "rajya sabha", "chief minister", "prime minister", "political party", "election campaign"]}
# Words that look alarming but are everyday in entertainment, sport and marketing.
_HARMLESS = {"attack": {"panic", "titans"}, "killed": {"it"}, "bomb": {"box", "office", "photo"},
             "crash": {"course", "diet"}, "war": {"star", "price", "console", "wars"}, "wars": {"star"},
             "virus": {"antivirus"}, "dead": {"walking", "redemption"}, "president": {"club", "company"}}

LEVEL_ORDER = {"safe": 0, "caution": 1, "sensitive": 2}


def classify(*texts):
    """{"level": "safe"|"caution"|"sensitive", "categories": [ids], "labels": [...], "matched": [words]}."""
    words = []
    for t in texts:
        words += textutil.words(t or "")
    present = set(words)
    joined = " ".join(words)
    level, cats, matched = "safe", [], []
    for cat, ws in _WORDS.items():
        hits = [w for w in ws if w in present and not (_HARMLESS.get(w, set()) & present)]
        hits += [ph for ph in _PHRASES.get(cat, []) if f" {ph} " in f" {joined} "]
        if hits:
            cats.append(cat)
            matched += hits[:3]
            if LEVEL_ORDER[CATEGORIES[cat][0]] > LEVEL_ORDER[level]:
                level = CATEGORIES[cat][0]
    return {"level": level, "categories": cats, "labels": [CATEGORIES[c][1] for c in cats],
            "matched": sorted(set(matched))[:6]}


# (safety policy, level) -> (action, short label, advice)
ADVICE = {
    ("newsroom", "sensitive"): ("care", "Cover with care",
        "Verify with official sources before publishing, avoid speculation and graphic thumbnails, "
        "don't name victims before families are informed, and update the story as facts change."),
    ("newsroom", "caution"): ("care", "Cover with balance",
        "Present facts and all sides, attribute claims, and keep opinion clearly labelled."),
    ("newsroom", "safe"): ("go", "Good to cover", "Move fast: check whether competitors have it already."),
    ("standard", "sensitive"): ("avoid", "Avoid unless it's your field",
        "Don't make content about this unless you have real expertise. Never monetise, joke about or "
        "use tragedy for views. If you do respond, be respectful and point to reliable sources."),
    ("standard", "caution"): ("care", "Only if it fits your niche",
        "Share an informed view only if it relates to your niche; expect strong reactions in comments."),
    ("standard", "safe"): ("go", "Good to join", "Add your own angle while interest is high."),
    ("strict", "sensitive"): ("avoid", "Stay away",
        "Don't post about this or tie any offer, product or hashtag to it. Pause scheduled promotional "
        "posts if they could look insensitive while this is in the news."),
    ("strict", "caution"): ("avoid", "Avoid as a brand",
        "Brands taking sides on politics, religion or legal cases often lose customers. Skip it unless "
        "it directly affects your customers (e.g. a rule change you must explain)."),
    ("strict", "safe"): ("go", "Good to join", "A light, relevant tie-in can work. Keep it on-brand and useful."),
}


def advice(level, safety):
    action, label, text = ADVICE[(safety if safety in ("newsroom", "standard", "strict") else "standard", level)]
    return {"action": action, "label": label, "advice": text}
