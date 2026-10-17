"""
make_report.py —— 从 results.json / results_lang.json 生成图表与 Markdown 报告片段

产物：
    charts/speedup_python.png     各臂相对 A0 的加速比（对数轴）
    charts/scaling.png            时间 vs n 的 log-log 图（含拟合斜率）
    charts/space.png              峰值内存 vs n
    charts/lang.png               跨语言对比
    report_tables.md              可直接粘进 README 的表格

只依赖 matplotlib（已在 requirements.txt 里注明）。

用法：
    python make_report.py
"""
from __future__ import annotations

import json
import math
import os
import platform

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

HERE = os.path.dirname(os.path.abspath(__file__))
CHARTS = os.path.join(HERE, "charts")
RES = os.path.join(HERE, "results.json")
RES_LANG = os.path.join(HERE, "results_lang_robust.json")
RES_ALPHA = os.path.join(HERE, "results_alphabet.json")
RES_SHAPE = os.path.join(HERE, "results_shape.json")

# 中文字体：Windows 上用雅黑，缺失时自动退回 DejaVu（图里只会有方框，不影响数据）
for cand in ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "Source Han Sans SC"):
    if any(cand == f.name for f in font_manager.fontManager.ttflist):
        plt.rcParams["font.sans-serif"] = [cand]
        break
plt.rcParams["axes.unicode_minus"] = False

# 暖色编辑风：espresso / amber / terracotta，不用冷蓝
C_BASE = "#8C5A3C"      # espresso brown —— 原版
C_MID = "#C98B4B"       # amber
C_BEST = "#B4472E"      # terracotta —— 最优
C_GREY = "#8A8178"
C_TEXT = "#2E2A26"
C_GRID = "#E3DCD3"

# 每条臂一个色（同色系不同明度/饱和，靠亮度也能区分，不只靠色相）
ARM_COLOR = {
    "a0_baseline": "#8C5A3C",
    "a1a_syntax": "#C4A484",
    "a1b_two_branch": "#B98A4E",
    "a1l_rolling": "#D9A441",
    "a2_list_backtrack": "#A8724A",
    "a3_bitset_len": "#B4472E",
    "a4_bitset_seq": "#D4693F",
    "a5_hirschberg": "#6E5B4B",
    "a6_hunt_szymanski_len": "#8E3B2A",
}

LABEL = {
    "a0_baseline": "A0 原版",
    "a1a_syntax": "A1a 语法局部化",
    "a1b_two_branch": "A1b 二分支递推",
    "a1l_rolling": "A1L 滚动两行",
    "a2_list_backtrack": "A2 list 回溯",
    "a3_bitset_len": "A3 位并行",
    "a4_bitset_seq": "A4 位并行+回溯",
    "a5_hirschberg": "A5 Hirschberg",
    "a6_hunt_szymanski_len": "A6 Hunt–Szymanski",
}


def _style(ax):
    ax.set_facecolor("#FBF8F4")
    ax.grid(True, which="major", color=C_GRID, linewidth=0.8, zorder=0)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color("#B9AEA3")
    ax.tick_params(colors=C_TEXT, labelsize=9)
    ax.xaxis.label.set_color(C_TEXT)
    ax.yaxis.label.set_color(C_TEXT)
    ax.title.set_color(C_TEXT)


