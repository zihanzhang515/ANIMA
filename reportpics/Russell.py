import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import hsv_to_rgb
from matplotlib import patheffects

plt.rcParams.update({
    'font.family': 'Georgia',
    'figure.facecolor': 'white',
    'axes.facecolor': 'white',
})

# ── Shared: draw Russell color wheel ──────────────────────────────────────
def draw_wheel(ax, res=800, r_max=1.18, alpha=0.55):
    """Render Russell-layout HSV color wheel onto ax."""
    x = np.linspace(-r_max * 1.02, r_max * 1.02, res)
    y = np.linspace(-r_max * 1.02, r_max * 1.02, res)
    X, Y = np.meshgrid(x, y)
    R = np.sqrt(X**2 + Y**2)
    Theta = np.degrees(np.arctan2(Y, X))   # -180..180, 0=right, 90=up

    # Hue mapping: green(0.33) at right → yellow(0.12) at top
    #              → red(0) at left → blue-purple(0.72) at bottom
    H = ((120 - Theta * 0.78) / 360) % 1.0
    S = np.clip(R / r_max, 0, 0.88)        # white at centre
    V = np.ones_like(R) * 0.97

    hsv = np.stack([H, S, V], axis=-1)
    rgb = hsv_to_rgb(hsv)
    # Mask outside circle → white
    mask = R > r_max
    rgb[mask] = 1.0

    ax.imshow(rgb, extent=[-r_max*1.02, r_max*1.02,
                           -r_max*1.02, r_max*1.02],
              origin='lower', zorder=0,
              interpolation='bilinear', alpha=alpha)

    ring = mpatches.Circle((0, 0), r_max, fill=False,
                            edgecolor='#CCCCCC', lw=0.8, zorder=1)
    ax.add_patch(ring)

def style_ax(ax, title):
    ax.axhline(0, color='#888888', lw=0.75, zorder=2)
    ax.axvline(0, color='#888888', lw=0.75, zorder=2)
    ax.set_xlim(-1.32, 1.32)
    ax.set_ylim(-1.32, 1.32)
    ax.set_aspect('equal')
    ax.set_xticks([-1, -0.5, 0, 0.5, 1])
    ax.set_yticks([-1, -0.5, 0, 0.5, 1])
    ax.tick_params(labelsize=8.5)
    ax.spines[['top', 'right']].set_visible(False)
    ax.set_xlabel('Valence  (← negative    positive →)',
                  fontsize=10.5, labelpad=8)
    ax.set_ylabel('Arousal  (↓ low    high ↑)',
                  fontsize=10.5, labelpad=8)
    ax.set_title(title, fontsize=10, pad=12, linespacing=1.6)

def label_point(ax, x, y, name, led_color, ox, oy):
    """Draw bold label with white halo so it's readable on color wheel."""
    txt = ax.text(x + ox, y + oy, name,
                  fontsize=9.5, fontweight='bold', color=led_color,
                  ha='left' if ox >= 0 else 'right', va='center',
                  zorder=8)
    txt.set_path_effects([
        patheffects.withStroke(linewidth=2.8, foreground='white')
    ])

# ── PEARL data ─────────────────────────────────────────────────────────────
# Actual LED colors (normalized to [0,1])
LED = {
    'Tired':    (160/255,  90/255,   0/255),
    'Happy':    (255/255, 140/255,   0/255),
    'Focus':    (  0/255,  50/255, 180/255),
    'Listen':   (  0/255, 160/255,  50/255),
    'Curious':  (  0/255, 200/255, 200/255),
    'Confused': (140/255,   0/255, 200/255),
}

# Designed positions [Valence, Arousal] – where each color BELONGS
# in color-emotion theory, plus where PEARL targets
# (note Tired sits in low-arousal negative despite amber hue → Russell violation)
designed = {
    'Tired':    (-0.15, -0.58),
    'Happy':    ( 0.72,  0.62),
    'Focus':    ( 0.22, -0.12),
    'Listen':   ( 0.42,  0.18),
    'Curious':  ( 0.52,  0.40),
    'Confused': (-0.22,  0.18),
}

# Perceived positions from Q3/Q4 (n=9, scale: (mean-4)/3 → [-1,+1])
perceived_raw = {
    'Tired':    {'q3':[2,1,1,2,1,1,1,1,3], 'q4':[3,1,5,3,6,1,2,1,6]},
    'Happy':    {'q3':[6,7,7,7,6,7,6,7,7], 'q4':[7,7,7,7,3,7,2,6,7]},
    'Focus':    {'q3':[2,3,4,6,7,2,2,1,2], 'q4':[2,3,4,6,5,4,4,1,2]},
    'Listen':   {'q3':[5,4,4,6,7,2,7,3,4], 'q4':[5,4,4,6,5,2,7,5,4]},
    'Curious':  {'q3':[6,7,6,3,4,2,4,3,1], 'q4':[5,7,6,4,5,5,4,5,1]},
    'Confused': {'q3':[3,5,2,6,3,2,7,4,1], 'q4':[4,6,4,6,4,5,4,4,1]},
}
perceived = {k: ((np.mean(v['q4'])-4)/3,
                 (np.mean(v['q3'])-4)/3)
             for k, v in perceived_raw.items()}

