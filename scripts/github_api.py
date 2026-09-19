"""GitHub data client — stdlib only, so CI needs no pip install.

Two data sources, and they behave very differently:

  * The REST API (`api.github.com`) — documented, paginated, and rate limited to
    60 req/hr unauthenticated (1000/hr with the workflow's GITHUB_TOKEN).
  * `github.com/users/<user>/contributions` — an UNDOCUMENTED HTML endpoint that
    returns the contribution calendar as `data-date` / `data-level` attributes.
    It is the only way to get the calendar without GraphQL, which returns 403
    unauthenticated. Because it is undocumented it may change without notice, so
    it is isolated in `get_contributions()` and its failure is survivable.

Design rule for every function here: a partial answer is worse than yesterday's
answer. On rate-limit or network failure we fall back to the last-good cache
rather than returning zeros, because a stats card that silently renders "0 repos"
is a worse outcome than a card showing slightly stale numbers.
"""

import json
import os
import re
import time
import urllib.error
import urllib.request

API = "https://api.github.com"
CONTRIB = "https://github.com/users/{user}/contributions"
CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     ".cache", "github.json")

UA = "Mr-Destroyer-profile-readme/1.0"


class ApiError(RuntimeError):
    pass


# --- cache -----------------------------------------------------------------

def _load_cache():
    try:
        with open(CACHE) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _save_cache(data):
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    tmp = CACHE + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
    os.replace(tmp, CACHE)


# --- http ------------------------------------------------------------------

