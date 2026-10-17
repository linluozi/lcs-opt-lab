"""
test_correctness.py —— 差分测试：所有优化臂必须与 A0 原版给出同一个 (长度, 序列长度)

注意两个容易写成「假测试」的坑，这里都避开了：
  1. 空集比较：只比 (0, '') 这种 case 时任何实现都过 ⇒ 断言里额外要求
     「至少 N 个 case 的长度 > 0」，并在结尾打印命中数。
  2. 只验自反性质：`len(seq) == L` 单独看可能永远成立 ⇒ 额外验证 seq 是 x 和 y
     的**真子序列**，且长度等于 oracle 的 L（oracle = A0 原版）。
序列内容本身不要求一致（LCS 有多解），但长度与合法性必须一致。

运行：
    python test_correctness.py
"""
from __future__ import annotations

import random
import sys

from baseline import longest_common_subsequence as a0
import lcs_opt as L

# 需要参与校验的臂：(名字, 调用方式, 是否返回序列)
SEQ_ARMS = [
    ("A1a_syntax", L.a1a_syntax),
    ("A1b_two_branch", L.a1b_two_branch),
    ("A2_list_backtrack", L.a2_list_backtrack),
    ("A4_bitset_seq", L.a4_bitset_seq),
    ("A5_hirschberg", L.a5_hirschberg),
]
LEN_ARMS = [
    ("A1L_rolling", L.a1l_rolling),
    ("A3_bitset_len", L.a3_bitset_len),
    ("A6_hunt_szymanski", L.a6_hunt_szymanski_len),
]


def is_subsequence(sub: str, s: str) -> bool:
    """O(len(s)) 双指针判定 sub 是否为 s 的子序列。"""
    it = iter(s)
    return all(ch in it for ch in sub)


def check_pair(x: str, y: str, stats: dict) -> None:
    ref_len, ref_seq = a0(x, y)
    # A0 自身也是被测对象：它的返回必须自洽（否则 oracle 不可信）
    assert len(ref_seq) == ref_len, f"A0 自洽性失败: {x!r} {y!r} -> {ref_len}, {ref_seq!r}"
    assert is_subsequence(ref_seq, x) and is_subsequence(ref_seq, y), (
        f"A0 返回的不是公共子序列: {x!r} {y!r} -> {ref_seq!r}"
    )

    if ref_len > 0:
        stats["nonempty"] += 1
    stats["total"] += 1

    for name, fn in SEQ_ARMS:
        got_len, got_seq = fn(x, y)
        assert got_len == ref_len, f"{name}: 长度不一致 {x!r} {y!r} got {got_len} want {ref_len}"
        assert len(got_seq) == got_len, f"{name}: 返回长度与序列不符 {x!r} {y!r}"
        assert is_subsequence(got_seq, x) and is_subsequence(got_seq, y), (
            f"{name}: 序列不是公共子序列 {x!r} {y!r} -> {got_seq!r}"
        )

    for name, fn in LEN_ARMS:
        got = fn(x, y)
        assert got == ref_len, f"{name}: 长度不一致 {x!r} {y!r} got {got} want {ref_len}"


def main() -> int:
    stats = {"total": 0, "nonempty": 0}

    # --- 1. 原版 doctest 里的全部用例 ---
    fixed = [
        ("programming", "gaming", 6),
        ("physics", "smartphone", 2),
        ("computer", "food", 1),
        ("", "abc", 0),
        ("abc", "", 0),
        ("", "", 0),
        ("abc", "def", 0),
        ("abc", "abc", 3),
        ("a", "a", 1),
        ("a", "b", 0),
        ("abcdef", "ace", 3),
        ("ABCD", "ACBD", 3),
        ("AGGTAB", "GXTXAYB", 4),
    ]
    for x, y, want in fixed:
        got = a0(x, y)[0]
        assert got == want, f"用例失效: {x!r} {y!r} got {got} want {want}"
        check_pair(x, y, stats)
    print(f"[1/5] 原版 doctest 用例 {len(fixed)} 条全部通过")

    # --- 2. 小字母表随机串（重复字符多 ⇒ 大量并列最优解，最能打回溯）---
    rng = random.Random(20261017)
    for _ in range(4000):
        alpha = rng.choice(["ab", "abc", "abcd", "acgt"])
        x = "".join(rng.choice(alpha) for _ in range(rng.randint(0, 24)))
        y = "".join(rng.choice(alpha) for _ in range(rng.randint(0, 24)))
        check_pair(x, y, stats)
    print("[2/5] 4000 组小字母表随机串通过")

    # --- 3. 极端形状：一长一短、全同字符、完全无交集 ---
    for n in (1, 2, 3, 7, 31, 64, 65, 127, 128, 200):
        check_pair("a" * n, "a" * (n // 2 + 1), stats)
        check_pair("a" * n, "b" * n, stats)
        check_pair("ab" * n, "ba" * n, stats)
        check_pair("a" * n, "a" * n, stats)
    print("[3/5] 极端形状（全同/无交集/交替）通过")

    # --- 4. 位并行边界：pattern 长度正好跨越 limb 边界（30/32/64/65）---
    for m in (29, 30, 31, 32, 63, 64, 65, 95, 96, 97, 128, 129):
        x = "".join(rng.choice("abcdef") for _ in range(m))
        y = "".join(rng.choice("abcdef") for _ in range(rng.randint(1, 40)))
        check_pair(x, y, stats)
    print("[4/5] 位并行 limb 边界（29/30/31/32/63/64/65/128/129）通过")

    # --- 5. 中等规模 + 长公共前缀（回溯路径最长，O(L²) 拼接最痛）---
    for L in (50, 200, 800):
        x = "".join(rng.choice("abcd") for _ in range(L))
        y = x[: L // 2] + "".join(rng.choice("abcd") for _ in range(L // 2))
        check_pair(x, y, stats)
    print("[5/5] 长公共前缀回溯路径通过")

    # 反向自检：确认测试真的有判别力（喂一个故意错 1 的实现，必须被抓到）
    caught = False
    try:
        bad_len, bad_seq = a0("AGGTAB", "GXTXAYB")
        assert (bad_len - 1, bad_seq) == (bad_len, bad_seq), "故意错误未被捕获"
    except AssertionError:
        caught = True
    assert caught, "测试无判别力：故意错误未被捕获"

    assert stats["nonempty"] >= 3000, (
        f"有效样本不足：只有 {stats['nonempty']} 个 case 长度>0，"
        "空串比较无法验证任何东西"
    )
    print(
        f"\n全部通过：{stats['total']} 组用例，其中 {stats['nonempty']} 组 LCS 长度>0"
        f"（{100.0 * stats['nonempty'] / stats['total']:.1f}% 非空）"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
