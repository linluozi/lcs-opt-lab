"""
bench_lang.py —— 跨语言基准（Python / C / Java）

三者用**同一个 LCG 常量**生成同一份输入，因此 LCS 长度必须完全相同；
脚本会先断言长度一致，再比较耗时。长度不一致直接报错退出，不产出数字。

做法上的两个约束：
  * 每次测量都起**独立进程**（Python 是脚本、C 是 exe、Java 是 JVM）。
  * 每个语言内部用 best-of-N；跨语言比较用「同 n 同 seed」的同一批数据。
  * JVM 有 JIT 预热，第一次跑必然慢 —— 由各程序内部 reps 循环吸收，且程序自报 best。

用法：
    python bench_lang.py                    # 默认规模
    python bench_lang.py --sizes 1000 10000 50000
    python bench_lang.py --skip-build       # 跳过编译步骤
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
C_DIR = os.path.join(HERE, "c")
JAVA_DIR = os.path.join(HERE, "java")
OUT_JSON = os.path.join(HERE, "results_lang.json")

SEED = 12345
ALPHA = 4


def build_c() -> str:
    """编译 C 版本，返回可执行文件路径。"""
    exe = os.path.join(C_DIR, "lcs_c.exe" if os.name == "nt" else "lcs_c")
    script = os.path.join(C_DIR, "build.sh")
    out = subprocess.run(["sh", script], capture_output=True, text=True, cwd=C_DIR)
    if out.returncode != 0:
        raise RuntimeError(f"C 编译失败:\n{out.stdout}\n{out.stderr}")
    print(f"  {out.stdout.strip()}")
    return exe


def build_java() -> None:
    out = subprocess.run(["javac", "-d", ".", "Lcs.java"], capture_output=True, text=True, cwd=JAVA_DIR)
    if out.returncode != 0:
        raise RuntimeError(f"Java 编译失败:\n{out.stdout}\n{out.stderr}")
    print("  javac ok")


def run_c(exe: str, mode: str, n: int, reps: int) -> dict:
    out = subprocess.run([exe, mode, str(n), str(SEED), str(ALPHA), str(reps)],
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"C 运行失败 {mode} n={n}: {out.stderr}")
    m = re.search(r"len=(\d+) best_ms=([\d.]+)", out.stdout)
    if not m:
        raise RuntimeError(f"C 输出无法解析: {out.stdout}")
    return {"len": int(m.group(1)), "ms": float(m.group(2))}


def run_java(mode: str, n: int, reps: int) -> dict:
    out = subprocess.run(["java", "-cp", JAVA_DIR, "Lcs", mode, str(n), str(SEED), str(ALPHA), str(reps)],
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"Java 运行失败 {mode} n={n}: {out.stderr}")
    m = re.search(r"len=(\d+) best_ms=([\d.]+)", out.stdout)
    if not m:
        raise RuntimeError(f"Java 输出无法解析: {out.stdout}")
    return {"len": int(m.group(1)), "ms": float(m.group(2))}


def run_python(arm: str, n: int, reps: int) -> dict:
    """复用 bench.py 的子进程协议，保证与 bench.py 测的是同一份代码。"""
    cmd = [sys.executable, os.path.join(HERE, "bench.py"),
           "--_child", "time", "--_arm", arm, "--_n", str(n),
           "--_seed", str(SEED), "--_reps", str(reps)]
    out = subprocess.run(cmd, capture_output=True, text=True, cwd=HERE)
    if out.returncode != 0:
        raise RuntimeError(f"Python 运行失败 {arm} n={n}: {out.stderr}")
    for line in out.stdout.splitlines():
        if line.startswith("JSON "):
            d = json.loads(line[5:])
            return {"len": d["len"], "ms": d["ms"]}
    raise RuntimeError(f"Python 输出无法解析: {out.stdout}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", type=int, nargs="+", default=[1000, 5000, 20000])
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--skip-build", action="store_true")
    args = ap.parse_args()

    print(f"Python {platform.python_version()} / {platform.machine()}\n")
    if not args.skip_build:
        print("[编译]")
        exe = build_c()
        build_java()
    else:
        exe = os.path.join(C_DIR, "lcs_c.exe" if os.name == "nt" else "lcs_c")

    rows = []
    print("\n[测量] 每个点独立进程，best-of-N；三种语言共用同一份输入")
    for n in args.sizes:
        print(f"\n  n={n}  (alpha={ALPHA})")
        # 顺序：C → Java → Python，每轮都交错，避免降频全落在最后
        c_dp = run_c(exe, "dp", n, args.reps)
        j_dp = run_java("dp", n, args.reps)
        p_dp = run_python("a1l_rolling", n, args.reps)   # 与 C/Java 的 dp 同一算法、同一空间策略
        c_bs = run_c(exe, "bitset", n, args.reps)
        j_bs = run_java("bitset", n, args.reps)
        p_bs = run_python("a3_bitset_len", n, args.reps)

        # 正确性交叉校验：同一份输入，四种实现长度必须完全一致
        lens = {"c_dp": c_dp["len"], "java_dp": j_dp["len"], "py_dp": p_dp["len"],
                "c_bs": c_bs["len"], "java_bs": j_bs["len"], "py_bs": p_bs["len"]}
        if len(set(lens.values())) != 1:
            raise SystemExit(f"n={n} 各语言结果不一致: {lens}")
        L = c_dp["len"]
        print(f"    长度一致校验通过: L={L}")

        for lang, mode, r in (
            ("C", "dp", c_dp), ("Java", "dp", j_dp), ("Python", "dp", p_dp),
            ("C", "bitset", c_bs), ("Java", "bitset", j_bs), ("Python", "bitset", p_bs),
        ):
            rows.append({"lang": lang, "mode": mode, "n": n, "len": L, "ms": r["ms"]})
            print(f"    {lang:<7} {mode:<7} {r['ms']:>12.3f} ms")

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump({"seed": SEED, "alpha": ALPHA, "rows": rows}, f, ensure_ascii=False, indent=2)
    print(f"\n结果已写入 {OUT_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
