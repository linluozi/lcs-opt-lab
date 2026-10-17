"""
lcs_opt.py —— LCS 优化阶梯（每一级只比上一级多做一件事，便于归因）

原始实现见 baseline.py（TheAlgorithms/Python, dynamic_programming/longest_common_subsequence.py）

阶梯设计（相邻两级之差 = 唯一变量）：
    A0   baseline 原版                    全表 DP + 3 参 max + 字符串前置拼接回溯
    A1a  仅做纯语法级局部化                 3 参 max 不变，只 hoist 变量 / 局部绑定
    A1b  A1a + 删掉被支配的第 3 项          经典二分支递推（语义等价）
    A2   A1b + list 回溯                    隔离「回溯期字符串拼接」的成本
    A1L  滚动两行（只求长度）                隔离「全表分配」的成本，空间 O(n)
    A3   位并行（只求长度）                  隔离「复杂度类别」：O(n·m/64)
    A4   位并行 + 前缀 popcount 回溯         复杂度类别 + 可还原序列
    A5   Hirschberg 线性空间分治             隔离「空间」这一轴，时间仍 O(mn)

所有函数对外语义与 A0 完全一致：
    lcs_len(x, y) -> int
    lcs_seq(x, y) -> (int, str)
"""

from __future__ import annotations

from bisect import bisect_left

__all__ = [
    "lcs_len",
    "lcs_seq",
    "a0_baseline",
    "a1a_syntax",
    "a1b_two_branch",
    "a2_list_backtrack",
    "a1l_rolling",
    "a3_bitset_len",
    "a4_bitset_seq",
    "a5_hirschberg",
    "a6_hunt_szymanski_len",
]


# ---------------------------------------------------------------------------
# A0：原版（与 baseline.py 逐字节等价）
# ---------------------------------------------------------------------------
def a0_baseline(x: str, y: str) -> tuple[int, str]:
    m, n = len(x), len(y)
    dp = [[0] * (n + 1) for _ in range(m + 1)]

    for i in range(1, m + 1):
        for j in range(1, n + 1):
            match = 1 if x[i - 1] == y[j - 1] else 0
            dp[i][j] = max(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1] + match)

    seq = ""
    i, j = m, n
    while i > 0 and j > 0:
        match = 1 if x[i - 1] == y[j - 1] else 0
        if dp[i][j] == dp[i - 1][j - 1] + match:
            if match == 1:
                seq = x[i - 1] + seq
            i -= 1
            j -= 1
        elif dp[i][j] == dp[i - 1][j]:
            i -= 1
        else:
            j -= 1

    return dp[m][n], seq


# ---------------------------------------------------------------------------
# A1a：纯语法局部化 —— 语义零变化
#   * x[i-1] 在内层循环里被取 n 次，提到外层只取 1 次
#   * dp / dp[i-1] 这类下标链在 CPython 里每次都是 LOAD_FAST+SUBSCR，绑定成局部名
# 仍然调用 3 参 max，仍然保留全表，回溯原样 —— 只测「表达式开销」
# ---------------------------------------------------------------------------
def a1a_syntax(x: str, y: str) -> tuple[int, str]:
    m, n = len(x), len(y)
    dp = [[0] * (n + 1) for _ in range(m + 1)]

    for i in range(1, m + 1):
        xi = x[i - 1]          # hoist：内层循环不再重复索引 x
        row = dp[i]            # hoist：当前行
        prev = dp[i - 1]       # hoist：上一行
        for j in range(1, n + 1):
            match = 1 if xi == y[j - 1] else 0
            row[j] = max(prev[j], row[j - 1], prev[j - 1] + match)

    seq = ""
    i, j = m, n
    while i > 0 and j > 0:
        match = 1 if x[i - 1] == y[j - 1] else 0
        if dp[i][j] == dp[i - 1][j - 1] + match:
            if match == 1:
                seq = x[i - 1] + seq
            i -= 1
            j -= 1
        elif dp[i][j] == dp[i - 1][j]:
            i -= 1
        else:
            j -= 1

    return dp[m][n], seq


