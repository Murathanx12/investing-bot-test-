"""T13 -- the fantasy transposition. Murat's test, as code.



THE IDEA, AND WHY IT BEATS THE YEAR-CANARY

==========================================

A canary DETECTS memorisation: ask the model what year it is reading and see if

it knows. Transposition REMOVES the thing being memorised. There is no 2016 to

remember if the story is set in 2051 in the orbital-cooling industry, and no

Micron to remember if the company is "Vantor Systems".



What survives a rewrite is the SHAPE of the situation: a demand shock, a supply

constraint, a lender pulling funding, a regulator, a war, a consensus that is

very high, a company doing one thing differently. If the decider can turn that

shape into a good number, it is reading rather than remembering. That is the

cleanest available test of the claim that an LLM adds anything to a screen.



THREE RULES, OR IT LEAKS

========================

1. **The rewriter is point-in-time too.** It sees only that window's items --

   never a later item, never a price. A rewriter that knows how the story ended

   writes the ending into the tone, and the decider then reads the ending.

2. **One mapping per era, frozen, built in CODE and not by the model.** The

   same real entity gets the same fantasy name in every window of an era, so

   the decider can follow a company across time -- and a model inventing names

   per call could not give it that. The map is hashed and is never shown to the

   decider.

3. **Magnitudes survive, nouns do not.** "+40% consensus upside", "revenue

   -18%", "third guidance cut in a year" pass through untouched. The numbers

   are the information; the nouns are the leak. `magnitudes_preserved` checks

   this on every rewrite and a window that fails is DROPPED, not repaired.



THE ARMS

========

    real          the original text, names and year intact -- the memory-full arm

    real_anon     entities stripped, year and industry left in

    fantasy       transposed: new year, new industry, new entities



`real - fantasy` is how much of the model's performance was memory or sector

prior. The fantasy arm is the claim; the others are the controls.



AND THE NULLS, which are what stop a positive from being a coincidence

    shuffled      the same decisions paired to another window's outcome

    basket        equal weight over every name in the era -- "better than WHAT"

    numbers_only  the window's NUMBERS with the prose deleted. If this does as

                  well as `fantasy`, the prose adds nothing and the whole

                  exercise has answered itself.



"I DON'T KNOW" IS RETIRED

=========================

The decider returns p_up / exp_return / downside / confidence / horizon /

reason for every name, every time. Uncertainty is `p_up` near 0.5 with low

confidence -- never a refusal. Then the CHOOSING is code: rank by the declared

personality, take the top k, and grade two separate things, because they fail

separately. Wealth asks whether the picks made money. Calibration asks whether

70% meant 70%. A model that is honest about its uncertainty and still ranks

well is the goal; a model that is confident and wrong is what the reliability

table exposes.



NOTHING HERE PLACES AN ORDER.

"""

from __future__ import annotations



import hashlib

import json

import re



SCHEMA = "transpose-1"



DECIDER_KEYS = ("p_up_21d", "exp_return", "downside_5pct", "confidence",

                "horizon", "reason")



#: Personalities are RANKINGS, in code. No prose ranks anything.

PERSONALITY_LAMBDA = {"balanced": 1.0, "aggressive": 0.25}



ARMS = ("real", "real_anon", "fantasy", "numbers_only")

NULLS = ("shuffled", "basket")



#: Fantasy vocabularies. Fixed lists rather than model-invented names, so the

#: same real entity maps to the same fantasy one in every window of an era --

#: which is what lets the decider follow a company through time at all.

FANTASY_INDUSTRIES = [

    "orbital cooling", "deep-sea lattice mining", "atmospheric carbon weaving",

    "neural prosthetics", "fusion containment", "synthetic protein foundries",

    "quantum timing", "arcology construction", "closed-loop water reclamation",

    "asteroid volatiles", "photonic logistics", "biofilm agriculture",

    "cryo-transport", "gravitic surveying", "spectral advertising",

    "regolith refining", "vertical kelp", "isotope separation",

    "swarm inspection", "memory-glass fabrication",

]

FANTASY_STEMS = [

    "Vantor", "Kessel", "Ombra", "Delune", "Ravik", "Thal", "Ixara", "Corvane",

    "Merion", "Solvane", "Attic", "Yurest", "Brakhem", "Nessa", "Olvid",

    "Praxa", "Quenlo", "Rhodane", "Sable", "Turin", "Umbriel", "Verdant",

    "Wexley", "Xanthe", "Ythera", "Zephrin", "Ardent", "Bellico", "Cindral",

    "Doram", "Elmire", "Fenwick", "Galvane", "Hesper", "Icarel", "Jorune",

]

FANTASY_SUFFIXES = ["Systems", "Works", "Dynamics", "Holdings", "Industries",

                    "Collective", "Foundry", "Consortium", "Labs", "Union"]

