"""
bench_alphabet.py —— 扫字母表大小 σ，看「换复杂度类别」的交叉点在哪

这是本项目最重要的一张图。LCS 的匹配点数 r ≈ n²/σ：
  * σ 小（DNA/二进制）⇒ r 巨大 ⇒ Hunt-Szymanski 的 O(r log n) 反而更差，位并行赢
  * σ 大（中文/ID/URL）⇒ r ≈ n ⇒ Hunt-Szymanski 的 O(n log n) 碾压 O(n²)

固定 n，只改 σ，三臂各测一次；每个点独立进程。

用法：
    python bench_alphabet.py
    python bench_alphabet.py --n 4000 --alphas 2 4 16 64 256 1024 4096
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "results_alphabet.json")


def _child(arm: str, n: int, sigma: int, seed: int, reps: int) -> dict:
    sys.path.insert(0, HERE)
    import gc
    import time
    import lcs_opt as L

    # 用 Unicode 私用区造 σ 个不同字符，保证 σ 精确可控
    pool = [chr(0xE000 + i) for i in range(sigma)]
    M = 0xFFFFFFFFFFFFFFFF
    s = seed

    def gen(cnt: int) -> str:
        nonlocal s
        out = []
        for _ in range(cnt):
            s = (s * 6364136223846793005 + 1442695040888963407) & M
            out.append(pool[(s >> 33) % sigma])
        return "".join(out)

    x = gen(n)
    y = gen(n)
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
    # 匹配点数 r（只数，不计时）
    from collections import Counter
    cnt = Counter(x)
    r = sum(cnt[ch] * y.count(ch) for ch in cnt)
    return {"arm": arm, "n": n, "sigma": sigma, "len": length, "ms": best * 1e3, "r": r}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=4000)
    ap.add_argument("--alphas", type=int, nargs="+", default=[2, 4, 16, 64, 256, 1024, 4096, 16384])
    ap.add_argument("--reps", type=int, default=2)
    ap.add_argument("--_child", action="store_true")
    ap.add_argument("--_arm")
    ap.add_argument("--_sigma", type=int)
    ap.add_argument("--_n", type=int)
    args = ap.parse_args()

    if args._child:
        print("JSON " + json.dumps(_child(args._arm, args._n, args._sigma, 12345, args.reps)))
        return 0

    arms = ["a0_baseline", "a1l_rolling", "a3_bitset_len", "a6_hunt_szymanski_len"]
    rows = []
    print(f"n={args.n}，reps={args.reps}，Python {platform.python_version()}\n")
    print(f"{'sigma':>7} {'r (匹配点)':>12} " + " ".join(f"{a.replace('_len',''):>18}" for a in arms))
    for sigma in args.alphas:
        line = []
        for arm in arms:
            # A0 是 O(n²)，σ 大时并不变慢，但 n 大时会很慢 —— 单独限次
            r_arm = max(1, args.reps // 2) if arm == "a0_baseline" else args.reps
            cmd = [sys.executable, os.path.abspath(__file__), "--_child",
                   "--_arm", arm, "--_n", str(args.n), "--_sigma", str(sigma),
                   "--reps", str(r_arm)]
            out = subprocess.run(cmd, capture_output=True, text=True, cwd=HERE)
            if out.returncode != 0:
                raise SystemExit(f"子进程失败 {arm} sigma={sigma}\n{out.stderr}")
            d = json.loads([l for l in out.stdout.splitlines() if l.startswith("JSON ")][0][5:])
            rows.append(d)
            line.append(f"{d['ms']:>15.3f} ms")
        print(f"{sigma:>7} {rows[-1]['r']:>12} " + " ".join(line))

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"n": args.n, "rows": rows}, f, ensure_ascii=False, indent=2)
    print(f"\n已写入 {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