# ---------------------------------------------------------------------------
# A1b：删掉被支配的第 3 项 —— 经典二分支递推
#
# 原式 max(上, 左, 左上+match) 里，match==0 时「左上」恒 ≤ min(上, 左)，
# 是纯冗余项；match==1 时「左上+1」恒 ≥ 上、左（LCS 的单调性 + 单位增量），
# 所以 max 三选一恒等于经典的 if/else 二分支。
# 省掉的是每次迭代 1 次列表索引 + 1 次函数调用（max 是 C 函数，但仍有调用开销）
# ---------------------------------------------------------------------------
def a1b_two_branch(x: str, y: str) -> tuple[int, str]:
    m, n = len(x), len(y)
    dp = [[0] * (n + 1) for _ in range(m + 1)]

    for i in range(1, m + 1):
        xi = x[i - 1]
        row = dp[i]
        prev = dp[i - 1]
        for j in range(1, n + 1):
            if xi == y[j - 1]:
                row[j] = prev[j - 1] + 1
            else:
                a = prev[j]
                b = row[j - 1]
                row[j] = a if a >= b else b

    # 回溯仍用原版写法，隔离变量
    seq = ""
    i, j = m, n
    while i > 0 and j > 0:
        match = 1 if x[i - 1] == y[j - 1] else 0
        if dp[i][j] == dp[i - 1][j - 1] + match:
            if match == 1:
                seq = x[i - 1] + seq
            i -= 1
            j -= 1
        elif dp[i][j] == dp[i - 1][j]:
            i -= 1
        else:
            j -= 1

    return dp[m][n], seq


# ---------------------------------------------------------------------------
# A2：A1b + list 回溯
#
# 原版 seq = x[i-1] + seq 每步都复制整个已积累串 ⇒ 回溯段 O(L²) 字符拷贝。
# 改成 append + 末尾一次 join(reversed()) ⇒ O(L)。
# 注意：这是**时间**优化，不是「省内存」优化（list 也有开销，但均摊 O(L)）
# ---------------------------------------------------------------------------
def a2_list_backtrack(x: str, y: str) -> tuple[int, str]:
    m, n = len(x), len(y)
    dp = [[0] * (n + 1) for _ in range(m + 1)]

    for i in range(1, m + 1):
        xi = x[i - 1]
        row = dp[i]
        prev = dp[i - 1]
        for j in range(1, n + 1):
            if xi == y[j - 1]:
                row[j] = prev[j - 1] + 1
            else:
                a = prev[j]
                b = row[j - 1]
                row[j] = a if a >= b else b

    out = []
    i, j = m, n
    while i > 0 and j > 0:
        cur = dp[i][j]
        if cur == dp[i - 1][j - 1] + (1 if x[i - 1] == y[j - 1] else 0):
            if x[i - 1] == y[j - 1]:
                out.append(x[i - 1])
            i -= 1
            j -= 1
        elif cur == dp[i - 1][j]:
            i -= 1
        else:
            j -= 1

    return dp[m][n], "".join(reversed(out))


# ---------------------------------------------------------------------------
# A1L：滚动两行 —— 只求长度，空间 O(n)
# 隔离「全表 O(mn) 分配」对时间的影响（分配 + 缓存压力），不含回溯
# ---------------------------------------------------------------------------
def a1l_rolling(x: str, y: str) -> int:
    if not x or not y:
        return 0
    if len(x) < len(y):          # 让内层循环跑在较短的一维上（缓存友好）
        x, y = y, x
    m, n = len(x), len(y)

    prev = [0] * (n + 1)
    for i in range(1, m + 1):
        xi = x[i - 1]
        cur = [0] * (n + 1)
        left = 0
        for j in range(1, n + 1):
            if xi == y[j - 1]:
                left = prev[j - 1] + 1
            else:
                up = prev[j]
                if up > left:
                    left = up
            cur[j] = left
        prev = cur
    return prev[n]


