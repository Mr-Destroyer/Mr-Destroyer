#!/usr/bin/env python3
"""Render the four data-driven assets: stats, languages, snake, projects.

Everything here is computed from live GitHub data, so the profile cannot claim
anything the API does not support. Output is deterministic for identical input —
the workflow commits these files daily, and a non-deterministic generator would
produce a spurious commit every day.

Usage:
    python3 scripts/generate.py [--user LOGIN] [--out assets] [--check]
"""

import argparse
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import github_api
import render as R
import theme

# Repos whose names read as jokes or noise get filtered from the showcase — the
# grid is the one place a visitor looks to judge the work, so it should not lead
# with a repo called "Fucker". Everything filtered here is still linked in the
# README's full project list; this only affects the featured card.
NOT_FEATURED = {"Fucker", "DDos_Zim", "FB-Hack"}


# --- stats -----------------------------------------------------------------

def render_stats(summary, user):
    W, H = 880, 150
    s = R.open_svg(W, H, extra_defs=R.sweep_gradient("sweep"))

    name = (user.get("name") or user.get("login") or "unknown")
    tiles = [
        ("REPOSITORIES", summary["repos"]),
        ("STARS EARNED", summary["stars"]),
        ("FOLLOWERS", summary["followers"]),
        ("ACTIVE DAYS", summary["contributions"]),
        ("CURRENT STREAK", summary["streak"].get("current", 0)),
    ]

    out = [s]
    out.append(R.text(28, 38, "// METRICS", size=11, fill=theme.ACCENT, spacing="2"))
    out.append(R.text(28, 62, name, size=17, weight=600))
    out.append(R.text(28, 82, "all figures computed from the live GitHub API",
                      size=11, fill=theme.MUTED))

    # Sweep highlight across the top rule — the one moving element on this card.
    out.append(f'<rect x="28" y="96" width="{W-56}" height="2" fill="#1E2A2E"/>')
    out.append(f'<rect x="28" y="96" width="{W-56}" height="2" fill="url(#sweep)"/>')

    colw = (W - 56) / len(tiles)
    for i, (label, value) in enumerate(tiles):
        cx = 28 + colw * i + colw / 2
        d = theme.stagger(i, base=0.15)
        out.append(R.text(cx, 128, f"{value:,}", size=26, weight=700,
                          fill=theme.ACCENT, anchor="middle", delay=d))
        out.append(R.text(cx, 145, label, size=9, fill=theme.MUTED,
                          anchor="middle", spacing="1.5", delay=d))
        if i:
            x = 28 + colw * i
            out.append(f'<line x1="{x:.0f}" y1="112" x2="{x:.0f}" y2="140" '
                       f'stroke="{theme.BORDER}" stroke-width="1"/>')

    out.append(R.close_svg())
    return "".join(out)


# --- languages -------------------------------------------------------------

def render_languages(counts):
    """Repos per primary language — see `language_repo_counts` for why not bytes."""
    rows = list(counts.items())[:7]
    rowh = 26
    H = 74 + max(1, len(rows)) * rowh
    W = 880
    s = R.open_svg(W, H)

    total = sum(counts.values())
    top = max((n for _, n in rows), default=1)

    out = [s]
    out.append(R.text(28, 36, "// PRIMARY LANGUAGE", size=11, fill=theme.ACCENT, spacing="2"))
    # `total` counts only repos with a detected language, which is fewer than the
    # repo total on the stats card (GitHub reports null for a repo it cannot
    # classify). Say so, or the two cards look like they disagree.
    if not total:
        # Keep the divisor below safe without letting the guard leak into the
        # caption — `or 1` on the total would render "across 1 repos", which is
        # a claim about the data rather than a fallback.
        out.append(R.text(28, 54, "language data unavailable this run",
                          size=11, fill=theme.MUTED))
        out.append(R.close_svg())
        return "".join(out)

    out.append(R.text(28, 54, f"by repository count, across {total} repos with a detected language",
                      size=11, fill=theme.MUTED))

    bar_x, bar_w = 176, 560
    for i, (lang, n) in enumerate(rows):
        y = 78 + i * rowh
        d = theme.stagger(i, base=0.12)
        out.append(R.text(28, y + 4, lang, size=12, fill=theme.TEXT, delay=d))
        out.append(R.bar(bar_x, y - 7, bar_w, 11, n / top, delay=d))
        out.append(R.text(bar_x + bar_w + 12, y + 4, f"{n}", size=12,
                          fill=theme.ACCENT, delay=d))
        out.append(R.text(bar_x + bar_w + 34, y + 4, f"{100*n/total:.0f}%",
                          size=11, fill=theme.MUTED, delay=d))

    out.append(R.close_svg())
    return "".join(out)


