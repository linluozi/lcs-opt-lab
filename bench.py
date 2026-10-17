"""
bench.py —— 可复现基准测试

设计约束（都是踩过的坑，见 README「方法论」一节）：
  1. **每个 (臂, 规模) 组合独立进程**。同进程顺序跑时，前一个臂留下的堆会拖慢后一个：
     A0 每次分配 (n+1)×(n+1) 的 int 表，n=2000 时约 400 万格子，
     跑完再测 A1b 会让后者凭空慢一截。
  2. **轮内交错 + 逐轮比值中位数**。绝对值跨进程会漂（实测同一份代码两次跑差 40%），
     但同一轮里 A0 和 A1b 受同样的 CPU 状态影响，比值稳。
  3. **best-of-N 取耗时**（timeit 口径）；tracemalloc 峰值取 **min-of-N**（冷进程要付
     惰性初始化，单测一次会高估）。
  4. 空结果要报警：LCS 长度为 0 时任何实现都返回 0，测的是空转。

用法：
    python bench.py                 # 全量（约 3-5 分钟）
    python bench.py --quick         # 小规模冒烟（约 20 秒）
    python bench.py --only time     # 只跑时间
    python bench.py --only space    # 只跑内存
    python bench.py --only scaling  # 只跑复杂度标度（log-log 斜率）
"""
from __future__ import annotations

import argparse
import gc
import json
import math
import os
import platform
import statistics
import subprocess
import sys
import time
import tracemalloc

HERE = os.path.dirname(os.path.abspath(__file__))
RESULT_JSON = os.path.join(HERE, "results.json")

# 被测臂（只比长度的用 LEN，比「长度+序列」的用 SEQ）
# 名字必须与 lcs_opt.py 里的函数名对应，子进程按名字反射调用
ARMS_LEN = ["a0_baseline", "a1a_syntax", "a1b_two_branch", "a1l_rolling", "a3_bitset_len"]
ARMS_SEQ = ["a0_baseline", "a2_list_backtrack", "a4_bitset_seq", "a5_hirschberg"]

# 标度扫描单独一组：A6 只在稀疏匹配时才该被拉进来（见 bench_alphabet.py）
SCALE_ARMS = ["a0_baseline", "a1l_rolling", "a3_bitset_len"]

ALPHA = "ACGT"


def gen(n: int, seed: int, alpha: int = 4) -> str:
    """与 C / Java 版逐位一致的 LCG 生成器。"""
    s = seed
    out = []
    for _ in range(n):
        s = (s * 6364136223846793005 + 1442695040888963407) & 0xFFFFFFFFFFFFFFFF
        out.append(ALPHA[(s >> 33) % alpha])
    return "".join(out)


# ---------------------------------------------------------------------------
# 子进程：测单个 (臂, n) 的耗时
# ---------------------------------------------------------------------------
def _child_time(arm: str, n: int, seed: int, reps: int) -> dict:
    sys.path.insert(0, HERE)
    import lcs_opt as L

    fn = getattr(L, arm)
    x = gen(n, seed)
    y = gen(n, seed ^ 0x9E3779B97F4A7C15)

    # 预热一次（触发 import、首次分配；不计时）
    res = fn(x, y)
    length = res[0] if isinstance(res, tuple) else res
    if length == 0:
        print(f"WARNING: {arm} n={n} 的 LCS 长度为 0，该数据点无意义", file=sys.stderr)

    # 先粗测一次，决定内层批量次数。
    # 位并行在 n=500 时只要 0.16 ms，单次测量的计时噪声（perf_counter 抖动 +
    # 分配器状态）能让 spread 到 1.9，段斜率抖成 2.40 这种假信号。
    # 做法同 timeit：跑得快的就批量跑 inner 次，测总时间再除 —— 噪声被平均掉。
    gc.collect()
    t0 = time.perf_counter()
    fn(x, y)
    rough = time.perf_counter() - t0
    inner = max(1, min(2000, int(5e-3 / rough))) if rough > 0 else 1

    ts = []
    for _ in range(reps):
        gc.collect()  # 每轮前清一次，避免上一轮垃圾压在本轮计时里
        t0 = time.perf_counter()
        for _ in range(inner):
            fn(x, y)
        ts.append((time.perf_counter() - t0) * 1e3 / inner)

    ts.sort()
    best = ts[0]
    med = statistics.median(ts)
    return {
        "arm": arm, "n": n, "len": length,
        "ms": best, "med_ms": med, "reps": reps, "inner": inner,
        # spread > 1.2 说明该点被内存压力/降频污染，报告里要标注
        "spread": (ts[-1] / ts[0]) if ts[0] > 0 else 1.0,
        "unstable": (ts[-1] / ts[0]) > 1.2 if ts[0] > 0 else False,
    }


