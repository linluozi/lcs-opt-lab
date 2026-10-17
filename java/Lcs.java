/*
 * Lcs.java —— Java 实现（两条路线）
 *
 *   mode=dp     经典两行滚动 DP（int[] 预分配，避免装箱）
 *   mode=bitset 位并行 LCS（long[] 手写进位/借位）
 *
 * 用法：
 *   java Lcs dp     1000 12345 4 5
 *   java Lcs bitset 100000 12345 4 5
 *
 * 输出：
 *   RESULT mode=<m> n=<n> alpha=<a> len=<L> best_ms=<t> reps=<r>
 *
 * 编译运行：
 *   javac Lcs.java && java Lcs bitset 100000 12345 4 5
 *
 * 生成器与 C / Python 版逐位一致（同一 LCG 常量），三语言吃同一份输入。
 */
public final class Lcs {
    private static final char[] ALPHA = {'A', 'C', 'G', 'T'};

    /** 与 Python / C 完全一致的 LCG（Knuth MMIX 常量）。 */
    private static long next(long s) {
        return s * 6364136223846793005L + 1442695040888963407L;
    }

    private static char[] gen(int n, long seed, int alpha) {
        char[] out = new char[n];
        long s = seed;
        for (int i = 0; i < n; i++) {
            s = next(s);
            // Java 的 >>> 是无符号右移，对应 C 的 (uint64_t)>>33
            out[i] = ALPHA[(int) ((s >>> 33) % alpha)];
        }
        return out;
    }

    // ---------------- DP：两行滚动 ----------------
    private static int lcsDp(char[] x, char[] y) {
        int m = x.length, n = y.length;
        if (m == 0 || n == 0) return 0;
        // 内层循环跑在较短的一维上，减少缓存行跨越
        if (m < n) { char[] t = x; x = y; y = t; int u = m; m = n; n = u; }
        int[] prev = new int[n + 1];
        int[] cur = new int[n + 1];
        for (int i = 0; i < m; i++) {
            final char xi = x[i];
            int left = 0;
            for (int j = 0; j < n; j++) {
                if (xi == y[j]) {
                    left = prev[j] + 1;
                } else {
                    int up = prev[j + 1];
                    if (up > left) left = up;
                }
                cur[j + 1] = left;
            }
            int[] t = prev; prev = cur; cur = t;
        }
        return prev[n];
    }

    /**
     * 无符号比较：a < b 返回 1，否则 0。
     *
     * Java 的 long 是**有符号**的，直接写 `a < v` 在最高位为 1（即 v 为负）时结论完全相反。
     * 位并行算法把 64 个 DP 单元塞进一个 long，最高位为 1 是常态 ⇒ 必须无符号比较。
     * 这里用异或 MIN_VALUE 把有符号序映射成无符号序（比 Long.compareUnsigned 少一层调用）。
     */
    private static long ult(long a, long b) {
        return ((a ^ Long.MIN_VALUE) < (b ^ Long.MIN_VALUE)) ? 1L : 0L;
    }

    // ---------------- 位并行 ----------------
    private static int lcsBitset(char[] x, char[] y, int alpha) {
        int m = x.length, n = y.length;
        if (m == 0 || n == 0) return 0;
        final int W = (m + 63) >>> 6;

        long[] masks = new long[alpha * W];   // 预分配，零初始化
        for (int i = 0; i < m; i++) {
            int c = idx(x[i]);
            masks[c * W + (i >>> 6)] |= 1L << (i & 63);
        }

        long[] V = new long[W];
        java.util.Arrays.fill(V, ~0L);
        final long lastMask = (m & 63) != 0 ? (1L << (m & 63)) - 1 : ~0L;
        V[W - 1] = lastMask;

        for (int j = 0; j < n; j++) {
            int c = idx(y[j]);
            int base = c * W;
            long carry = 0, borrow = 0;
            for (int w = 0; w < W; w++) {
                long v = V[w];
                long u = v & masks[base + w];

                long a = v + u;
                long c1 = ult(a, v);                 // 无符号溢出 = 进位
                long a2 = a + carry;
                long c2 = ult(a2, a);

                long b = v - u;
                long b1 = ult(v, u);                 // 无符号下溢 = 借位
                long b2 = ult(b, borrow);

                V[w] = a2 | (b - borrow);
                carry = c1 | c2;
                borrow = b1 | b2;
            }
            // 清掉最高字第 m 位以上的脏位（否则下一轮 popcount 会多减，长度偏小）
            V[W - 1] &= lastMask;
        }

        int len = m;
        for (int w = 0; w < W; w++) len -= Long.bitCount(V[w]);
        return len;
    }