# --- snake -----------------------------------------------------------------

def _trace_path(points):
    """Connect points with orthogonal, rounded-corner segments.

    Straight diagonals between active cells turn the grid into a stock-price
    chart — the first version of this did exactly that and read as noise. Moving
    only horizontally then vertically, with a small radius on each corner, makes
    it read as a trace running through the grid instead.

    Returns (path_data, approximate_length) — the length drives the
    stroke-dashoffset draw-on, so it only needs to be an upper bound.
    """
    R = 4  # corner radius
    d = [f"M{points[0][0]:.0f} {points[0][1]:.0f}"]
    length = 0.0
    for i in range(1, len(points)):
        x0, y0 = points[i - 1]
        x1, y1 = points[i]
        dx, dy = x1 - x0, y1 - y0
        if abs(dx) < 0.5 and abs(dy) < 0.5:
            continue
        if abs(dy) < 0.5:  # horizontal run
            d.append(f"L{x1:.0f} {y1:.0f}")
        elif abs(dx) < 0.5:  # vertical run
            d.append(f"L{x1:.0f} {y1:.0f}")
        else:
            # Horizontal first, then vertical, with a rounded elbow. Radius is
            # clamped so short hops do not overshoot into a cusp.
            r = min(R, abs(dx) / 2, abs(dy) / 2)
            sx = 1 if dx > 0 else -1
            sy = 1 if dy > 0 else -1
            d.append(f"L{x1 - sx * r:.0f} {y0:.0f}")
            d.append(f"Q{x1:.0f} {y0:.0f} {x1:.0f} {y0 + sy * r:.0f}")
            d.append(f"L{x1:.0f} {y1:.0f}")
        length += abs(dx) + abs(dy)
    return " ".join(d), length + 1


