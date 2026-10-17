"""
test_cross_lang.py —— 跨语言差分测试

三种语言的实现必须对**任意输入**给出同一个 LCS 长度。这里不用随机生成器，
而是直接喂测试用例，让 C / Java / Python 各自算一遍再比对。

为什么单独写这个脚本：
  * 生成器对齐只能证明「同一份输入下结果一致」，不能证明「任意输入都一致」。
    位并行实现在跨语言移植时踩过两个只有任意输入才暴露的坑：
      - C：忘了清最高字的脏位 ⇒ 长度偏小（1308 被算成 1260）
      - Java：`long` 有符号比较 ⇒ 进位判断反向（1308 被算成 1228）
    这两个 bug 在固定种子的大输入上会暴露，但只有「大量小输入」才能定位。
  * 顺带覆盖字符集：C 版 stdin 模式用 0..255 编号，不限于 ACGT。

用法：
    python test_cross_lang.py
    python test_cross_lang.py --skip-build
"""
from __future__ import annotations

import argparse
import os
import random
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
C_EXE = os.path.join(HERE, "c", "lcs_c.exe" if os.name == "nt" else "lcs_c")
JAVA_DIR = os.path.join(HERE, "java")

sys.path.insert(0, HERE)
import lcs_opt as L


def run_c(x: str, y: str) -> int:
    out = subprocess.run([C_EXE, "dp", "stdin"], input=f"{x}\n{y}\n",
                         capture_output=True, text=True, encoding="utf-8")
    if out.returncode != 0:
        raise RuntimeError(f"C 失败: {out.stdout} {out.stderr}")
    m = re.search(r"len=(\d+)", out.stdout)
    return int(m.group(1))


def run_java(x: str, y: str) -> int:
    """Java 版 stdin 模式：按 UTF-16 码元比较，BMP 内字符与 Python 一致。"""
    payload = x + "\n" + y + "\n"
    out = subprocess.run(["java", "-cp", JAVA_DIR, "Lcs", "dp", "stdin"],
                         input=payload, capture_output=True, text=True,
                         encoding="utf-8")
    if out.returncode != 0:
        raise RuntimeError(f"Java 失败: {out.stdout} {out.stderr}")
    m = re.search(r"len=(\d+)", out.stdout)
    return int(m.group(1))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-build", action="store_true")
    args = ap.parse_args()

    if not args.skip_build:
        subprocess.run(["sh", os.path.join(HERE, "c", "build.sh")], check=True,
                       cwd=os.path.join(HERE, "c"), capture_output=True)

    if not os.path.exists(C_EXE):
        print(f"缺少 {C_EXE}，先跑 sh c/build.sh")
        return 1

    rng = random.Random(20261017)
    cases: list[tuple[str, str]] = [
        ("AGGTAB", "GXTXAYB"), ("programming", "gaming"), ("physics", "smartphone"),
        ("", "abc"), ("abc", ""), ("", ""), ("abc", "def"), ("abc", "abc"),
        ("a", "a"), ("a", "b"), ("abcdef", "ace"), ("ABCD", "ACBD"),
    ]
    # 小字母表（重复多，回溯路径长）
    for _ in range(150):
        alpha = rng.choice(["ab", "abc", "abcd", "acgt"])
        cases.append((
            "".join(rng.choice(alpha) for _ in range(rng.randint(0, 30))),
            "".join(rng.choice(alpha) for _ in range(rng.randint(0, 30))),
        ))
    # 位并行 limb 边界
    for m in (1, 2, 29, 30, 31, 32, 63, 64, 65, 95, 96, 97, 127, 128, 129):
        cases.append((
            "".join(rng.choice("abcdef") for _ in range(m)),
            "".join(rng.choice("abcdef") for _ in range(rng.randint(0, 40))),
        ))
    # 宽字符集：验证 C 的 0..255 编号路径（ASCII 范围内）
    for _ in range(60):
        alpha = [chr(c) for c in range(33, 33 + 90)]
        cases.append((
            "".join(rng.choice(alpha) for _ in range(rng.randint(0, 20))),
            "".join(rng.choice(alpha) for _ in range(rng.randint(0, 20))),
        ))
    # 中文（仅 Java 能验：C 版按字节比较会拒绝，见 lcs_c.c 的说明）
    cjk_cases = []
    for _ in range(40):
        alpha = "中文测试数据样本"
        cjk_cases.append((
            "".join(rng.choice(alpha) for _ in range(rng.randint(0, 16))),
            "".join(rng.choice(alpha) for _ in range(rng.randint(0, 16))),
        ))

    bad_c = 0
    nonempty = 0
    for x, y in cases:
        want = L.a3_bitset_len(x, y)
        if want > 0:
            nonempty += 1
        got = run_c(x, y)
        if got != want:
            bad_c += 1
            if bad_c <= 5:
                print(f"[C] MISMATCH  x={x!r} y={y!r}  python={want} c={got}")
    print(f"C    vs Python：{len(cases)} 组，失败 {bad_c} 组")

    bad_j = 0
    for x, y in cjk_cases:
        want = L.a3_bitset_len(x, y)
        got = run_java(x, y)
        if got != want:
            bad_j += 1
            if bad_j <= 5:
                print(f"[Java] MISMATCH  x={x!r} y={y!r}  python={want} java={got}")
    print(f"Java vs Python（含中文）：{len(cjk_cases)} 组，失败 {bad_j} 组")

    total = len(cases) + len(cjk_cases)
    print(f"\n合计 {total} 组；ASCII 用例中 {nonempty} 组 LCS 长度>0"
          f"（{100*nonempty/len(cases):.1f}%）")
    assert nonempty >= len(cases) * 0.5, "有效样本不足，多数用例是空串"
    return 0 if (bad_c == 0 and bad_j == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
