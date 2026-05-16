# 混淆矩阵 — matplotlib代码（在本地运行）
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import seaborn as sns

# 解决 Mac 下中文显示问题（优先使用 Arial Unicode MS 或 PingFang SC）
plt.rcParams['font.sans-serif'] = ['Arial', 'Helvetica', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False

# 只保留英文
labels = ['Confused', 'Curious', 'Focus', 'Tired', 'Listen', 'Happy']
col_labels = labels + ['Other']

# 行=目标pattern，列=参与者回答
# 格式：[困惑, 好奇, 专注, 疲惫, 倾听, 开心, 其他]
matrix = np.array([
    [1, 5, 2, 0, 2, 0, 0],   # 困惑
    [4, 2, 0, 0, 1, 3, 0],   # 好奇
    [1, 0, 3, 1, 3, 0, 2],   # 专注
    [1, 0, 1, 8, 0, 0, 0],   # 疲惫
    [1, 0, 3, 0, 3, 0, 3],   # 倾听
    [1, 1, 0, 0, 0, 7, 2],   # 开心
])

# 设置整体风格
sns.set_theme(style="white")
plt.rcParams['font.sans-serif'] = ['Arial', 'Helvetica']

fig, ax = plt.subplots(figsize=(10, 6.5))

# 使用 seaborn 的 heatmap 进行美化
# cmap 选择高级的蓝青色渐变 (例如 'PuBu' 或 'Blues')
sns.heatmap(matrix, annot=True, fmt="d", cmap="PuBu",
            xticklabels=col_labels, yticklabels=labels,
            cbar_kws={'label': 'Count (n=10)', 'shrink': 0.8},
            annot_kws={"size": 16, "weight": "bold"}, ax=ax,
            linewidths=1.5, linecolor='white')

# 定制化刻度标签
ax.set_xticklabels(ax.get_xticklabels(), fontsize=13, rotation=0)
ax.set_yticklabels(ax.get_yticklabels(), fontsize=13, rotation=0)

ax.set_xlabel('Participant Response', fontsize=14, fontweight='bold', labelpad=15, color='#333333')
ax.set_ylabel('Target Pattern', fontsize=14, fontweight='bold', labelpad=15, color='#333333')

# 对角线高亮边框 (绿色框)
for i in range(6):
    # seaborn heatmap 的坐标是以方块左上角为起点的 (x, y) = (列, 行)
    ax.add_patch(mpatches.Rectangle((i, i), 1, 1,
        fill=False, edgecolor='#1D9E75', linewidth=3.5))

plt.tight_layout()

# 保存高清 PNG 和 PDF
plt.savefig('confusion_matrix.png', bbox_inches='tight', dpi=300)
plt.savefig('confusion_matrix.pdf', bbox_inches='tight', dpi=300)

print("生成成功！已保存为 confusion_matrix.png 和 confusion_matrix.pdf")

# 如果在命令行运行，避免卡住可以注释掉 show，如果在 IDE 中可以取消注释
# plt.show()