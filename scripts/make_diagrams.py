"""Writes app/templates/_diagrams.html: annotated sketches of both charts, on made-up data. Run: python3 scripts/make_diagrams.py"""
import math
from pathlib import Path

L, R = 50, 600            # plot x range
N = 40                    # days
X = lambda i: L + (R - L) * (i + 0.5) / N
W = (R - L) / N

def badge(n, x, y, tx, ty):
    """Numbered badge at (x, y) with an arrow to the feature at (tx, ty)."""
    out = ""
    if (tx, ty) != (x, y):
        dx, dy = tx - x, ty - y; d = math.hypot(dx, dy); ux, uy = dx / d, dy / d
        sx, sy = x + ux * 11, y + uy * 11
        out += f'<line x1="{sx:.0f}" y1="{sy:.0f}" x2="{tx:.0f}" y2="{ty:.0f}" class="arrow" marker-end="url(#ah)"/>'
    out += f'<circle cx="{x}" cy="{y}" r="10" class="badge"/><text x="{x}" y="{y + 4}" class="badge-n">{n}</text>'
    return out

DEFS = ('<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        '<path d="M0,0 L10,5 L0,10 z" class="arrowhead"/></marker></defs>')

# ---------- Fatigue debt ----------
ready = [1,2,0,1,-1,1,2,0,-2,-3,-4,-3,-5,-4,-6,-7,-5,-3,-2,-1,0,1,2,1,2,3,2,1,0,1,3,4,3,2,1,0,1,2,3,4]
debt = []
for i in range(N):
    debt.append(sum(-r for r in ready[max(0, i - 7):i + 1] if r < 0))
P1 = (14, 114); Z1 = 64; s1 = 5.2            # readiness panel, zero line, px per point
P2 = (134, 250); s2 = 116 / 50               # debt panel 0..50
P3 = (270, 350); M3 = 310; s3 = 8.5          # variation panel, 4.5 at M3
var = [4.5,5,4,4.6,5.2,4.4,4.8,5,6.2,6.8,7.2,6.5,5.8,5.4,4.9,4.2,3.6,3.2,3.8,4.4,4.6,4.5,4.9,4.2,4.4,4.8,4.6,4.3,4.5,4.9,5.1,4.7,4.4,4.6,4.5,4.3,4.6,4.8,4.4,4.5]
fo, limit, danger = 11, 19, 25
col = lambda v: "var(--red)" if abs(v) >= 6 else "var(--amber)" if abs(v) >= 3 else "var(--green)"
states = [(0, 8, "#6fb8e0"), (8, 13, "#a37ef0"), (13, 19, "#f08a5d"), (19, 30, "#6fb8e0"), (30, 34, "#5fcf9b"), (34, 40, "#6fb8e0")]

svg = [f'<svg viewBox="0 0 640 372" class="sketch" role="img" aria-labelledby="sk-debt">{DEFS}']
for a, b, c in states:
    svg.append(f'<rect x="{L + a * W:.1f}" y="10" width="{(b - a) * W:.1f}" height="344" fill="{c}" opacity=".22"/>')
for top, bottom, name in ((P1[0], P1[1], ""), (P2[0], P2[1], ""), (P3[0], P3[1], "")):
    svg.append(f'<rect x="{L}" y="{top}" width="{R - L}" height="{bottom - top}" class="panel"/>')
svg.append(f'<line x1="{L}" y1="{Z1}" x2="{R}" y2="{Z1}" class="axis"/>')
for i, v in enumerate(ready):
    y, h = (Z1 - v * s1, v * s1) if v > 0 else (Z1, -v * s1)
    svg.append(f'<rect x="{X(i) - W / 2 + 1:.1f}" y="{y:.1f}" width="{W - 2:.1f}" height="{max(h, 1):.1f}" fill="{col(v)}"/>')
pts = " ".join(f"{X(i):.1f},{P2[1] - d * s2:.1f}" for i, d in enumerate(debt))
svg.append(f'<polygon points="{X(0):.1f},{P2[1]} {pts} {X(N - 1):.1f},{P2[1]}" class="debt-area"/>')
svg.append(f'<polyline points="{pts}" class="debt-line"/>')
for v, c in ((fo, "#8a63d2"), (limit, "var(--amber)"), (danger, "var(--red)")):
    svg.append(f'<line x1="{L}" y1="{P2[1] - v * s2:.1f}" x2="{R}" y2="{P2[1] - v * s2:.1f}" stroke="{c}" stroke-dasharray="5 4" stroke-width="1.5"/>')
rec = next(i for i in range(20, N) if debt[i] == 0)
svg.append(f'<line x1="{X(rec):.1f}" y1="{P2[0]}" x2="{X(rec):.1f}" y2="{P2[1]}" stroke="var(--green)" stroke-dasharray="2 3" stroke-width="2"/>')
svg.append(f'<rect x="{L}" y="{M3 - 1.5 * s3:.1f}" width="{R - L}" height="{3 * s3:.1f}" class="band"/>')
for i, v in enumerate(var):
    d = v - 4.5; y, h = (M3 - d * s3, d * s3) if d > 0 else (M3, -d * s3)
    c = "var(--red)" if v <= 1 or v >= 8 else "var(--amber)" if v < 3 or v > 6 else "var(--green)"
    svg.append(f'<rect x="{X(i) - W / 2 + 1:.1f}" y="{y:.1f}" width="{W - 2:.1f}" height="{max(h, 1):.1f}" fill="{c}"/>')
for label, y in (("{{ t('Readiness') }}", (P1[0] + P1[1]) / 2), ("{{ t('Fatigue debt') }}", (P2[0] + P2[1]) / 2), ("{{ t('HRV variation') }}", (P3[0] + P3[1]) / 2)):
    svg.append(f'<text x="{L - 8}" y="{y:.0f}" class="ylabel" transform="rotate(-90 {L - 8} {y:.0f})">{label}</text>')
peak = max(range(N), key=lambda i: debt[i])
svg += [
    badge(1, 622, 28, X(25) + 3, Z1 - 3 * s1 - 2),
    badge(2, 622, 74, X(15) + 4, Z1 + 7 * s1 - 4),
    badge(3, 360, 150, X(peak - 3), P2[1] - debt[peak - 3] * s2 + 8),
    badge(4, 622, P2[1] - fo * s2 + 8, R + 1, P2[1] - fo * s2),
    badge(5, 622, P2[1] - limit * s2 - 4, R + 1, P2[1] - limit * s2),
    badge(6, 622, P2[1] - danger * s2 - 14, R + 1, P2[1] - danger * s2),
    badge(7, X(rec) + 34, P2[1] - 20, X(rec) + 2, P2[1] - 30),
    badge(8, 622, M3 - 2, R + 1, M3 - 1.5 * s3 + 2),
    badge(9, X(10), 362, X(10), 340),
]
svg.append('</svg>')
debt_svg = "\n".join(svg)

# ---------- HRV-guided ----------
import random
random.seed(4)
week = [62,63,63,64,63,62,61,60,58,56,54,53,52,52,53,55,57,58,60,61,62,62,63,63,62,63,64,66,68,70,71,70,68,66,65,64,63,63,62,62]
lo = [57] * 14 + [56] * 14 + [58] * 12; hi = [67] * 14 + [66] * 14 + [68] * 12
daily = [w + random.uniform(-5, 5) for w in week]
cv = [3 + 0.8 * math.sin(i / 3) + (1.6 if 8 <= i <= 14 else 0) for i in range(N)]
rhr = [48 + random.uniform(-2, 2) + (3 if 9 <= i <= 14 else 0) for i in range(N)]
sig = ["green" if l <= w <= h else "amber" for w, l, h in zip(week, lo, hi)]
T = (12, 30); H = (44, 208); HR = (40, 75); C = (228, 288); Q = (304, 352)
yh = lambda v: H[1] - (v - HR[0]) / (HR[1] - HR[0]) * (H[1] - H[0])
svg = [f'<svg viewBox="0 0 640 372" class="sketch" role="img">{DEFS}']
for top, bottom in (T, H, C, Q):
    svg.append(f'<rect x="{L}" y="{top}" width="{R - L}" height="{bottom - top}" class="panel"/>')
for i, s in enumerate(sig):
    svg.append(f'<rect x="{L + i * W:.1f}" y="{T[0]}" width="{W:.1f}" height="{T[1] - T[0]}" fill="var(--{s})"/>')
band = "".join(f"{L + i * W:.1f},{yh(hi[i]):.1f} {L + (i + 1) * W:.1f},{yh(hi[i]):.1f} " for i in range(N))
band += "".join(f"{L + (i + 1) * W:.1f},{yh(lo[i]):.1f} {L + i * W:.1f},{yh(lo[i]):.1f} " for i in reversed(range(N)))
svg.append(f'<polygon points="{band}" class="band"/>')
for i, v in enumerate(daily):
    svg.append(f'<circle cx="{X(i):.1f}" cy="{yh(v):.1f}" r="2.6" class="dot-hrv"/>')
svg.append(f'<polyline points="{" ".join(f"{X(i):.1f},{yh(v):.1f}" for i, v in enumerate(week))}" class="hrv-line"/>')
for i, (v, s) in enumerate(zip(week, sig)):
    svg.append(f'<circle cx="{X(i):.1f}" cy="{yh(v):.1f}" r="3.2" fill="var(--{s})"/>')
yc = lambda v: C[1] - v / 6 * (C[1] - C[0])
svg.append(f'<polyline points="{" ".join(f"{X(i):.1f},{yc(v):.1f}" for i, v in enumerate(cv))}" fill="none" stroke="#8a63d2" stroke-width="2"/>')
yq = lambda v: Q[1] - (v - 42) / 14 * (Q[1] - Q[0])
for i, v in enumerate(rhr):
    svg.append(f'<circle cx="{X(i):.1f}" cy="{yq(v):.1f}" r="2.4" fill="var(--red)" opacity=".7"/>')
for label, y in (("HRV (ms)", (H[0] + H[1]) / 2), ("CV %", (C[0] + C[1]) / 2), ("{{ 'Tętno' if lang == 'pl' else 'RHR' }}", (Q[0] + Q[1]) / 2)):
    svg.append(f'<text x="{L - 8}" y="{y:.0f}" class="ylabel" transform="rotate(-90 {L - 8} {y:.0f})">{label}</text>')
low = 12; high = 30
svg += [
    badge(1, 622, 21, R + 1, 21),
    badge(2, X(3), 66, X(3), yh(daily[3]) - 4),
    badge(3, X(22), 66, X(22), yh(week[22]) - 5),
    badge(4, 622, yh(hi[-1]) , R + 1, yh(hi[-1]) + 4),
    badge(5, X(low) + 30, 196, X(low) + 4, yh(week[low]) + 4),
    badge(6, X(high) + 70, 130, X(high) + 5, yh(week[high]) + 3),
    badge(7, 622, C[0] + 18, R + 1, yc(cv[-1])),
    badge(8, 622, Q[0] + 22, R + 1, yq(rhr[-1])),
]
svg.append('</svg>')
hrv_svg = "\n".join(svg)

open(Path(__file__).resolve().parent.parent / "app/templates/_diagrams.html", "w").write(
    "{# Generated by scripts/make_diagrams.py: annotated sketches of the two charts. Numbers match the list under each. #}\n"
    "{% if model.key == 'debt' %}\n" + debt_svg + "\n{% else %}\n" + hrv_svg + "\n{% endif %}\n")
print(len(debt_svg), len(hrv_svg))