def render_snake(contributions, weeks=53):
    """The real contribution grid with a snake traversing the active cells.

    `contributions` arrives oldest-first as (date, level). GitHub's grid is
    column-per-week, seven rows per column, Sunday at top.

    The mapping from a chronological list to (col, row) is by DATE, not by
    index. Deriving it from the index is the trap: the obvious `divmod(idx, 7)`
    is only correct for week-major input, and a date-sorted list is not that.
    It fails silently — the grid still has 371 cells and still looks like a
    contribution graph, but every cell sits in the wrong weekday row.

    The grid is genuinely sparse — most days are level 0 — so level 0 is drawn
    barely above the background. The card should read as calm and deliberate,
    not as a broken render.
    """
    CELL, GAP = 11, 3
    step = CELL + GAP
    LEFT, TOP = 28, 74
    W = LEFT * 2 + weeks * step
    H = TOP + 7 * step + 40

    s = R.open_svg(W, H, extra_defs=R.sweep_gradient("snakeSweep", dur=6.0))

    out = [s]
    out.append(R.text(28, 36, "// CONTRIBUTION HISTORY", size=11,
                      fill=theme.ACCENT, spacing="2"))

    # Empty input is reachable, not hypothetical: `collect()` substitutes an
    # empty list when the scrape fails and there is no cache to fall back on —
    # which is always the case in CI, where `.cache/` is gitignored and never
    # restored. Indexing into that crashed the whole run. Degrade to a card that
    # says so instead: a missing graph is a much better outcome than a failed
    # Action, and the text makes the gap visible rather than hiding it.
    if not contributions:
        out.append(R.text(28, 54, "contribution data unavailable this run",
                          size=11, fill=theme.MUTED))
        out.append(R.close_svg())
        return "".join(out)

    cells = contributions[-weeks * 7:] if len(contributions) > weeks * 7 else contributions

    active = sum(1 for _, lv in cells if lv > 0)
    out.append(R.text(28, 54, f"{active} active days across the last {weeks} weeks",
                      size=11, fill=theme.MUTED))

    # --- grid -------------------------------------------------------------
    # Anchor the columns on the most recent Saturday, which is the right edge
    # of GitHub's own calendar (their weeks run Sunday -> Saturday). Every cell
    # is then placed by how many whole weeks it sits before that anchor.
    def _weekend(d):
        """The Saturday ending the week that contains date `d`."""
        return d + datetime.timedelta(days=(5 - d.weekday()) % 7)

    last_date = datetime.date.fromisoformat(cells[-1][0])
    anchor = _weekend(last_date)

    order = []  # (cx, cy) for active cells, in reading order
    placed = 0
    for date_s, level in cells:
        d = datetime.date.fromisoformat(date_s)
        col = weeks - 1 - ((anchor - _weekend(d)).days // 7)
        if not 0 <= col < weeks:
            continue  # outside the window we are drawing
        # day 0 == Sunday at the top, matching GitHub
        row = (d.weekday() + 1) % 7
        x = LEFT + col * step
        y = TOP + row * step
        fill = theme.LEVELS[min(level, 4)]
        out.append(f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="2.5" '
                   f'fill="{fill}"><title>{date_s}: level {level}</title></rect>')
        placed += 1
        if level > 0:
            order.append((x + CELL / 2, y + CELL / 2))

    # A grid that silently drops cells is the failure mode this guards against.
    if placed != len(cells):
        raise ValueError(
            f"snake grid placed {placed} of {len(cells)} cells — "
            "the date-to-column mapping is wrong"
        )

    # --- snake ------------------------------------------------------------
    # A path through the active cells, drawn on with stroke-dashoffset (CSS,
    # verified working in the probe). Semi-transparent so it reads as a trace
    # over the data rather than hiding it.
    if len(order) > 1:
        d, _total_len = _trace_path(order)
        # pathLength="1" normalises the geometry so the CSS dash values can be
        # a plain 1 — no need to know the real path length. See render.open_svg.
        out.append(
            f'<path class="draw" pathLength="1" style="animation-duration:4.5s" '
            f'd="{d}" fill="none" stroke="{theme.ACCENT}" stroke-width="1.6" '
            f'stroke-linecap="round" stroke-linejoin="round" opacity="0.55"/>'
        )
        # The head: a single slow-pulsing dot, not a flashing one.
        hx, hy = order[-1]
        out.append(f'<circle cx="{hx:.0f}" cy="{hy:.0f}" r="3.5" fill="{theme.ACCENT}">'
                   f'<animate attributeName="r" values="3;4.5;3" dur="2.4s" '
                   f'repeatCount="indefinite"/></circle>')

    # --- legend -----------------------------------------------------------
    ly = TOP + 7 * step + 20
    out.append(R.text(28, ly, "less", size=9, fill=theme.MUTED))
    lx = 62
    for lv in range(5):
        out.append(f'<rect x="{lx}" y="{ly-9}" width="10" height="10" rx="2" '
                   f'fill="{theme.LEVELS[lv]}"/>')
        lx += 14
    out.append(R.text(lx + 4, ly, "more", size=9, fill=theme.MUTED))

    out.append(R.close_svg())
    return "".join(out)


# --- projects --------------------------------------------------------------

def render_projects(repos, limit=6):
    """Featured repos: highest stars first, ties broken by name for determinism."""
    picked = sorted(
        [r for r in repos if r.get("name") not in NOT_FEATURED],
        key=lambda r: (-(r.get("stargazers_count") or 0), r.get("name") or ""),
    )[:limit]

    rowh = 46
    H = 76 + max(1, len(picked)) * rowh + 8
    W = 880
    s = R.open_svg(W, H, extra_defs=R.sweep_gradient("projSweep", dur=7.0))

    out = [s]
    out.append(R.text(28, 36, "// SELECTED WORK", size=11, fill=theme.ACCENT, spacing="2"))
    if not picked:
        # Without this the card renders a header over empty space, which reads
        # as a broken image rather than as missing data.
        out.append(R.text(28, 54, "repository data unavailable this run",
                          size=11, fill=theme.MUTED))
        out.append(R.close_svg())
        return "".join(out)
    out.append(R.text(28, 54, "offensive-security tooling and utilities",
                      size=11, fill=theme.MUTED))
    out.append(f'<rect x="28" y="66" width="{W-56}" height="2" fill="#1E2A2E"/>')
    out.append(f'<rect x="28" y="66" width="{W-56}" height="2" fill="url(#projSweep)"/>')

    for i, r in enumerate(picked):
        y = 88 + i * rowh
        d = theme.stagger(i, base=0.15)
        name = r.get("name") or ""
        stars = r.get("stargazers_count") or 0
        lang = r.get("language") or "—"
        desc = (r.get("description") or "").strip()
        if len(desc) > 68:
            desc = desc[:65].rstrip() + "..."

        out.append(R.text(28, y, name, size=13, weight=600, fill=theme.ACCENT, delay=d))
        out.append(R.text(28, y + 17, desc, size=10.5, fill=theme.MUTED, delay=d))

        if stars:
            out.append(R.text(W - 60, y, f"{stars}", size=13, weight=700,
                              fill=theme.TEXT, anchor="end", delay=d))
            out.append(R.text(W - 28, y, "★", size=12, fill=theme.ACCENT,
                              anchor="end", delay=d))
        out.append(R.text(W - 28, y + 17, lang, size=10, fill=theme.MUTED,
                          anchor="end", delay=d))

        if i < len(picked) - 1:
            out.append(f'<line x1="28" y1="{y + 30}" x2="{W-28}" y2="{y + 30}" '
                       f'stroke="{theme.BORDER}" stroke-width="1"/>')

    out.append(R.close_svg())
    return "".join(out)


# --- entry point -----------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", default="mr-destroyer")
    ap.add_argument("--out", default="assets")
    ap.add_argument("--check", action="store_true",
                    help="report whether output would change; write nothing")
    args = ap.parse_args()

    data, warnings = github_api.collect(args.user)
    for w in warnings:
        print(f"WARNING: {w}", file=sys.stderr)

    summary = github_api.summarize(data)
    if not summary["repos"]:
        print("ERROR: no repo data available; refusing to write empty cards",
              file=sys.stderr)
        return 1

    lang_counts = github_api.language_repo_counts(data["repos"])

    files = {
        "stats.svg": render_stats(summary, data.get("user") or {}),
        "languages.svg": render_languages(lang_counts),
        "snake.svg": render_snake(data["contributions"]),
        "projects.svg": render_projects(data["repos"]),
    }

    os.makedirs(args.out, exist_ok=True)
    changed = []
    for name, content in files.items():
        path = os.path.join(args.out, name)
        old = None
        if os.path.exists(path):
            with open(path) as fh:
                old = fh.read()
        if old != content:
            changed.append(name)
            if not args.check:
                with open(path, "w") as fh:
                    fh.write(content)
        print(f"{'updated' if old != content else 'unchanged'}  {path}")

    print(f"\n{len(changed)} file(s) changed"
          + (f": {', '.join(changed)}" if changed else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