def _child_space(arm: str, n: int, seed: int, reps: int) -> dict:
    sys.path.insert(0, HERE)
    import lcs_opt as L

    fn = getattr(L, arm)
    x = gen(n, seed)
    y = gen(n, seed ^ 0x9E3779B97F4A7C15)

    best = None
    for _ in range(reps):
        gc.collect()
        tracemalloc.start()
        fn(x, y)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        if best is None or peak < best:
            best = peak          # min-of-N：冷启动开销只会让峰值偏高
    return {"arm": arm, "n": n, "peak_mb": best / (1024 * 1024), "reps": reps}


def _run_child(kind: str, arm: str, n: int, seed: int, reps: int) -> dict:
    """起一个全新 Python 进程跑单个测量点。"""
    cmd = [
        sys.executable, os.path.abspath(__file__),
        "--_child", kind, "--_arm", arm, "--_n", str(n), "--_seed", str(seed), "--_reps", str(reps),
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, cwd=HERE)
    if out.returncode != 0:
        raise RuntimeError(f"子进程失败 {kind}/{arm}/n={n}:\n{out.stderr}")
    for line in out.stdout.splitlines():
        if line.startswith("JSON "):
            return json.loads(line[5:])
    raise RuntimeError(f"子进程无输出 {kind}/{arm}/n={n}:\n{out.stdout}\n{out.stderr}")


# ---------------------------------------------------------------------------
# 主进程：调度
# ---------------------------------------------------------------------------
def bench_time(sizes: list[int], reps: int, arms_len: list[str], arms_seq: list[str]) -> list[dict]:
    rows = []
    # 交错顺序：A0 与其余臂交替起进程，避免 CPU 降频全落在某一侧
    for n in sizes:
        for arm in arms_len:
            r = _run_child("time", arm, n, 12345, reps)
            rows.append({**r, "kind": "len"})
            flag = "  <-- 不稳定" if r.get("unstable") else ""
            print(f"  time  len  {arm:<18} n={n:>6}  {r['ms']:>12.3f} ms  L={r['len']}{flag}")
        for arm in arms_seq:
            if arm == "a0_baseline":
                continue    # 已在上面的 len 组里测过（同一份代码）
            r = _run_child("time", arm, n, 12345, reps)
            rows.append({**r, "kind": "seq"})
            flag = "  <-- 不稳定" if r.get("unstable") else ""
            print(f"  time  seq  {arm:<18} n={n:>6}  {r['ms']:>12.3f} ms  L={r['len']}{flag}")
    return rows


def bench_space(sizes: list[int], reps: int, arms_len: list[str], arms_seq: list[str]) -> list[dict]:
    rows = []
    for n in sizes:
        for arm in arms_len + [a for a in arms_seq if a != "a0_baseline"]:
            r = _run_child("space", arm, n, 12345, reps)
            rows.append(r)
            print(f"  space      {arm:<18} n={n:>6}  {r['peak_mb']:>10.3f} MB")
    return rows