# Per-label text offsets [dx, dy]  (tweak to avoid overlap)
off_A = {
    'Tired':    (-0.13,  0.11),
    'Happy':    ( 0.12,  0.11),
    'Focus':    ( 0.12, -0.11),
    'Listen':   ( 0.12,  0.12),
    'Curious':  (-0.24,  0.12),
    'Confused': ( 0.12,  0.12),
}
off_B = {
    'Tired':    (-0.13, -0.12),
    'Happy':    ( 0.12,  0.12),
    'Focus':    ( 0.12, -0.12),
    'Listen':   (-0.22,  0.12),
    'Curious':  (-0.24, -0.12),
    'Confused': ( 0.12,  0.12),
}

# ── Figure A: design chapter ───────────────────────────────────────────────
fig_A, ax_A = plt.subplots(figsize=(6.5, 6.5))
draw_wheel(ax_A, alpha=0.52)
style_ax(ax_A,
    'Figure 4.X — PEARL signal vocabulary: designed positions\n'
    'in Russell (1980) circumplex  (marker colour = LED colour)')

for name, (vx, vy) in designed.items():
    c = LED[name]
    hex_c = '#{:02x}{:02x}{:02x}'.format(
        int(c[0]*255), int(c[1]*255), int(c[2]*255))
    ax_A.scatter(vx, vy, s=200, color=hex_c,
                 edgecolors='white', linewidths=1.8, zorder=6)
    label_point(ax_A, vx, vy, name, hex_c,
                *off_A[name])

ax_A.scatter(0, 0, s=90, color='white',
             edgecolors='#999999', linewidths=1.2, zorder=7)
ax_A.text(0, 0, 'Neutral', fontsize=7.5, color='#888888',
          ha='center', va='center', zorder=8)

plt.tight_layout()
plt.savefig('figure_A_design_russell.pdf', dpi=200, bbox_inches='tight')
plt.savefig('figure_A_design_russell.png', dpi=200, bbox_inches='tight')
plt.show()

# ── Figure B: Study 1 perceived ───────────────────────────────────────────
fig_B, ax_B = plt.subplots(figsize=(6.5, 6.5))
draw_wheel(ax_B, alpha=0.52)
style_ax(ax_B,
    'Figure 5.3 — PEARL Study 1: perceived positions in Russell (1980) space\n'
    'Placed by participant Q3/Q4 ratings  (n = 9,  marker colour = LED colour)')

for name, (vx, vy) in perceived.items():
    c = LED[name]
    hex_c = '#{:02x}{:02x}{:02x}'.format(
        int(c[0]*255), int(c[1]*255), int(c[2]*255))
    # Draw designed position as faint hollow marker
    dv, da = designed[name]
    ax_B.scatter(dv, da, s=140, color=hex_c, alpha=0.20,
                 edgecolors=hex_c, linewidths=1.5,
                 linestyle='--', zorder=4)
    # Arrow designed → perceived
    ax_B.annotate(
        '', xy=(vx, vy), xytext=(dv, da),
        arrowprops=dict(
            arrowstyle='-|>', color=hex_c,
            lw=1.4, mutation_scale=11,
            connectionstyle='arc3,rad=0.08'
        ), zorder=5)
    # Perceived filled circle
    ax_B.scatter(vx, vy, s=200, color=hex_c,
                 edgecolors='white', linewidths=1.8, zorder=6)
    label_point(ax_B, vx, vy, name, hex_c, *off_B[name])

# Legend
h1 = ax_B.scatter([], [], s=80, color='#888888', alpha=0.22,
                  edgecolors='#888888', linewidths=1.5,
                  label='Designed intent (faint)')
h2 = ax_B.scatter([], [], s=80, color='#888888',
                  edgecolors='white', linewidths=1.8,
                  label='Perceived mean (●, n=9)')
ax_B.legend(handles=[h1, h2], fontsize=8.5, loc='lower left',
            frameon=True, framealpha=0.92, edgecolor='#DDDDDD',
            borderpad=0.8)

plt.tight_layout()
plt.savefig('figure_B_study1_russell.pdf', dpi=200, bbox_inches='tight')
plt.savefig('figure_B_study1_russell.png', dpi=200, bbox_inches='tight')
plt.show()