    private static double nowMs() {
        return System.nanoTime() / 1e6;
    }

    /** 'A'->0 'C'->1 'G'->2 'T'->3；不能用 x[i]-'A'，字母在 ASCII 里不连续。 */
    private static int idx(char c) {
        switch (c) {
            case 'A': return 0;
            case 'C': return 1;
            case 'G': return 2;
            default:  return 3;
        }
    }

    /**
     * 从 stdin 读两行，用 DP 与位并行各算一遍并交叉校验。
     * Java 的 char 是 UTF-16 码元，中文字符（BMP 内）能正确表示，
     * 所以这里不像 C 版那样限制 ASCII。
     */
    private static int runStdin() throws java.io.IOException {
        java.io.BufferedReader br =
            new java.io.BufferedReader(new java.io.InputStreamReader(System.in, "UTF-8"));
        String a = br.readLine();
        String b = br.readLine();
        if (a == null) a = "";
        if (b == null) b = "";

        char[] x = a.toCharArray();
        char[] y = b.toCharArray();

        // 用 TreeSet 建紧凑字符编号，避免 256 表溢出
        java.util.TreeSet<Character> set = new java.util.TreeSet<>();
        for (char c : x) set.add(c);
        for (char c : y) set.add(c);
        int sigma = set.size();
        java.util.HashMap<Character, Integer> ids = new java.util.HashMap<>();
        int next = 0;
        for (char c : set) ids.put(c, next++);

        int d = lcsDp(x, y);
        int bitset = lcsBitsetIds(x, y, ids, sigma);
        System.out.printf("RESULT mode=stdin len=%d bitset=%d sigma=%d agree=%d%n",
                          d, bitset, sigma, d == bitset ? 1 : 0);
        return d == bitset ? 0 : 1;
    }

    /** 同 lcsBitset，但字符编号来自外部 map（支持任意字符集）。 */
    private static int lcsBitsetIds(char[] x, char[] y,
                                    java.util.HashMap<Character, Integer> ids, int sigma) {
        int m = x.length, n = y.length;
        if (m == 0 || n == 0) return 0;
        final int W = (m + 63) >>> 6;
        long[] masks = new long[Math.max(sigma, 1) * W];
        for (int i = 0; i < m; i++) {
            int c = ids.get(x[i]);
            masks[c * W + (i >>> 6)] |= 1L << (i & 63);
        }
        long[] V = new long[W];
        java.util.Arrays.fill(V, ~0L);
        final long lastMask = (m & 63) != 0 ? (1L << (m & 63)) - 1 : ~0L;
        V[W - 1] = lastMask;
        for (int j = 0; j < n; j++) {
            int c = ids.get(y[j]);
            int base = c * W;
            long carry = 0, borrow = 0;
            for (int w = 0; w < W; w++) {
                long v = V[w];
                long u = v & masks[base + w];
                long a = v + u;
                long c1 = ult(a, v);
                long a2 = a + carry;
                long c2 = ult(a2, a);
                long b = v - u;
                long b1 = ult(v, u);
                long b2 = ult(b, borrow);
                V[w] = a2 | (b - borrow);
                carry = c1 | c2;
                borrow = b1 | b2;
            }
            V[W - 1] &= lastMask;
        }
        int len = m;
        for (int w = 0; w < W; w++) len -= Long.bitCount(V[w]);
        return len;
    }

    public static void main(String[] args) throws java.io.IOException {
        if (args.length >= 2 && args[1].equals("stdin")) {
            System.exit(runStdin());
        }
        if (args.length < 5) {
            System.err.println("usage: java Lcs dp|bitset <n> <seed> <alpha> <reps>");
            System.err.println("       printf 'abc\\ndef' | java Lcs dp stdin");
            System.exit(2);
        }
        boolean bitset = args[0].equals("bitset");
        int n = Integer.parseInt(args[1]);
        long seed = Long.parseLong(args[2]);
        int alpha = Integer.parseInt(args[3]);
        int reps = Integer.parseInt(args[4]);

        char[] x = gen(n, seed, alpha);
        char[] y = gen(n, seed ^ 0x9E3779B97F4A7C15L, alpha);

        int len = 0;
        double best = Double.MAX_VALUE;
        for (int r = 0; r < reps; r++) {
            long t0 = System.nanoTime();
            len = bitset ? lcsBitset(x, y, alpha) : lcsDp(x, y);
            double dt = (System.nanoTime() - t0) / 1e6;
            if (dt < best) best = dt;
        }

        System.out.printf(
            "RESULT mode=%s n=%d alpha=%d len=%d best_ms=%.4f reps=%d%n",
            bitset ? "bitset" : "dp", n, alpha, len, best, reps);
    }
}
