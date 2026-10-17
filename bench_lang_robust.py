"""
bench_lang_robust.py —— 跨语言基准的稳健版：每个配置多次独立进程，报告区间

为什么需要它：`bench_lang.py` 每个配置只起一次进程（内部 best-of-N），
实测同一份 C 位并行代码在 n=20000 时，不同次运行给出 6.86 / 6.97 / 7.05 /
9.53 / 14.20 ms —— **单次运行的点值不可引用**。这里改成每配置 R 次独立进程，
报告 min / median / max，并把区间宽度一并写出。

用法：
    python bench_lang_robust.py                     # 默认 5 次
    python bench_lang_robust.py --runs 7 --sizes 20000
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import statistics
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
C_EXE = os.path.join(HERE, "c", "lcs_c.exe" if os.name == "nt" else "lcs_c")
JAVA_DIR = os.path.join(HERE, "java")
OUT = os.path.join(HERE, "results_lang_robust.json")

SEED = 12345
ALPHA = 4


def _c(mode: str, n: int, reps: int) -> float:
    out = subprocess.run([C_EXE, mode, str(n), str(SEED), str(ALPHA), str(reps)],
                         capture_output=True, text=True)
    m = re.search(r"best_ms=([\d.]+)", out.stdout)
    if not m:
        raise RuntimeError(out.stderr)
    return float(m.group(1))


def _java(mode: str, n: int, reps: int) -> float:
    out = subprocess.run(["java", "-cp", JAVA_DIR, "Lcs", mode, str(n), str(SEED),
                          str(ALPHA), str(reps)], capture_output=True, text=True)
    m = re.search(r"best_ms=([\d.]+)", out.stdout)
    if not m:
        raise RuntimeError(out.stderr)
    return float(m.group(1))


def _py(arm: str, n: int, reps: int) -> float:
    out = subprocess.run([sys.executable, os.path.join(HERE, "bench.py"),
                          "--_child", "time", "--_arm", arm, "--_n", str(n),
                          "--_seed", str(SEED), "--_reps", str(reps)],
                         capture_output=True, text=True, cwd=HERE)
    for line in out.stdout.splitlines():
        if line.startswith("JSON "):
            return json.loads(line[5:])["ms"]
    raise RuntimeError(out.stderr)


def build() -> None:
    """
    编译 C 与 Java。

    .class / .exe 都在 .gitignore 里，所以从 GitHub 克隆下来的仓库没有编译产物 ——
    不先编译就直接跑，会得到一句 `RuntimeError: C 运行失败 ... ''` 这种没法定位的报错。
    """
    r = subprocess.run(["sh", os.path.join(HERE, "c", "build.sh")],
                       cwd=os.path.join(HERE, "c"), capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"C 编译失败：\n{r.stdout}\n{r.stderr}")
    print(f"  {r.stdout.strip()}")
    r = subprocess.run(["javac", "-d", ".", "Lcs.java"],
                       cwd=JAVA_DIR, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"Java 编译失败（需要 JDK）：\n{r.stdout}\n{r.stderr}")
    print("  javac ok")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--sizes", type=int, nargs="+", default=[1000, 5000, 20000])
    ap.add_argument("--skip-build", action="store_true")
    args = ap.parse_args()

    if not args.skip_build:
        build()

    print(f"Python {platform.python_version()} / {platform.machine()}")
    print(f"每配置 {args.runs} 次独立进程，每次内部 best-of-{args.reps}\n")

    arms = [
        ("C", "dp", lambda n: _c("dp", n, args.reps)),
        ("C", "bitset", lambda n: _c("bitset", n, args.reps)),
        ("Java", "dp", lambda n: _java("dp", n, args.reps)),
        ("Java", "bitset", lambda n: _java("bitset", n, args.reps)),
        ("Python", "dp", lambda n: _py("a1l_rolling", n, args.reps)),
        ("Python", "bitset", lambda n: _py("a3_bitset_len", n, args.reps)),
    ]

    rows = []
    for n in args.sizes:
        print(f"n={n}")
        for lang, mode, fn in arms:
            vals = sorted(fn(n) for _ in range(args.runs))
            lo, med, hi = vals[0], statistics.median(vals), vals[-1]
            rows.append({"lang": lang, "mode": mode, "n": n,
                         "min": lo, "median": med, "max": hi,
                         "spread": hi / lo if lo > 0 else 1.0})
            print(f"  {lang:<7} {mode:<7} min={lo:9.3f}  med={med:9.3f}  "
                  f"max={hi:9.3f}  spread={hi/lo:.2f}x")
        print()

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"runs": args.runs, "reps": args.reps, "rows": rows},
                  f, ensure_ascii=False, indent=2)
    print(f"已写入 {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
