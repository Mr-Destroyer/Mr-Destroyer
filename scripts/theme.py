"""Design tokens — the single source of truth for every generated asset.

The restraint rule: one accent plus neutrals. The previous assets used green +
blue + amber + white simultaneously, which is what read as unpolished. Hierarchy
here comes from size, weight and letter-spacing, not from more colors.
"""

# --- palette ---------------------------------------------------------------
BG = "#0B0F10"  # ground: near-black with a cool cast, never pure #000
SURFACE = "#11171A"  # card fill
BORDER = "#1E2A2E"  # hairlines
ACCENT = "#00E5A0"  # the green — mint-shifted, used sparingly
ACCENT_DIM = "#0A6B4E"  # inactive bars, ghosted text
TEXT = "#E6EDF3"  # primary
MUTED = "#8B949E"  # secondary

# Contribution-graph ramp, empty -> busiest. Level 0 is deliberately barely
# distinguishable from BG so a sparse grid reads as calm rather than broken.
LEVELS = ["#151C1F", "#0A6B4E", "#00A874", "#00C98C", "#00E5A0"]

# --- type ------------------------------------------------------------------
# No @font-face is possible: raw.githubusercontent.com serves SVGs under
# `default-src 'none'`, so external fonts are blocked. System stacks only.
MONO = (
    "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, "
    "'Liberation Mono', monospace"
)

# --- motion ----------------------------------------------------------------
# Everything animates ONCE on load, staggered, then settles into slow ambient
# motion only. No rapid flashing — the asset this replaces ran a 0.15s
# full-frame luminance flicker, which is a genuine photosensitivity risk.
STAGGER_MS = 90  # per-row delay for entrance choreography
EASE = "cubic-bezier(.2,.7,.3,1)"

# Motion opt-in. Every animated class is VISIBLE in its base state, and only
# becomes "hidden, then animate in" inside this query. The inverse arrangement —
# opacity:0 as the base with the animation as the rescue — means any renderer
# that does not run animations shows a permanently blank card. That is the
# difference between "no animation" and "no content".
#
# `no-preference` rather than `reduce`: a browser that does not understand the
# query at all never matches it, so it keeps the visible base state. Writing
# this as `reduce { show everything }` would make the fallback depend on the
# query being supported, which is the wrong way round.
#
# The easing is interpolated rather than referenced through a custom property,
# so hand-authored assets get it without each having to declare `--ease`.
REDUCED_MOTION = """
    @media (prefers-reduced-motion: no-preference) {
      .rise { opacity: 0; animation: riseIn .7s %s forwards; }
      .draw { stroke-dashoffset: 1; animation: draw 1.6s ease-out forwards; }
      .blink { animation: blink 1.1s steps(1) infinite; }
    }""" % EASE


def stagger(i, base=0.0, step_ms=STAGGER_MS):
    """Entrance delay in seconds for row `i`."""
    return base + (i * step_ms) / 1000.0


def esc(s):
    """Escape text for XML content."""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