def _get(url, accept="application/vnd.github+json", timeout=25):
    """GET with a token when one is available. Raises ApiError on failure."""
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": accept,
    })
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
            remaining = resp.headers.get("X-RateLimit-Remaining")
            if remaining is not None and int(remaining) <= 1:
                # Let the caller know we are about to be cut off.
                raise ApiError(f"rate limit nearly exhausted (remaining={remaining})")
            return body
    except urllib.error.HTTPError as e:
        raise ApiError(f"HTTP {e.code} for {url}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ApiError(f"network failure for {url}: {e}") from e


def _get_json(url):
    return json.loads(_get(url))


# --- public API ------------------------------------------------------------

def get_user(login):
    return _get_json(f"{API}/users/{login}")


def get_repos(login, include_forks=False):
    """All repos, newest-updated first. Forks are excluded by default.

    Forks are excluded because a fork is not evidence of work — including them
    would inflate the language breakdown with code he did not write.
    """
    out, page = [], 1
    while page <= 5:  # 500 repos is far beyond any realistic profile
        batch = _get_json(
            f"{API}/users/{login}/repos?per_page=100&page={page}&sort=updated"
        )
        if not isinstance(batch, list) or not batch:
            break
        out.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    if not include_forks:
        out = [r for r in out if not r.get("fork")]
    return out


def get_languages(login, repos, limit=30):
    """Aggregate byte counts across repos, newest-updated first.

    Capped at `limit` repos to stay well inside the rate limit — the newest 30
    non-fork repos already characterise the stack, and the tail is mostly
    small scripts that would skew the distribution toward noise.
    """
    totals = {}
    for repo in repos[:limit]:
        name = repo.get("name")
        if not name:
            continue
        try:
            langs = _get_json(f"{API}/repos/{login}/{name}/languages")
        except ApiError:
            # Skip this repo rather than failing the whole breakdown.
            continue
        if isinstance(langs, dict):
            for lang, nbytes in langs.items():
                totals[lang] = totals.get(lang, 0) + int(nbytes)
    return totals


_CELL = re.compile(r'data-date="(\d{4}-\d{2}-\d{2})"[^>]*data-level="(\d)"')


def language_repo_counts(repos):
    """Repos per primary language, most first.

    This is the metric the profile displays, and the choice is deliberate.
    Byte counts are NOT a fair picture here: a single vendored 15 MB JavaScript
    tool (`ufonet`) outweighs every line of Python he has written, so a
    byte-weighted chart would lead with JavaScript and misrepresent the profile.
    Counting repos by primary language answers the question a reader actually
    has — "what does this person build?" — and is not distorted by one imported
    codebase.
    """
    counts = {}
    for r in repos:
        lang = r.get("language")
        if lang:
            counts[lang] = counts.get(lang, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def get_contributions(login):
    """The contribution calendar, as a list of (date, level 0-4).

    UNDOCUMENTED endpoint — returns 371 cells (53 weeks x 7 days). This is the
    fragile dependency in the whole pipeline, so it is isolated here and its
    failure is handled by the caller keeping last-good output.

    DOCUMENT ORDER IS DAY-MAJOR, NOT WEEK-MAJOR. This is the trap in this
    endpoint and it is not obvious, because the dates are ascending either way:

        cell[i] has day-index (i // 53) and week-index (i % 53)

    so the first 53 cells are all Sundays (stepping 7 days apart), the next 53
    are all Mondays, and so on. Verified against the live endpoint: all 371
    cells satisfy `i == day_index * 53 + week_index`, where those indices come
    from the row's own `contribution-day-component-<day>-<week>` id.

    Anything that consumes this list positionally must therefore NOT assume
    week-major order — see the note in `generate.render_snake()`. We normalise
    to chronological order here so that every caller gets the obvious thing,
    and so the fragile parsing knowledge stays in one place.
    """
    html = _get(CONTRIB.format(user=login), accept="text/html")
    cells = _CELL.findall(html)
    if not cells:
        # Attribute order is not guaranteed; try the reversed pairing.
        alt = re.compile(r'data-level="(\d)"[^>]*data-date="(\d{4}-\d{2}-\d{2})"')
        cells = [(d, lv) for lv, d in alt.findall(html)]
    if not cells:
        raise ApiError("contribution calendar parsed to zero cells")
    # Sort by date so callers receive oldest-first chronological order.
    return _chronological([(d, int(lv)) for d, lv in cells])


def _chronological(cells):
    """Sort (date, level) cells oldest-first, tolerating cached JSON lists.

    The cache round-trips tuples as two-element lists, so this must not assume
    a tuple type. Sorting is idempotent, which is what lets it be applied both
    to freshly fetched data and to whatever the cache hands back.
    """
    out = []
    for cell in cells:
        if isinstance(cell, (list, tuple)) and len(cell) == 2:
            out.append((str(cell[0]), int(cell[1])))
    return sorted(out, key=lambda c: c[0])


def get_streak(contributions):
    """Current and longest streak, computed locally from the calendar.

    `contributions` must be in CHRONOLOGICAL order (oldest first) — a simple
    scan is only correct in that order. `get_contributions()` guarantees this.

    This scan is why the day-major quirk matters: run against raw endpoint
    order it reports a "current streak" of 3 for this profile, because the last
    three cells are three consecutive *Saturdays*. The true value is 1.
    """
    longest = cur = 0
    longest_end = None
    for date, level in contributions:
        if level > 0:
            cur += 1
            if cur > longest:
                longest, longest_end = cur, date
        else:
            cur = 0
    # Current streak: trailing run, allowing today to be empty (a day still in
    # progress should not read as a broken streak).
    tail = 0
    for _, level in reversed(contributions):
        if level > 0:
            tail += 1
        elif tail == 0:
            continue  # today not yet counted
        else:
            break
    return {"current": tail, "longest": longest, "longest_end": longest_end}


def collect(login, cache_key=None):
    """Gather everything the generator needs, with last-good fallback.

    Returns (data, warnings). `warnings` is non-empty when any source failed and
    cached values were substituted — the caller prints them so a silent
    degradation is visible in the Action log.
    """
    # GitHub logins are case-insensitive, but a dict key is not: caching under
    # the login as typed means `--user Mr-Destroyer` and `--user mr-destroyer`
    # populate two separate entries, and a run under a new casing starts with an
    # EMPTY cache — which silently defeats the last-good fallback at exactly the
    # moment it is needed. Normalise so one user is always one cache entry.
    key = (cache_key or login).lower()
    cache = _load_cache()
    prev = cache.get(key, {})
    warnings = []
    data = {}

    def attempt(name, fn, default):
        try:
            data[name] = fn()
        except (ApiError, ValueError) as e:
            if name in prev:
                data[name] = prev[name]
                warnings.append(f"{name}: {e} — kept cached value")
            else:
                data[name] = default
                warnings.append(f"{name}: {e} — no cache, using default")

    attempt("user", lambda: get_user(login), {})

    try:
        repos = get_repos(login)
        data["repos"] = repos
    except (ApiError, ValueError) as e:
        repos = prev.get("repos", [])
        data["repos"] = repos
        warnings.append(f"repos: {e} — kept cached value")

    attempt("languages", lambda: get_languages(login, repos), {})
    attempt("contributions", lambda: get_contributions(login), [])

    # A cache written before the day-major fix holds cells in endpoint order.
    # Serving that unchanged would keep the old wrong streak alive indefinitely,
    # so normalise on read as well as on fetch.
    data["contributions"] = _chronological(data.get("contributions") or [])

    data["streak"] = get_streak(data["contributions"]) if data["contributions"] else {
        "current": 0, "longest": 0, "longest_end": None
    }
    data["fetched_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # Merge per field, not wholesale. Writing the whole entry unconditionally
    # would let a run where `user` failed but `repos` succeeded overwrite a good
    # cached `user` with the empty default — i.e. the cache would decay toward
    # empty precisely under the rate-limiting it exists to survive. A field is
    # only replaced when this run actually produced a non-empty value for it.
    merged = dict(prev)
    for field in ("user", "repos", "languages", "contributions"):
        value = data.get(field)
        if value:
            merged[field] = value
        elif field not in merged:
            merged[field] = value if value is not None else {}

    # Never persist an entry that carries no data at all.
    if any(merged.get(f) for f in ("user", "repos", "contributions")):
        cache[key] = merged
        _save_cache(cache)
    else:
        warnings.append("nothing fetched and no usable cache — not writing cache")

    return data, warnings


def summarize(data):
    """Derive the headline numbers, counting stars across non-fork repos only."""
    repos = data.get("repos") or []
    stars = sum(int(r.get("stargazers_count") or 0) for r in repos)
    user = data.get("user") or {}
    return {
        "repos": len(repos),
        "stars": stars,
        "followers": int(user.get("followers") or 0),
        "contributions": sum(1 for _, lv in (data.get("contributions") or []) if lv > 0),
        "streak": data.get("streak") or {"current": 0, "longest": 0},
    }
