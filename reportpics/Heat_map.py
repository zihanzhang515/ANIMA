import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import LinearSegmentedColormap

plt.rcParams.update({
    'font.family': 'DejaVu Sans',
    'figure.facecolor': 'white',
    'axes.facecolor': 'white',
})

patterns   = ['Tired', 'Happy', 'Focus', 'Listen', 'Curious', 'Confused']
participants = ['P01','P02','P03','P04','P05','P06','P07','P08','P09','P10']

# Q2 scores  [P01..P10]  (rows = patterns in display order)
q2 = np.array([
    [1, 7, 7, 7, 6, 7, 7, 7, 6, 1],   # Tired
    [5, 7, 7, 6, 7, 7, 7, 7, 7, 2],   # Happy
    [4, 6, 6, 4, 3, 3, 3, 5, 7, 5],   # Focus
    [5, 7, 1, 3, 5, 5, 3, 7, 6, 6],   # Listen
    [7, 7, 1, 6, 6, 5, 2, 7, 5, 6],   # Curious
    [4, 6, 1, 3, 6, 5, 6, 5, 6, 1],   # Confused
])

# Correct (1) / Incorrect (0)  [P01..P10]
correct = np.array([
    [1, 1, 1, 1, 1, 1, 1, 1, 0, 0],   # Tired
    [1, 0, 1, 1, 1, 0, 1, 0, 1, 1],   # Happy
    [0, 0, 1, 0, 0, 0, 1, 1, 0, 0],   # Focus
    [0, 1, 1, 0, 0, 0, 0, 0, 0, 1],   # Listen
    [1, 0, 0, 0, 0, 0, 0, 1, 0, 0],   # Curious
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 0],   # Confused
])

# Custom blue colormap  (white → navy)
cmap = LinearSegmentedColormap.from_list(
    'pearl_blue', ['#EBF3FB', '#1A3A6B'], N=256)

fig, ax = plt.subplots(figsize=(11, 6.5))
im = ax.imshow(q2, cmap=cmap, vmin=0, vmax=7,
               aspect='auto', zorder=0)

nrows, ncols = q2.shape
cell_w = 1.0  # in data units

for i in range(nrows):
    for j in range(ncols):
        val = q2[i, j]
        is_correct = correct[i, j]

        # ── text color: white on dark cells, dark on light ──────────────
        text_color = 'white' if val >= 4 else '#1A3A6B'
        ax.text(j, i, str(val),
                ha='center', va='center',
                fontsize=14, fontweight='bold',
                color=text_color, zorder=3)

        # ── cell border rectangle ─────────────────────────────────────
        border_color = '#27AE60' if is_correct else '#E74C3C'
        border_lw    = 3.0
        rect = mpatches.FancyBboxPatch(
            (j - 0.44, i - 0.44), 0.88, 0.88,
            boxstyle='square,pad=0',
            linewidth=border_lw,
            edgecolor=border_color,
            facecolor='none',
            zorder=4)
        ax.add_patch(rect)

# ── Axes ──────────────────────────────────────────────────────────────────
ax.set_xticks(range(ncols))
ax.set_xticklabels(participants, fontsize=11, fontweight='bold')
ax.set_yticks(range(nrows))
ax.set_yticklabels(patterns, fontsize=11)
ax.set_xlabel('Participants', fontsize=12, fontweight='bold', labelpad=10)
ax.set_ylabel('Target Pattern', fontsize=12, fontweight='bold', labelpad=10)
ax.tick_params(length=0)

# Remove default spines, add outer box
for spine in ax.spines.values():
    spine.set_visible(False)
ax.set_xlim(-0.5, ncols - 0.5)
ax.set_ylim(nrows - 0.5, -0.5)

# ── Colorbar ──────────────────────────────────────────────────────────────
cbar = fig.colorbar(im, ax=ax, shrink=0.82, pad=0.02,
                    ticks=[1, 2, 3, 4, 5, 6, 7])
cbar.ax.set_ylabel('Q2 Score  (1 = slow,  7 = immediate)',
                   fontsize=10, labelpad=10, rotation=270, va='bottom')
cbar.ax.tick_params(labelsize=9)
cbar.outline.set_visible(False)

# ── Legend ────────────────────────────────────────────────────────────────
h_ok  = mpatches.Patch(facecolor='none', edgecolor='#27AE60',
                        linewidth=2.5, label='Correct recognition')
h_err = mpatches.Patch(facecolor='none', edgecolor='#E74C3C',
                        linewidth=2.5, label='Incorrect recognition')
ax.legend(handles=[h_ok, h_err],
          fontsize=10, loc='upper left',
          bbox_to_anchor=(-0.01, -0.12),
          ncol=2, frameon=False)

ax.set_title(
    'Figure 5.2 — Q2 Metacognitive Immediacy per pattern and participant\n'
    'Cell colour = immediacy score.  Border = recognition outcome.',
    fontsize=11, pad=14, linespacing=1.7)

plt.tight_layout()
plt.savefig('q2_heatmap_v2.pdf', dpi=200, bbox_inches='tight')
plt.savefig('q2_heatmap_v2.png', dpi=200, bbox_inches='tight')
plt.show()