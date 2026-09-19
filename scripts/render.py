"""SVG primitives shared by every generated asset.

Every generated asset routes through these so they cannot drift apart visually.

Animation rules derived from the probe (see the plan's PROBE RESULTS):
  - SMIL (`<animate>`) is the RELIABLE path for animating SVG geometry and
    presentation attributes: gradient x1/x2 sweeps, clipPath width reveals.
  - CSS `@keyframes` is reliable for `opacity` and `stroke-dashoffset`.
  - CSS animating `transform` on an SVG element is a SILENT NO-OP. Never do it.
  - `feTurbulence` at a tasteful opacity is indistinguishable from no texture.
"""

import theme


# --- document scaffolding --------------------------------------------------

def open_svg(width, height, extra_defs=""):
    """Open an SVG sized by viewBox only.

    No `height` attribute: a fixed height crops or letterboxes when GitHub
    renders narrower than the viewBox (mobile). Letting the aspect ratio drive
    keeps it correct at every width.
    """
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" role="img">
  <defs>
    <style>
      text {{ font-family: {theme.MONO}; }}
      /* Base states are the RESTING state — fully visible. The hidden start
         state and the animation itself live in theme.REDUCED_MOTION, gated on
         `prefers-reduced-motion: no-preference`. Do not move `opacity: 0` or a
         non-zero dashoffset back into these rules: as a base state they render
         a permanently blank card anywhere animations do not run. */
      @keyframes riseIn {{ from {{ opacity: 0; transform: translateY(10px); }} to {{ opacity: 1; transform: translateY(0); }} }}
      /* Normalised draw-on. Pair with `pathLength="1"` on the element and the
         browser treats the path as exactly 1 unit long, so the dash values are
         1 regardless of real geometry — no need to measure the path and pass
         its length in as `--len`, which was undefined in four of five assets
         and silently made the rule a no-op there. `from` is explicit because
         the base dashoffset is 0, so an implicit start would animate 0 -> 0. */
      .draw {{ stroke-dasharray: 1; stroke-dashoffset: 0; }}
      @keyframes draw {{ from {{ stroke-dashoffset: 1; }} to {{ stroke-dashoffset: 0; }} }}
      @keyframes blink {{ 0%,49% {{ opacity: 1; }} 50%,100% {{ opacity: 0; }} }}
      {theme.REDUCED_MOTION}
    </style>
    {extra_defs}
  </defs>
  <rect width="{width}" height="{height}" fill="{theme.BG}"/>'''


def close_svg():
    return "</svg>\n"


# --- components ------------------------------------------------------------

def card(x, y, w, h, radius=6, fill=None, stroke=None, delay=None):
    """A surface panel. `delay` opts it into the staggered entrance."""
    fill = fill or theme.SURFACE
    stroke = stroke or theme.BORDER
    cls = f' class="rise" style="animation-delay:{delay:.2f}s"' if delay is not None else ""
    return (
        f'<rect{cls} x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="1"/>'
    )


def text(x, y, s, size=12, fill=None, weight=400, anchor="start",
         spacing=None, delay=None, opacity=None):
    """A text run. Escapes content — never pass raw user data unescaped."""
    fill = fill or theme.TEXT
    attrs = [
        f'x="{x}"', f'y="{y}"', f'font-size="{size}"', f'fill="{fill}"',
        f'font-weight="{weight}"',
    ]
    if anchor != "start":
        attrs.append(f'text-anchor="{anchor}"')
    if spacing is not None:
        attrs.append(f'letter-spacing="{spacing}"')
    if opacity is not None:
        attrs.append(f'opacity="{opacity}"')
    if delay is not None:
        attrs.append(f'class="rise" style="animation-delay:{delay:.2f}s"')
    return f'<text {" ".join(attrs)}>{theme.esc(s)}</text>'


def bar(x, y, w, h, pct, fill=None, delay=None, bg=True):
    """A horizontal meter. Draws the track, then the filled portion.

    Uses a rect width (not stroke-dashoffset) because the probe showed geometry
    attributes are the dependable path.
    """
    fill = fill or theme.ACCENT
    out = []
    if bg:
        out.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{h/2}" '
            f'fill="{theme.ACCENT_DIM}" opacity="0.18"/>'
        )
    fw = max(h, w * max(0.0, min(1.0, pct)))
    cls = f' class="rise" style="animation-delay:{delay:.2f}s"' if delay is not None else ""
    out.append(
        f'<rect{cls} x="{x}" y="{y}" width="{fw:.1f}" height="{h}" rx="{h/2}" fill="{fill}"/>'
    )
    return "".join(out)


def hairline(x, y, w, delay=None, length=900):
    """A 1px rule that draws itself on."""
    cls = 'class="draw" style="--len:{}px; animation-delay:{:.2f}s"'.format(length, delay or 0)
    return (
        f'<line {cls} x1="{x}" y1="{y}" x2="{x + w}" y2="{y}" '
        f'stroke="{theme.BORDER}" stroke-width="1"/>'
    )


def dot(x, y, r=3, fill=None, delay=None):
    """A status dot. Slow ambient pulse only — never a fast flash."""
    fill = fill or theme.ACCENT
    cls = f' class="rise" style="animation-delay:{delay:.2f}s"' if delay is not None else ""
    return f'<circle{cls} cx="{x}" cy="{y}" r="{r}" fill="{fill}"/>'


def sweep_gradient(gid, color=None, opacity=0.95, dur=4.0):
    """A gradient that sweeps horizontally via SMIL.

    This is the premium-motion workhorse. SMIL on x1/x2 was the one shimmer
    technique that reliably produced a visible moving highlight (probe T3a);
    the CSS `transform: translateX` equivalent was a silent no-op.
    """
    color = color or theme.ACCENT
    return f'''<linearGradient id="{gid}" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="{color}" stop-opacity="0"/>
      <stop offset="50%" stop-color="{color}" stop-opacity="{opacity}"/>
      <stop offset="100%" stop-color="{color}" stop-opacity="0"/>
      <animate attributeName="x1" values="-0.6;1" dur="{dur}s" repeatCount="indefinite"/>
      <animate attributeName="x2" values="-0.1;1.5" dur="{dur}s" repeatCount="indefinite"/>
    </linearGradient>'''


def pulse_gradient(gid, lo=None, hi=None, dur=5.0):
    """A gradient whose stops breathe between two colors via SMIL.

    Probe T3b. Softer and slower than the sweep — good for large surfaces where
    a sweeping highlight would be too busy.
    """
    lo = lo or theme.ACCENT_DIM
    hi = hi or theme.ACCENT
    return f'''<linearGradient id="{gid}" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="{lo}">
        <animate attributeName="stop-color" values="{lo};{hi};{lo}" dur="{dur}s" repeatCount="indefinite"/>
      </stop>
      <stop offset="100%" stop-color="{hi}">
        <animate attributeName="stop-color" values="{hi};{lo};{hi}" dur="{dur}s" repeatCount="indefinite"/>
      </stop>
    </linearGradient>'''


def glow_filter(fid, color=None, blur=3.0):
    """A glow that stacks two drop-shadows.

    CSS `filter: drop-shadow()` was verified working (probe T5). Kept modest:
    heavy filters on a full-width SVG cost frames on low-end machines.
    """
    color = color or theme.ACCENT
    return f'''<filter id="{fid}" x="-40%" y="-40%" width="180%" height="180%">
      <feDropShadow dx="0" dy="0" stdDeviation="{blur}" flood-color="{color}" flood-opacity="0.55"/>
      <feDropShadow dx="0" dy="0" stdDeviation="{blur * 3}" flood-color="{color}" flood-opacity="0.25"/>
    </filter>'''


def clip_reveal(cid, x, y, w, h, dur=1.8, begin=0.3):
    """A clipPath whose rect grows left-to-right via SMIL — the typewriter effect.

    Probe T7b. The CSS `clip-path: inset()` variant was a silent no-op.
    """
    return f'''<clipPath id="{cid}">
      <rect x="{x}" y="{y}" width="0" height="{h}">
        <animate attributeName="width" from="0" to="{w}" dur="{dur}s" begin="{begin}s" fill="freeze"/>
      </rect>
    </clipPath>'''