FANTASY_PLACES = ["Meridian", "Kalthos", "New Ashen", "Perrine", "Sunder",

                  "Vellich", "Otrant", "Hallow Reach", "Dun Cairn", "Ferros"]



#: Years that are unmistakably not the present. A rewrite set in 2027 is a

#: rewrite the model can still date.

FANTASY_YEAR_BASE = 2051





def _rng(seed_text: str):

    """A deterministic generator seeded from text, so a map rebuilt from the

    same era and seed is byte-identical. `random.seed(str)` is stable across

    runs but NOT across Python versions; a hash digest is stable across both."""

    import random

    h = hashlib.sha256(seed_text.encode("utf-8")).hexdigest()

    return random.Random(int(h[:16], 16))





def build_entity_map(symbols: list[str], sectors: list[str], *, era: str,

                     seed: str = "aegis-t13") -> dict:

    """The frozen mapping for one era. Built in code; never shown to the decider.



    Deterministic by construction: the same (era, seed, sorted inputs) rebuild

    the same map, so a lost map file is recoverable and two machines agree.

    """

    rng = _rng(f"{seed}|{era}")

    syms = sorted(set(s for s in symbols if s))

    secs = sorted(set(s for s in sectors if s))



    stems = FANTASY_STEMS[:]

    rng.shuffle(stems)

    sufs = FANTASY_SUFFIXES[:]

    companies: dict[str, str] = {}

    for i, s in enumerate(syms):

        stem = stems[i % len(stems)]

        suf = sufs[(i // len(stems)) % len(sufs)]

        # A second pass round the stem list must not collide with the first.

        name = f"{stem} {suf}" if i >= len(stems) else f"{stem} {rng.choice(sufs)}"

        while name in companies.values():

            suf = sufs[(sufs.index(suf) + 1) % len(sufs)]

            name = f"{stem} {suf}"

        companies[s] = name



    inds = FANTASY_INDUSTRIES[:]

    rng.shuffle(inds)

    industries = {s: inds[i % len(inds)] for i, s in enumerate(secs)}



    places = FANTASY_PLACES[:]

    rng.shuffle(places)



    payload = {

        "schema": SCHEMA, "era": era, "seed": seed,

        "year_offset": FANTASY_YEAR_BASE - int(era[:4]),

        "companies": companies,

        "industries": industries,

        "places": places,

        "note": ("GRADER ONLY. The decider never sees this file. It is built in code "

                 "rather than by the rewriter so that one real company keeps one "

                 "fantasy name across every window of the era -- which is the only "

                 "way the decider can follow a name through time."),

    }

    payload["sha256"] = hashlib.sha256(

        json.dumps({k: v for k, v in payload.items() if k != "sha256"},

                   sort_keys=True).encode("utf-8")).hexdigest()

    return payload





#: A number, with optional sign, thousands separators, decimals and a percent.

_NUM = re.compile(r"[-+]?\$?\d[\d,]*(?:\.\d+)?%?")

_YEARISH = re.compile(r"^(19|20)\d{2}$")



#: DATES ARE NOT MAGNITUDES, and stripping them is not optional.

#:

#: The first version of this checker failed most good rewrites, and the reason

#: was our own header line. `[2025-10-27]` matches the number pattern three

#: times -- 2025 (dropped as a year), then `-10` and `-27` as SIGNED NUMBERS.

#: A correct rewrite moving that header to `[2051-11-17]` therefore looked like

#: three magnitudes dropped and three invented, and the window was discarded.

#: The drop was not random either: bundles with more dated items failed more

#: often, which is to say the windows carrying the most information were the

#: ones most likely to be thrown away.

#: The month alternation carries NO trailing `[a-z]*`, and that is the whole
#: reason it is written out longhand. The first version used `(?:Jan|Feb|Mar|
#: ...)[a-z]*` to catch full month names, and "Mar" then matched inside
#: "Margin" -- so "Margin 31%" was stripped as a date and a real magnitude
#: disappeared from one side of the comparison. Long forms are listed before
#: their abbreviations so "March" matches as itself.
_MONTHS = r"January|February|March|April|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept|Sep|Oct|Nov|Dec|May"
_DATEISH = re.compile(
    r"\b(19|20)\d{2}[-/]\d{1,2}[-/]\d{1,2}\b"                     # 2025-10-27
    r"|\b\d{1,2}[-/]\d{1,2}[-/](19|20)\d{2}\b"                     # 27/10/2025
    r"|\b(?:" + _MONTHS + r")\.?\s+\d{1,2}\b"                      # Dec. 13
    r"|\b\d{1,2}\s+(?:" + _MONTHS + r")\b",                        # 13 December
    re.I)


def strip_dates(text: str) -> str:

    """Remove calendar dates so their day and month numbers are not read as

    magnitudes. Years are handled separately by `years_in`."""

    return _DATEISH.sub(" <DATE> ", text or "")





def numbers_in(text: str) -> list[str]:

    """Every magnitude in the text, normalised, with DATES and YEARS excluded.



    Years and dates are excluded on purpose: the whole point of the rewrite is

    to move them, so counting them as magnitudes would fail every good rewrite

    and pass none. Years are checked separately by `years_in`.

    """

    out = []

    for m in _NUM.findall(strip_dates(text or "")):

        raw = m.strip()

        core = raw.lstrip("+-$").rstrip("%").replace(",", "")

        if _YEARISH.match(core):

            continue

        if not core:

            continue

        try:

            val = float(core)

        except ValueError:

            continue

        pct = raw.endswith("%")

        neg = raw.startswith("-")

        out.append(f"{'-' if neg else ''}{val:g}{'%' if pct else ''}")

    return sorted(out)





def years_in(text: str) -> set[int]:

    return {int(m) for m in re.findall(r"\b(19\d{2}|20\d{2})\b", text or "")}





def magnitudes_preserved(original: str, rewritten: str) -> dict:

    """Did the rewrite keep the numbers? Multiset comparison, both directions.



    DROPPED numbers mean the rewriter deleted information the decider needs.

    ADDED numbers are worse: the rewriter invented a magnitude, and the decider

    would then be reading a fact that never happened.

    """

    a, b = numbers_in(original), numbers_in(rewritten)

    from collections import Counter

    ca, cb = Counter(a), Counter(b)

    dropped = sorted((ca - cb).elements())

    added = sorted((cb - ca).elements())

    return {"ok": not dropped and not added,

            "n_original": len(a), "n_rewritten": len(b),

            "dropped": dropped[:20], "added": added[:20],

            "n_dropped": len(dropped), "n_added": len(added)}





def leak_check(rewritten: str, *, real_symbols: list[str], real_years: set[int],

               extra_terms: list[str] | None = None) -> dict:

    """Did a real ticker, a real year, or a banned term survive the rewrite?



    A rewrite that still says "Micron" or "2016" has not transposed anything,

    and one leaked token is enough to let a model date the whole window.

    """

    text = rewritten or ""

    upper = text.upper()

    tick = [s for s in real_symbols

            if re.search(rf"\b{re.escape(s.upper())}\b", upper)]

    yrs = sorted(years_in(text) & real_years)

    terms = [t for t in (extra_terms or [])

             if t and re.search(rf"\b{re.escape(t.lower())}\b", text.lower())]

    return {"clean": not tick and not yrs and not terms,

            "tickers": tick, "years": yrs, "terms": terms}





def rank(decisions: list[dict], *, personality: str = "balanced",

         k: int = 5) -> list[dict]:

    """CODE RANKS. No prose ranks anything, ever.



    balanced   `exp_return - 1.00 x |downside_5pct|`

    aggressive `p_up x exp_return`  -- the spec's second form, which does not

               subtract the bad case at all and is meant not to.



    A decision missing a number it needs ranks LAST, never at zero: a zero would

    let an unmeasured name outrank a measured negative one.

    """

    lam = PERSONALITY_LAMBDA.get(personality)

    if lam is None:

        raise ValueError(f"unknown personality {personality!r}")



    def value(d: dict) -> float:

        er, dn, p = d.get("exp_return"), d.get("downside_5pct"), d.get("p_up_21d")

        if personality == "aggressive":

            return float("-inf") if er is None or p is None else float(p) * float(er)

        if er is None or dn is None:

            return float("-inf")

        return float(er) - lam * abs(float(dn))



    scored = [dict(d, rank_value=value(d)) for d in decisions]

    scored.sort(key=lambda d: -d["rank_value"])

    return [d for d in scored[:k] if d["rank_value"] != float("-inf")]





def calibration(decisions: list[dict], outcomes: dict[str, float], *,

                bins: int = 10) -> dict:

    """Brier score and a reliability table. Separate from wealth, on purpose.



    A model can rank well and be badly calibrated (it knows the order and not

    the odds) or be well calibrated and rank badly (it knows the odds and they

    are all the same). Those are different failures with different fixes, and

    one number reporting both would hide whichever is the smaller.

    """

    pairs = [(float(d["p_up_21d"]), 1.0 if outcomes[d["key"]] > 0 else 0.0)

             for d in decisions

             if d.get("p_up_21d") is not None and d.get("key") in outcomes]

    if not pairs:

        return {"n": 0, "verdict": "NOT GRADEABLE",

                "why": "no decision had both a probability and a resolved outcome"}

    brier = sum((p - y) ** 2 for p, y in pairs) / len(pairs)

    base = sum(y for _, y in pairs) / len(pairs)

    # The climatology benchmark: always predict the base rate. A Brier score

    # with nothing beside it is unreadable; this is what it must beat.

    brier_climate = sum((base - y) ** 2 for _, y in pairs) / len(pairs)

    table = []

    for i in range(bins):

        lo, hi = i / bins, (i + 1) / bins

        cell = [(p, y) for p, y in pairs if (lo <= p < hi or (i == bins - 1 and p == 1.0))]

        if not cell:

            continue

        table.append({"bin": f"{lo:.1f}-{hi:.1f}", "n": len(cell),

                      "mean_p": round(sum(p for p, _ in cell) / len(cell), 4),

                      "hit_rate": round(sum(y for _, y in cell) / len(cell), 4)})

    return {"n": len(pairs), "base_rate": round(base, 4),

            "brier": round(brier, 5), "brier_climatology": round(brier_climate, 5),

            "skill_vs_climatology": round(brier_climate - brier, 5),

            "reliability": table,

            "note": ("Brier is lower-is-better. `skill_vs_climatology` above zero means "

                     "the model beat always-predicting-the-base-rate, which is the only "

                     "benchmark a probability has.")}





def wealth(picks_by_date: dict[str, list[dict]], outcomes: dict[str, float]) -> dict:

    """Terminal wealth of the top-k, compounded date by date."""

    dates = sorted(picks_by_date)

    per_date, w = [], 1.0

    for d in dates:

        rs = [outcomes[p["key"]] for p in picks_by_date[d] if p.get("key") in outcomes]

        if not rs:

            continue

        r = sum(rs) / len(rs)

        per_date.append({"date": d, "n": len(rs), "ret": round(r, 5)})

        w *= (1.0 + r)

    if not per_date:

        return {"n_dates": 0, "verdict": "NOT GRADEABLE"}

    rs = [p["ret"] for p in per_date]

    mean = sum(rs) / len(rs)

    if len(rs) > 1:

        var = sum((x - mean) ** 2 for x in rs) / (len(rs) - 1)

        t = mean / ((var / len(rs)) ** 0.5) if var > 0 else None

    else:

        t = None

    return {"n_dates": len(per_date), "terminal_wealth": round(w, 4),

            "mean_per_date": round(mean, 5),

            "t_stat": (round(t, 3) if t is not None else None),

            "hit_rate": round(sum(1 for x in rs if x > 0) / len(rs), 4),

            "per_date": per_date}





def parity(decisions_a: list[dict], decisions_b: list[dict]) -> dict:

    """REWRITER-PARITY. The check that decides whether the arm is admissible.



    The same window is rewritten twice. If the decider's probability moves MORE

    between two rewrites of one window than it does between different windows,

    the rewriter is supplying the variation and the arm is measuring the

    rewriter rather than the market. That is `REWRITER_LEAK` and it stops the

    run rather than being noted in a footnote.

    """

    a = {d["key"]: d.get("p_up_21d") for d in decisions_a}

    b = {d["key"]: d.get("p_up_21d") for d in decisions_b}

    both = [k for k in a if k in b and a[k] is not None and b[k] is not None]

    if len(both) < 5:

        return {"n": len(both), "verdict": "NOT GRADEABLE",

                "why": "fewer than 5 windows were rewritten twice"}

    within = [abs(float(a[k]) - float(b[k])) for k in both]

    vals = [float(a[k]) for k in both] + [float(b[k]) for k in both]

    mean = sum(vals) / len(vals)

    between = [abs(v - mean) for v in vals]

    mw = sum(within) / len(within)

    mb = sum(between) / len(between)

    ratio = mw / mb if mb > 0 else float("inf")

    return {

        "n_windows": len(both),

        "mean_abs_diff_between_rewrites": round(mw, 4),

        "mean_abs_deviation_across_windows": round(mb, 4),

        "ratio": round(ratio, 3),

        "verdict": "REWRITER_LEAK" if ratio >= 1.0 else "OK",

        "note": ("ratio >= 1 means two rewrites of the SAME window disagree as much as "

                 "different windows do -- the rewriter is the signal, not the market."),

    }





def shuffled_null(decisions: list[dict], outcomes: dict[str, float], *,

                  seed: str = "aegis-t13-null") -> dict[str, float]:

    """Null 1: the same decisions, paired to somebody else's outcome.



    Answers "does this ranking know anything about THIS name" -- as opposed to

    having found a month when everything went up. A ranking that scores as well

    on shuffled outcomes has found the calendar, not the company.

    """

    keys = sorted(k for k in outcomes if any(d.get("key") == k for d in decisions))

    vals = [outcomes[k] for k in keys]

    rng = _rng(seed)

    rng.shuffle(vals)

    return dict(zip(keys, vals))

