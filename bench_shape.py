"""
bench_shape.py —— 固定短串、拉长另一串，验证位并行的真实复杂度

位并行 LCS 的复杂度是 **O(n · ⌈m/64⌉)**，不是 O(n)。
当 n == m 时它退化成 n²/64，log-log 斜率看起来「应该」是 2 —— 但在本机小规模下
解释器固定开销把斜率压到了 1.3 左右，很容易被误读成「它变成了线性算法」。

正确的验证方式：**固定 m，只扫 n**。此时理论曲线是严格直线（斜率 1），
因为 ⌈m/64⌉ 是常数。若斜率确实是 1，才说明实现没有隐藏的 O(n²) 项。

同时对 DP 做同样的事：DP 固定 m 时也是 O(n)，斜率同样应为 1 ——
两者在「固定 m」这条轴上都线性，差别在**斜率常数**（1 vs m/64）。

用法：
    python bench_shape.py
"""
from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "results_shape.json")


def _child(arm: str, m: int, n: int, reps: int) -> dict:
    sys.path.insert(0, HERE)
    import gc
    import time
    import lcs_opt as L

    ALPHA = "ACGT"
    M64 = 0xFFFFFFFFFFFFFFFF

    def gen(cnt: int, seed: int) -> str:
        s = seed
        out = []
        for _ in range(cnt):
            s = (s * 6364136223846793005 + 1442695040888963407) & M64
            out.append(ALPHA[(s >> 33) % 4])
        return "".join(out)

    x = gen(m, 12345)                  # 短串：决定 bit 宽度
    y = gen(n, 12345 ^ 0x9E3779B97F4A7C15)
    fn = getattr(L, arm)

    res = fn(x, y)
    length = res[0] if isinstance(res, tuple) else res
    best = float("inf")
    for _ in range(reps):
        gc.collect()
        t0 = time.perf_counter()
        fn(x, y)
        dt = time.perf_counter() - t0
        if dt < best:
            best = dt
    return {"arm": arm, "m": m, "n": n, "len": length, "ms": best * 1e3}


def slope(pts: list[tuple[int, float]]) -> float:
    xs = [math.log(p[0]) for p in pts]
    ys = [math.log(max(p[1], 1e-12)) for p in pts]
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    return sum((a - mx) * (b - my) for a, b in zip(xs, ys)) / sum((a - mx) ** 2 for a in xs)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--m", type=int, default=512)
    ap.add_argument("--ns", type=int, nargs="+", default=[2000, 4000, 8000, 16000, 32000])
    ap.add_argument("--reps", type=int, default=2)
    ap.add_argument("--_child", action="store_true")
    ap.add_argument("--_arm")
    ap.add_argument("--_m", type=int)
    ap.add_argument("--_n", type=int)
    args = ap.parse_args()

    if args._child:
        print("JSON " + json.dumps(_child(args._arm, args._m, args._n, args.reps)))
        return 0

    arms = ["a1l_rolling", "a3_bitset_len"]
    print(f"固定 m={args.m}，扫 n（理论：两者都应斜率≈1，差别在常数）\n")
    print(f"{'n':>8} " + " ".join(f"{a:>16}" for a in arms))
    rows = []
    series: dict[str, list[tuple[int, float]]] = {a: [] for a in arms}
    for n in args.ns:
        cells = []
        for arm in arms:
            cmd = [sys.executable, os.path.abspath(__file__), "--_child",
                   "--_arm", arm, "--_m", str(args.m), "--_n", str(n), "--reps", str(args.reps)]
            out = subprocess.run(cmd, capture_output=True, text=True, cwd=HERE)
            if out.returncode != 0:
                raise SystemExit(f"失败 {arm} n={n}\n{out.stderr}")
            d = json.loads([l for l in out.stdout.splitlines() if l.startswith("JSON ")][0][5:])
            rows.append(d)
            series[arm].append((n, d["ms"]))
            cells.append(f"{d['ms']:>13.3f} ms")
        print(f"{n:>8} " + " ".join(cells))

    print("\n斜率：")
    for arm, pts in series.items():
        print(f"  {arm:<16} slope = {slope(pts):.3f}")
    print("\n判读：两者斜率都≈1 说明固定 m 时都是 O(n)；"
          "\n      位并行的优势来自斜率常数 ≈ m/64，而不是渐近阶不同。")

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"m": args.m, "rows": rows,
                   "slopes": {a: slope(p) for a, p in series.items()}},
                  f, ensure_ascii=False, indent=2)
    print(f"\n已写入 {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