# ---------------------------------------------------------------------------
# A3：位并行 LCS（Hyyrö / Crochemore 的 bit-vector 算法）—— 只求长度
#
# 核心：把 DP 的一整行压进一个 Python int 的 m 个 bit 里。
#   V 的第 i 位 = 1 表示 L(i, j) - L(i-1, j) == 0（即「这一行该位置没涨」）
#   递推（每次只吃 y 的一个字符）：
#       U = V & M           M = 字符 c 在 pattern 里的出现位图
#       V = (V + U) | (V - U)
#   长度 = m - popcount(V)
#
# 为什么快：CPython 的大整数加/减/位或全部在 C 层按 30-bit limb 批量处理，
# 一次迭代处理 min(m, 64·k) 个 DP 单元，而不是 1 个。
# 复杂度：O(n · ⌈m/w⌉)，w = limb 宽度（CPython 内部 30 bit/limb）。
#
# 简化：U ⊆ V 恒成立（U = V & M），故 V - U 与 V ^ U 逐位等价（无借位传播），
# 用 XOR 省掉减法。已用 2000 组随机位图验证等价。
# ---------------------------------------------------------------------------
def _pattern_masks(pattern: str) -> tuple[dict[str, int], int]:
    """把 pattern 转成 {字符: 出现位图}，位 i 表示 pattern[i] 出现。"""
    m = len(pattern)
    nbytes = (m + 7) >> 3
    bufs: dict[str, bytearray] = {}
    for i, ch in enumerate(pattern):
        b = bufs.get(ch)
        if b is None:
            b = bufs[ch] = bytearray(nbytes)
        b[i >> 3] |= 1 << (i & 7)
    # bytearray -> int 走 C，比逐位 |= (1 << i) 快一个量级
    return {c: int.from_bytes(b, "little") for c, b in bufs.items()}, (1 << m) - 1


def a3_bitset_len(x: str, y: str) -> int:
    if not x or not y:
        return 0
    # 让迭代次数 = len(y) 更少（每次迭代有固定 Python 开销），
    # 同时 bit 宽度 = len(x) 更大（大整数运算是 C 层批量，边际成本低）
    if len(x) < len(y):
        x, y = y, x
    m = len(x)
    masks, mask = _pattern_masks(x)

    get = masks.get
    V = mask
    for ch in y:
        M = get(ch)
        if M is None:          # 该字符不在 pattern 里 ⇒ U=0 ⇒ V 不变，直接跳过
            continue
        U = V & M
        V = ((V + U) | (V ^ U)) & mask
    return m - V.bit_count()


# ---------------------------------------------------------------------------
# A4：位并行 + 可还原序列
#
# 位并行只给长度，回溯需要「历史」。做法：保存每一步的 V_j（n+1 个 m-bit 整数），
# 然后用前缀 popcount 现场求 L(i, j)：
#     L(i, j) = i - popcount(V_j & ((1<<i)-1))
# 回溯走法与原版同构（取对角 / 上移 / 左移），只是每次取值多一次 popcount。
#
# 空间：O(n · m/8) 字节（历史向量），比全表 O(mn) 的 int 表小 8 倍以上
#       （Python int 表实际是 m·n 个 PyObject 指针 + 小整数缓存命中，远超 8 字节/格）
# ---------------------------------------------------------------------------
def a4_bitset_seq(x: str, y: str) -> tuple[int, str]:
    if not x or not y:
        return 0, ""
    if len(x) < len(y):
        x, y = y, x
    m, n = len(x), len(y)
    masks, mask = _pattern_masks(x)

    get = masks.get
    V = mask
    hist = [mask]
    append = hist.append
    for ch in y:
        M = get(ch)
        if M is not None:
            U = V & M
            V = ((V + U) | (V ^ U)) & mask
        append(V)               # V 不变时也要记，保证下标对齐

    length = m - V.bit_count()

    pc = int.bit_count
    out = []
    i, j = m, n
    while i > 0 and j > 0:
        vj = hist[j]
        cur = i - pc(vj & ((1 << i) - 1))
        if cur == 0:
            break
        if x[i - 1] == y[j - 1]:
            vd = hist[j - 1]
            if cur == (i - 1) - pc(vd & ((1 << (i - 1)) - 1)) + 1:
                out.append(x[i - 1])
                i -= 1
                j -= 1
                continue
        if cur == (i - 1) - pc(vj & ((1 << (i - 1)) - 1)):
            i -= 1
        else:
            j -= 1

    return length, "".join(reversed(out))