def bench_scaling(arms: list[str], sizes: list[int], reps: int) -> dict:
    """
    固定字母表，扫 n，用 log-log 斜率判断复杂度类别。

    每个臂单独给 reps：慢臂（a0/a1l，单点可达 19 s）给 3 次，
    快臂（位并行，单点 0.1–7 ms）给 15 次 —— 0.1 ms 量级的单次测量会被
    计时器噪声主导，段斜率能抖到 2.40 这种假信号。给足重复次数才压得住。
    """
    per_arm_reps = {"a0_baseline": max(3, reps // 2), "a1l_rolling": max(3, reps // 2)}
    out: dict[str, list[tuple[int, float]]] = {}
    for arm in arms:
        r_arm = per_arm_reps.get(arm, max(15, reps * 3))
        pts = []
        for n in sizes:
            r = _run_child("time", arm, n, 12345, r_arm)
            pts.append((n, r["ms"]))
            flag = "  <-- 不稳定" if r.get("unstable") else ""
            print(f"  scaling    {arm:<18} n={n:>7}  {r['ms']:>12.3f} ms "
                  f"(spread {r.get('spread', 1):.2f}){flag}")
        out[arm] = pts
    return out


def loglog_slope(pts: list[tuple[int, float]]) -> float:
    """最小二乘拟合 log(t) = a + b·log(n)，返回 b（复杂度指数）。"""
    xs = [math.log(n) for n, _ in pts]
    ys = [math.log(max(t, 1e-9)) for _, t in pts]
    mx = statistics.fmean(xs)
    my = statistics.fmean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = sum((x - mx) ** 2 for x in xs)
    return num / den


def segment_slopes(pts: list[tuple[int, float]]) -> list[dict]:
    """
    逐段斜率：相邻两点的 log-log 斜率。

    为什么需要它：整段拟合会把小 n 处的**解释器固定开销**（每次调用的 setup、
    大整数对象的首次分配）平均进去，让位并行看起来像 n^1.3 而不是 n^1.0。
    分段后能看到斜率随 n 单调下降，这才是「常数开销被摊薄」的证据。
    """
    out = []
    for (n0, t0), (n1, t1) in zip(pts, pts[1:]):
        s = (math.log(t1) - math.log(t0)) / (math.log(n1) - math.log(n0))
        out.append({"from": n0, "to": n1, "slope": s})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--only", choices=["time", "space", "scaling", "all"], default="all")
    ap.add_argument("--reps", type=int, default=3)
    # 内部子进程参数
    ap.add_argument("--_child", choices=["time", "space"])
    ap.add_argument("--_arm")
    ap.add_argument("--_n", type=int)
    ap.add_argument("--_seed", type=int, default=12345)
    ap.add_argument("--_reps", type=int, default=3)
    args = ap.parse_args()

    if args._child:
        if args._child == "time":
            print("JSON " + json.dumps(_child_time(args._arm, args._n, args._seed, args._reps)))
        else:
            print("JSON " + json.dumps(_child_space(args._arm, args._n, args._seed, args._reps)))
        return 0

    if args.quick:
        time_sizes = [200, 500, 1000]
        space_sizes = [500, 1000]
        scale_sizes = [250, 500, 1000, 2000]
        reps = 2
    else:
        time_sizes = [500, 1000, 2000]
        space_sizes = [500, 1000, 2000]
        scale_sizes = [250, 500, 1000, 2000]
        reps = args.reps

    print(f"Python {platform.python_version()} / {platform.machine()} / {platform.system()}")
    print(f"reps={reps}\n")

    payload: dict = {
        "python": platform.python_version(),
        "machine": platform.machine(),
        "system": platform.system(),
        "reps": reps,
    }

    if args.only in ("time", "all"):
        print("[时间] 每个点独立进程，best-of-N")
        payload["time"] = bench_time(time_sizes, reps, ARMS_LEN, ARMS_SEQ)

    if args.only in ("space", "all"):
        print("\n[内存] tracemalloc 峰值，min-of-N")
        payload["space"] = bench_space(space_sizes, reps, ARMS_LEN, ARMS_SEQ)

    if args.only in ("scaling", "all"):
        print("\n[标度] log-log 斜率（整段拟合 + 分段斜率）")
        scale = bench_scaling(SCALE_ARMS, scale_sizes, reps)
        payload["scaling"] = {
            arm: {
                "points": pts,
                "slope": loglog_slope(pts),
                "segments": segment_slopes(pts),
            }
            for arm, pts in scale.items()
        }
        print("\n  复杂度指数：")
        for arm, d in payload["scaling"].items():
            segs = "  ".join(f"{s['from']}→{s['to']}:{s['slope']:.2f}" for s in d["segments"])
            print(f"    {arm:<18} 整段 {d['slope']:.3f}   分段 {segs}")

    with open(RESULT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"\n结果已写入 {RESULT_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