def load(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def chart_speedup(data: dict) -> None:
    rows = data["time"]
    by_n: dict[int, dict[str, float]] = {}
    for r in rows:
        by_n.setdefault(r["n"], {})[r["arm"]] = r["ms"]

    sizes = sorted(by_n)
    arms = ["a1a_syntax", "a1b_two_branch", "a1l_rolling", "a2_list_backtrack",
            "a3_bitset_len", "a4_bitset_seq", "a5_hirschberg"]

    fig, ax = plt.subplots(figsize=(10.4, 5.8), dpi=160)
    _style(ax)
    # 每条线加不同 marker，黑白打印也能区分
    markers = {"a1a_syntax": "o", "a1b_two_branch": "s", "a1l_rolling": "^",
               "a2_list_backtrack": "v", "a3_bitset_len": "D",
               "a4_bitset_seq": "P", "a5_hirschberg": "X"}
    for arm in arms:
        xs, ys = [], []
        for n in sizes:
            base = by_n[n].get("a0_baseline")
            cur = by_n[n].get(arm)
            if base and cur:
                xs.append(n)
                ys.append(base / cur)
        if not xs:
            continue
        color = ARM_COLOR[arm]
        lw = 2.6 if arm in ("a3_bitset_len", "a4_bitset_seq") else 1.9
        ax.plot(xs, ys, marker=markers[arm], markersize=5.5, linewidth=lw, color=color,
                label=LABEL[arm], zorder=3)
        ax.annotate(f"{ys[-1]:.0f}×", (xs[-1], ys[-1]), textcoords="offset points",
                    xytext=(7, -3), fontsize=9, color=color, fontweight="bold")

    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.axhline(1.0, color=C_BASE, linestyle="--", linewidth=1.0, zorder=2)
    ax.annotate("原版基线 1×", (sizes[-1], 1.0), textcoords="offset points",
                xytext=(-58, -14), fontsize=8, color=C_BASE)
    ax.set_xlabel("字符串长度 n（两串等长，字母表 σ=4）")
    ax.set_ylabel("相对 A0 原版的加速比（倍，对数轴）")
    ax.set_title("LCS 优化阶梯：每一级只比上一级多一件事", fontsize=12, pad=12)
    ax.legend(frameon=False, fontsize=8.5, loc="upper left", ncol=2, columnspacing=1.2)
    fig.tight_layout()
    fig.savefig(os.path.join(CHARTS, "speedup_python.png"), facecolor="#FBF8F4")
    plt.close(fig)

    # 局部放大：只画 1×–6× 那一段，否则常数级优化在整图里永远是一条平线
    fig, ax = plt.subplots(figsize=(9.6, 4.8), dpi=160)
    _style(ax)
    for arm in ["a1a_syntax", "a1b_two_branch", "a1l_rolling", "a2_list_backtrack", "a5_hirschberg"]:
        xs, ys = [], []
        for n in sizes:
            base = by_n[n].get("a0_baseline")
            cur = by_n[n].get(arm)
            if base and cur:
                xs.append(n)
                ys.append(base / cur)
        if xs:
            ax.plot(xs, ys, marker=markers[arm], markersize=5.5, linewidth=2.0,
                    color=ARM_COLOR[arm], label=LABEL[arm], zorder=3)
            ax.annotate(f"{ys[-1]:.2f}×", (xs[-1], ys[-1]), textcoords="offset points",
                        xytext=(7, -3), fontsize=9, color=ARM_COLOR[arm], fontweight="bold")
    ax.axhline(1.0, color=C_BASE, linestyle="--", linewidth=1.0, zorder=2)
    ax.set_xscale("log")
    ax.set_ylim(0.9, 6.0)
    ax.set_xlabel("字符串长度 n")
    ax.set_ylabel("相对 A0 的加速比（倍）")
    ax.set_title("放大 1×–6× 区间：常数优化真实值（位并行已移出视野）", fontsize=12, pad=12)
    ax.legend(frameon=False, fontsize=9, loc="upper left")
    fig.tight_layout()
    fig.savefig(os.path.join(CHARTS, "speedup_zoom.png"), facecolor="#FBF8F4")
    plt.close(fig)


def chart_scaling(data: dict) -> None:
    sc = data.get("scaling")
    if not sc:
        return
    fig, ax = plt.subplots(figsize=(9.6, 5.4), dpi=160)
    _style(ax)
    colors = {"a0_baseline": C_BASE, "a1l_rolling": C_MID, "a3_bitset_len": C_BEST}
    markers = {"a0_baseline": "o", "a1l_rolling": "^", "a3_bitset_len": "D"}
    for arm, d in sc.items():
        pts = d["points"]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        ax.plot(xs, ys, marker=markers.get(arm, "o"), markersize=5.5, linewidth=2.2,
                color=colors.get(arm, C_GREY),
                label=f"{LABEL.get(arm, arm)}  整段斜率 {d['slope']:.2f}", zorder=3)
        # 标出最右点的分段斜率，说明「斜率在下降」
        segs = d.get("segments") or []
        if segs:
            last = segs[-1]
            ax.annotate(f"末段 {last['slope']:.2f}", (xs[-1], ys[-1]),
                        textcoords="offset points", xytext=(-4, 10), fontsize=8,
                        color=colors.get(arm, C_GREY))

    # 参考斜率：n^1 与 n^2，贴在角落便于目测
    xs = [sc["a0_baseline"]["points"][0][0], sc["a0_baseline"]["points"][-1][0]]
    y0 = sc["a3_bitset_len"]["points"][0][1]
    for expo in (1.0, 2.0):
        ref = [y0 * (x / xs[0]) ** expo for x in xs]
        ax.plot(xs, ref, linestyle=":", linewidth=1.0, color="#B9AEA3", zorder=2)
        ax.annotate(f"参考 n^{expo:.0f}", (xs[1], ref[1]), textcoords="offset points",
                    xytext=(-58, 4), fontsize=8, color="#8A8178")

    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("字符串长度 n（两串等长）")
    ax.set_ylabel("耗时（ms，对数轴）")
    ax.set_title("等长双串：DP 沿 n² 走，位并行的斜率还在往上爬（1.07→1.28）",
                 fontsize=11.5, pad=12)
    ax.legend(frameon=False, fontsize=9, loc="upper left")
    fig.tight_layout()
    fig.savefig(os.path.join(CHARTS, "scaling.png"), facecolor="#FBF8F4")
    plt.close(fig)


def chart_space(data: dict) -> None:
    rows = data.get("space")
    if not rows:
        return
    by_n: dict[int, dict[str, float]] = {}
    for r in rows:
        by_n.setdefault(r["n"], {})[r["arm"]] = r["peak_mb"]
    sizes = sorted(by_n)
    arms = ["a0_baseline", "a1b_two_branch", "a5_hirschberg", "a1l_rolling",
            "a4_bitset_seq", "a3_bitset_len"]
    arm_color = {
        "a0_baseline": "#8C5A3C", "a1b_two_branch": "#A8724A",
        "a5_hirschberg": "#6E5B4B", "a1l_rolling": "#D9A441",
        "a4_bitset_seq": "#D4693F", "a3_bitset_len": "#B4472E",
    }

    # 横向条形：内存跨 4 个数量级（38 MB → 0.003 MB），纵向柱状会挤成一团
    fig, ax = plt.subplots(figsize=(10.0, 6.2), dpi=160)
    _style(ax)
    height = 0.62
    ypos, labels = [], []
    y = 0
    group_centers = []
    for n in sizes:
        start = y
        for arm in arms:
            v = by_n[n].get(arm)
            if v is None:
                continue
            ax.barh(y, v, height=height, color=arm_color[arm],
                    label=LABEL[arm] if n == sizes[0] else None, zorder=3)
            ax.annotate(f"{v:.3f} MB", (v, y), textcoords="offset points",
                        xytext=(4, 0), fontsize=7.5, color="#5A5048", va="center")
            ypos.append(y)
            labels.append(LABEL[arm])          # 每组都标，否则后两组读不出是哪根
            y += 1
        group_centers.append(((start + y - 1) / 2, n))
        y += 0.9   # 组间留白

    ax.set_xscale("log")
    ax.set_yticks(ypos)
    ax.set_yticklabels(labels, fontsize=8.5)
    ax.set_ylim(y - 0.6, -0.8)                  # 倒序，n 小的在上
    ax.set_xlabel("峰值内存（MB，对数轴）")
    ax.set_title("峰值内存：全表 O(n²) 降到位并行 O(n·m/8)", fontsize=12, pad=12)
    ax.grid(True, axis="x", color=C_GRID, linewidth=0.8)
    ax.grid(False, axis="y")
    for yc, n in group_centers:
        ax.text(1.015, yc, f"n={n}", transform=ax.get_yaxis_transform(),
                fontsize=10, color=C_TEXT, fontweight="bold", va="center")
    fig.tight_layout()
    fig.savefig(os.path.join(CHARTS, "space.png"), facecolor="#FBF8F4")
    plt.close(fig)


def chart_alphabet(data: dict) -> None:
    """σ 扫描：固定 n，只改字母表大小。这张图说明「更优复杂度 ≠ 永远更快」。"""
    rows = data["rows"]
    sigmas = sorted({r["sigma"] for r in rows})
    arms = ["a1l_rolling", "a3_bitset_len", "a6_hunt_szymanski_len"]
    colors = {"a1l_rolling": C_BASE, "a3_bitset_len": C_MID, "a6_hunt_szymanski_len": C_BEST}

    fig, ax = plt.subplots(figsize=(9.2, 5.2), dpi=160)
    _style(ax)
    for arm in arms:
        pts = [(r["sigma"], r["ms"]) for r in rows if r["arm"] == arm]
        pts.sort()
        ax.plot([p[0] for p in pts], [p[1] for p in pts], marker="o", markersize=5,
                linewidth=2.0, color=colors[arm], label=LABEL[arm], zorder=3)

    # 找交叉点（相邻 σ 之间）
    cross = None
    for s0, s1 in zip(sigmas, sigmas[1:]):
        def val(arm, s):
            return next(r["ms"] for r in rows if r["arm"] == arm and r["sigma"] == s)
        d0 = val("a3_bitset_len", s0) - val("a6_hunt_szymanski_len", s0)
        d1 = val("a3_bitset_len", s1) - val("a6_hunt_szymanski_len", s1)
        if d0 * d1 < 0:
            cross = (s0, s1)
            ax.axvspan(s0, s1, color="#EBD9C6", alpha=0.5, zorder=1)
            ax.annotate("交叉点", ((s0 * s1) ** 0.5, val("a3_bitset_len", s1) * 1.6),
                        ha="center", fontsize=9, color=C_BEST, fontweight="bold")
            break

    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel(f"字母表大小 σ（固定 n={data['n']}）")
    ax.set_ylabel("耗时（ms，对数轴）")
    ax.set_title("复杂度更优不等于永远更快：σ 决定谁赢", fontsize=12, pad=12)
    ax.legend(frameon=False, fontsize=9, loc="upper right")
    fig.tight_layout()
    fig.savefig(os.path.join(CHARTS, "alphabet.png"), facecolor="#FBF8F4")
    plt.close(fig)
    return cross


def chart_shape(data: dict) -> None:
    """固定 m 扫 n：证明两者都是 O(n)，差别只在斜率常数。"""
    rows = data["rows"]
    arms = ["a1l_rolling", "a3_bitset_len"]
    colors = {"a1l_rolling": C_BASE, "a3_bitset_len": C_BEST}

    fig, ax = plt.subplots(figsize=(9.2, 5.0), dpi=160)
    _style(ax)
    for arm in arms:
        pts = sorted((r["n"], r["ms"]) for r in rows if r["arm"] == arm)
        ax.plot([p[0] for p in pts], [p[1] for p in pts], marker="o", markersize=5,
                linewidth=2.0, color=colors[arm],
                label=f"{LABEL[arm]}  slope={data['slopes'][arm]:.2f}", zorder=3)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel(f"较长串长度 n（固定短串 m={data['m']}）")
    ax.set_ylabel("耗时（ms，对数轴）")
    ax.set_title("固定 m 扫 n：两条线平行，同阶只差常数", fontsize=12, pad=12)
    ax.legend(frameon=False, fontsize=9, loc="upper left")
    fig.tight_layout()
    fig.savefig(os.path.join(CHARTS, "shape.png"), facecolor="#FBF8F4")
    plt.close(fig)


def chart_lang(data: dict) -> None:
    """跨语言图：用稳健版数据（每配置多次独立进程），画中位数 + min–max 误差带。"""
    rows = data["rows"]
    sizes = sorted({r["n"] for r in rows})
    lang_color = {"C": "#8C5A3C", "Java": "#C98B4B", "Python": "#B4472E"}
    lang_marker = {"C": "o", "Java": "s", "Python": "D"}
    fig, axes = plt.subplots(1, 2, figsize=(11.6, 4.9), dpi=160, sharey=True)
    for ax, mode in zip(axes, ("dp", "bitset")):
        _style(ax)
        for lang in ("C", "Java", "Python"):
            pts = sorted((r["n"], r) for r in rows
                         if r["lang"] == lang and r["mode"] == mode)
            if not pts:
                continue
            xs = [p[0] for p in pts]
            med = [p[1]["median"] for p in pts]
            lo = [p[1]["min"] for p in pts]
            hi = [p[1]["max"] for p in pts]
            ax.fill_between(xs, lo, hi, color=lang_color[lang], alpha=0.18, zorder=2)
            ax.plot(xs, med, marker=lang_marker[lang], markersize=6, linewidth=2.2,
                    color=lang_color[lang], label=lang, zorder=3)
            ax.annotate(f"{med[-1]:.0f}", (xs[-1], med[-1]), textcoords="offset points",
                        xytext=(7, -3), fontsize=8.5, color=lang_color[lang],
                        fontweight="bold")
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel("字符串长度 n")
        ax.set_title("两行滚动 DP" if mode == "dp" else "位并行", fontsize=11)
        ax.legend(frameon=False, fontsize=9, loc="upper left")
    axes[0].set_ylabel("耗时（ms，对数轴；线=中位数，带=min–max）")
    fig.suptitle("同一算法三种语言：位并行把 Python 与 C 的差距从 74× 压到 4.7×",
                 fontsize=12, y=0.99)
    fig.tight_layout()
    fig.savefig(os.path.join(CHARTS, "lang.png"), facecolor="#FBF8F4")
    plt.close(fig)


def md_tables(data: dict, lang: dict | None) -> str:
    out = []
    rows = data["time"]
    by_n: dict[int, dict[str, float]] = {}
    for r in rows:
        by_n.setdefault(r["n"], {})[r["arm"]] = r["ms"]
    sizes = sorted(by_n)

    out.append("### 表 1 · Python 各臂耗时与加速比（ms，best-of-N，独立进程）\n")
    header = "| 实现 | " + " | ".join(f"n={n}" for n in sizes) + " |"
    out.append(header)
    out.append("|---" * (len(sizes) + 1) + "|")
    order = ["a0_baseline", "a1a_syntax", "a1b_two_branch", "a1l_rolling",
             "a2_list_backtrack", "a3_bitset_len", "a4_bitset_seq", "a5_hirschberg"]
    for arm in order:
        cells = []
        for n in sizes:
            t = by_n[n].get(arm)
            if t is None:
                cells.append("—")
                continue
            base = by_n[n]["a0_baseline"]
            cells.append(f"{t:.2f}（**{base / t:.1f}×**）")
        out.append(f"| {LABEL[arm]} | " + " | ".join(cells) + " |")

    sc = data.get("scaling")
    if sc:
        out.append("\n### 表 2 · 复杂度指数（log-log 最小二乘斜率）\n")
        out.append("| 实现 | 整段拟合 | 理论值 | 分段斜率（相邻点） |")
        out.append("|---|---|---|---|")
        for arm, d in sc.items():
            theory = {
                "a0_baseline": "2.0",
                "a1l_rolling": "2.0",
                "a3_bitset_len": "2.0（等长时，常数 1/64）",
            }.get(arm, "—")
            segs = d.get("segments") or []
            seg_txt = " → ".join(f"{s['slope']:.2f}" for s in segs) if segs else "—"
            out.append(f"| {LABEL.get(arm, arm)} | {d['slope']:.3f} | {theory} | {seg_txt} |")

    sp = data.get("space")
    if sp:
        sp_by_n: dict[int, dict[str, float]] = {}
        for r in sp:
            sp_by_n.setdefault(r["n"], {})[r["arm"]] = r["peak_mb"]
        sp_sizes = sorted(sp_by_n)
        out.append("\n### 表 3 · 峰值内存（MB，tracemalloc，min-of-N）\n")
        out.append("| 实现 | " + " | ".join(f"n={n}" for n in sp_sizes) + " |")
        out.append("|---" * (len(sp_sizes) + 1) + "|")
        for arm in order:
            cells = [f"{sp_by_n[n][arm]:.3f}" if arm in sp_by_n[n] else "—" for n in sp_sizes]
            out.append(f"| {LABEL[arm]} | " + " | ".join(cells) + " |")

    if lang:
        runs = lang.get("runs", "?")
        out.append(f"\n### 表 4 · 跨语言对比（ms，{runs} 次独立进程，min / median / max）\n")
        lg_sizes = sorted({r["n"] for r in lang["rows"]})
        for mode, title in (("dp", "两行滚动 DP"), ("bitset", "位并行")):
            out.append(f"**{title}**\n")
            out.append("| 语言 | " + " | ".join(f"n={n}" for n in lg_sizes) + " |")
            out.append("|---" * (len(lg_sizes) + 1) + "|")
            for lname in ("C", "Java", "Python"):
                cells = []
                for n in lg_sizes:
                    hit = [r for r in lang["rows"]
                           if r["lang"] == lname and r["mode"] == mode and r["n"] == n]
                    cells.append(
                        f"{hit[0]['min']:.3f} / {hit[0]['median']:.3f} / {hit[0]['max']:.3f}"
                        if hit else "—")
                out.append(f"| {lname} | " + " | ".join(cells) + " |")
            out.append("")
    return "\n".join(out)


def md_alphabet(alpha: dict | None, shape: dict | None) -> str:
    out = []
    if alpha:
        rows = alpha["rows"]
        sigmas = sorted({r["sigma"] for r in rows})
        arms = ["a0_baseline", "a1l_rolling", "a3_bitset_len", "a6_hunt_szymanski_len"]
        out.append(f"\n### 表 5 · 字母表扫描（固定 n={alpha['n']}，ms）\n")
        out.append("| σ | 匹配点 r | " + " | ".join(LABEL[a] for a in arms) + " | 赢家 |")
        out.append("|---" * (len(arms) + 3) + "|")
        for s in sigmas:
            vals = {}
            for a in arms:
                hit = [r for r in rows if r["arm"] == a and r["sigma"] == s]
                if hit:
                    vals[a] = hit[0]["ms"]
            r_cnt = next(r["r"] for r in rows if r["sigma"] == s)
            win = min(vals, key=vals.get) if vals else None
            cells = [f"{vals[a]:.3f}" if a in vals else "—" for a in arms]
            out.append(f"| {s} | {r_cnt} | " + " | ".join(cells)
                       + f" | {LABEL[win] if win else '—'} |")
    if shape:
        out.append(f"\n### 表 6 · 固定 m={shape['m']} 扫 n（ms）\n")
        ns = sorted({r["n"] for r in shape["rows"]})
        arms = ["a1l_rolling", "a3_bitset_len"]
        out.append("| n | " + " | ".join(LABEL[a] for a in arms) + " | 倍数 |")
        out.append("|---" * (len(arms) + 2) + "|")
        for n in ns:
            vals = {a: next(r["ms"] for r in shape["rows"] if r["arm"] == a and r["n"] == n) for a in arms}
            out.append(f"| {n} | " + " | ".join(f"{vals[a]:.3f}" for a in arms)
                       + f" | {vals['a1l_rolling'] / vals['a3_bitset_len']:.1f}× |")
        out.append("\n拟合斜率：" + "，".join(
            f"{LABEL[a]} {shape['slopes'][a]:.3f}" for a in arms))
    return "\n".join(out)


def main() -> int:
    os.makedirs(CHARTS, exist_ok=True)
    data = load(RES)
    lang = load(RES_LANG)
    alpha = load(RES_ALPHA)
    shape = load(RES_SHAPE)
    if data is None:
        print(f"缺少 {RES}，先跑 bench.py")
        return 1

    chart_speedup(data)
    chart_scaling(data)
    chart_space(data)
    if lang:
        chart_lang(lang)
    cross = chart_alphabet(alpha) if alpha else None
    if shape:
        chart_shape(shape)

    md = md_tables(data, lang) + md_alphabet(alpha, shape)
    with open(os.path.join(HERE, "report_tables.md"), "w", encoding="utf-8") as f:
        f.write(f"<!-- 由 make_report.py 生成 / Python {platform.python_version()} -->\n\n{md}\n")

    print("已生成：")
    for f in sorted(os.listdir(CHARTS)):
        print("  charts/" + f)
    print("  report_tables.md")
    if cross:
        print(f"\n交叉点在 σ ∈ [{cross[0]}, {cross[1]}] 之间")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