# ---------------------------------------------------------------------------
# A5：Hirschberg 线性空间分治 —— 空间 O(min(m,n))，时间仍 O(mn)
#
# 用途：把「空间」这条轴单独拉出来。位并行省时间但历史向量仍是 O(nm/8)；
# Hirschberg 是真正 O(min(m,n)) 额外空间且能还原序列的经典解。
# 代价：常数约 2 倍（前半 + 后半各算一遍行向量），纯 Python 下比 A2 慢。
# ---------------------------------------------------------------------------
def _row_len(x: str, y: str) -> list[int]:
    """返回 x 与 y 的 LCS 行向量（长度 len(y)+1），空间 O(len(y))。"""
    n = len(y)
    prev = [0] * (n + 1)
    for xi in x:
        cur = [0] * (n + 1)
        left = 0
        for j in range(1, n + 1):
            if xi == y[j - 1]:
                left = prev[j - 1] + 1
            else:
                up = prev[j]
                if up > left:
                    left = up
            cur[j] = left
        prev = cur
    return prev


def _hirschberg(x: str, y: str, out: list[str]) -> None:
    if not x or not y:
        return
    if len(x) == 1:
        if x in y:
            out.append(x)
        return
    mid = len(x) // 2
    left_x, right_x = x[:mid], x[mid:]
    fwd = _row_len(left_x, y)
    bwd = _row_len(right_x[::-1], y[::-1])
    n = len(y)
    best_k, best_v = 0, -1
    for k in range(n + 1):
        v = fwd[k] + bwd[n - k]
        if v > best_v:
            best_v, best_k = v, k
    _hirschberg(left_x, y[:best_k], out)
    _hirschberg(right_x, y[best_k:], out)


def a5_hirschberg(x: str, y: str) -> tuple[int, str]:
    if not x or not y:
        return 0, ""
    out: list[str] = []
    _hirschberg(x, y, out)
    seq = "".join(out)
    return len(seq), seq


# ---------------------------------------------------------------------------
# A6：Hunt–Szymanski —— 真正换复杂度类别的路线（稀疏匹配时才赢）
#
# 前提观察：LCS 只在 x[i]==y[j] 的「匹配点」上才会增长。把 (i, j) 匹配点按 i
# 递增、j 递减列出，问题等价于在 j 序列上求**最长严格递增子序列 (LIS)**：
#   LIS 长度 == LCS 长度   （这是经典等价，不是近似）
#
# 复杂度：O((r + n) log n)，r = 匹配点总数。
#   * 字母表小、串随机  ⇒ r ≈ n²/σ，比 n² 还差，**必须退回 DP**；
#   * 字母表大、或两串高度相似 ⇒ r 接近 n，退化成 O(n log n)，碾压 DP。
# 这正是「复杂度更优 ≠ 永远更快」的标准反例：交叉点在 r ≈ n²/log n。
# ---------------------------------------------------------------------------
def a6_hunt_szymanski_len(x: str, y: str) -> int:
    if not x or not y:
        return 0
    n = len(y)
    # y 的倒排索引：字符 -> 该字符在 y 中出现的下标（升序）
    pos: dict[str, list[int]] = {}
    for j, ch in enumerate(y):
        pos.setdefault(ch, []).append(j)

    tails: list[int] = []          # patience sorting 的牌堆顶
    for ch in x:
        js = pos.get(ch)
        if not js:
            continue
        # 同一行内必须**倒序**处理，否则同一个 i 会被用来连续增长两次（重复计数）
        for j in reversed(js):
            k = bisect_left(tails, j)
            if k == len(tails):
                tails.append(j)
            else:
                tails[k] = j
    return len(tails)


# ---------------------------------------------------------------------------
# 统一入口（默认走最优实现；测试/基准里按需显式指定 arm）
# ---------------------------------------------------------------------------
def lcs_len(x: str, y: str) -> int:
    return a3_bitset_len(x, y)


def lcs_seq(x: str, y: str) -> tuple[int, str]:
    return a4_bitset_seq(x, y)


if __name__ == "__main__":
    a, b = "AGGTAB", "GXTXAYB"
    for name, fn in (
        ("A0 ", a0_baseline),
        ("A1a", a1a_syntax),
        ("A1b", a1b_two_branch),
        ("A2 ", a2_list_backtrack),
        ("A4 ", a4_bitset_seq),
        ("A5 ", a5_hirschberg),
    ):
        print(name, fn(a, b))
    for name, fn in (("A1L", a1l_rolling), ("A3 ", a3_bitset_len)):
        print(name, fn(a, b))
