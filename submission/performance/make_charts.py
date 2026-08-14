#!/usr/bin/env python3
"""
make_charts.py — 比赛交付数据可视化（离线，无外部依赖网络）

数据来源（权威，勿改数值，改动请同步更新来源文档）：
  - docs/competition-submission/RESULTS.md          # 四项精度 + 官方 RTF
  - docs/competition-submission/OPTIMIZATIONS.md    # 本地 A/B 优化里程碑
  - docs/F6_PHASE2_STEP5_AMDAHL_RANKING.md          # W0 时间占比（Amdahl）

生成 4 张 PNG 到 charts/（本目录）：
  1. accuracy.png      — 四项精度指标：候选 vs 基线 vs 验收线（PASS 高亮）
  2. t2w_iteration.png — T2W 延迟演进（本地 A/B，非 official RTF）
  3. w0_breakdown.png  — W0 时间占比（Amdahl 饼图）
  4. rtf_parity.png    — 官方 SPEAK→WAV RTF：候选 vs 基线（parity，无已证实加速）

运行：python3 make_charts.py
"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

OUT = Path(__file__).parent / "charts"
OUT.mkdir(exist_ok=True)

# ---- 统一风格（无 CJK 字体，图表标签一律英文，中文见本文件注释与引用文档）----
plt.rcParams.update({
    "figure.dpi": 130,
    "font.size": 10,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "grid.linestyle": "--",
})

CAND = "#1565c0"   # blue  (candidate)
BASE = "#90a4ae"   # grey  (baseline)
THR  = "#c62828"   # red   (threshold)
PASS = "#2e7d32"   # green


# ============================================================ 1. accuracy ====
def chart_accuracy():
    # (label, candidate, baseline, threshold, direction)
    metrics = [
        ("Daily-Omni\naccuracy (%)",     79.43, 79.5,  77.5,  "up"),
        ("Video-MME\naccuracy (%)",      69.8,  69.0,  67.0,  "up"),
        ("Seed-TTS\nSIM / ASV",          0.969, 0.709, 0.689, "up"),
        ("Seed-TTS\nZH_WER (%)",         1.422, 1.414, 1.56,  "down"),
    ]

    fig, axes = plt.subplots(2, 2, figsize=(10, 7))
    fig.suptitle("Accuracy vs admission thresholds (4 metrics, all PASS)",
                 fontweight="bold", fontsize=13)

    for ax, (label, cand, base, thr, direction) in zip(axes.ravel(), metrics):
        x = [0, 1]
        bars = ax.bar(x, [base, cand], width=0.55,
                      color=[BASE, PASS if direction == "up" and cand >= thr
                             else (PASS if cand <= thr else CAND)],
                      edgecolor="black", linewidth=0.5)
        ax.axhline(thr, color=THR, linestyle="--", linewidth=1.5,
                   label=f"threshold {thr}")
        ax.set_xticks(x)
        ax.set_xticklabels(["baseline", "candidate"])
        ax.set_title(label, fontsize=10)
        ax.legend(fontsize=8, loc="best")
        # 数值标注
        for b, v in zip(bars, [base, cand]):
            ax.text(b.get_x() + b.get_width() / 2, v,
                    f"{v:,}", ha="center", va="bottom", fontsize=8)

    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(OUT / "accuracy.png", bbox_inches="tight")
    plt.close(fig)


# ======================================================= 2. t2w_iteration ====
def chart_t2w_iteration():
    # (stage, latency_ms, note)
    stages = [
        ("pristine\nCPU T2W\n(W0 p50)",        4798, "baseline"),
        ("CANN flow-only\n(W0 p50)",           894,  "-81.4%"),
        ("+ Flow / Vocoder\npipeline (window)", 375, "1.60x"),
    ]
    labels = [s[0] for s in stages]
    values = [s[1] for s in stages]
    notes  = [s[2] for s in stages]

    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(labels, values, width=0.55,
                  color=[BASE, CAND, PASS], edgecolor="black", linewidth=0.5)
    ax.set_ylabel("latency (ms)")
    ax.set_title("T2W latency iteration (local A/B, NOT official RTF)",
                 fontweight="bold", fontsize=12)
    for b, v, n in zip(bars, values, notes):
        ax.text(b.get_x() + b.get_width() / 2, v + 80,
                f"{v:,} ms\n({n})", ha="center", va="bottom", fontsize=9)
    ax.set_ylim(0, max(values) * 1.25)
    ax.text(0.5, -0.22,
            "Source: OPTIMIZATIONS.md (local paired A/B; official RTF is parity, see rtf_parity.png)",
            transform=ax.transAxes, ha="center", fontsize=8, color="dimgrey")
    fig.tight_layout()
    fig.savefig(OUT / "t2w_iteration.png", bbox_inches="tight")
    plt.close(fig)


# ====================================================== 3. w0_breakdown ======
def chart_w0_breakdown():
    slices = [("T2W_inf (CPU flow+vocoder)", 4490, "#c62828"),
              ("overhead",                    320, "#f9a825"),
              ("decode -> speak",             142, "#1565c0")]
    labels = [f"{n}\n{v:,} ms" for n, v, _ in slices]
    values = [v for _, v, _ in slices]
    colors = [c for _, _, c in slices]

    fig, ax = plt.subplots(figsize=(7, 7))
    ax.pie(values, labels=labels, colors=colors, autopct="%1.1f%%",
           startangle=90, counterclock=False,
           wedgeprops=dict(edgecolor="white", linewidth=1.5),
           textprops=dict(fontsize=10))
    ax.set_title("W0 latency breakdown (p50 = 4830 ms, Amdahl)",
                 fontweight="bold", fontsize=12)
    fig.tight_layout()
    fig.savefig(OUT / "w0_breakdown.png", bbox_inches="tight")
    plt.close(fig)


# ========================================================== 4. rtf_parity ====
def chart_rtf_parity():
    baseline = 1.087
    cand_mid = 1.13
    cand_lo, cand_hi = 1.09, 1.17

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.bar(["baseline", "candidate\ncore.rtf_aggregate"],
           [baseline, cand_mid], width=0.5,
           color=[BASE, CAND], edgecolor="black", linewidth=0.5,
           yerr=[[0, 0], [cand_mid - cand_lo, cand_hi - cand_mid]],
           capsize=6, error_kw=dict(elinewidth=1.5, ecolor="black"))
    ax.axhline(baseline, color=THR, linestyle="--", linewidth=1.2, alpha=0.7)
    ax.set_ylabel("SPEAK -> WAV RTF (lower is better)")
    ax.set_title("Official RTF: parity vs baseline (no proven speedup)",
                 fontweight="bold", fontsize=12)
    ax.text(1, cand_hi + 0.01, f"[{cand_lo}, {cand_hi}]", ha="center",
            va="bottom", fontsize=9)
    ax.set_ylim(0, 1.4)
    fig.tight_layout()
    fig.savefig(OUT / "rtf_parity.png", bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    chart_accuracy()
    chart_t2w_iteration()
    chart_w0_breakdown()
    chart_rtf_parity()
    print("charts written to:", OUT.resolve())
    for p in sorted(OUT.glob("*.png")):
        print("  -", p.name)
