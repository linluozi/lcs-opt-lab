/*
 * lcs_c.c —— C 实现（两条路线）
 *
 *   mode=dp     经典两行滚动 DP，O(n·m) 时间 / O(min) 空间
 *   mode=bitset Hyyrö 位并行 LCS，O(n·⌈m/64⌉) 时间 / O(⌈m/64⌉·σ) 空间
 *
 * 用法：
 *   lcs_c dp     1000 12345 4 5      # mode n seed alphabet reps
 *   lcs_c bitset 100000 12345 4 5
 *   echo -e "AGGTAB\nGXTXAYB" | lcs_c dp stdin    # 从标准输入读两行任意串
 *
 * 输出（机器可读，便于 bench.py 解析）：
 *   RESULT mode=<m> n=<n> len=<L> best_ms=<t> reps=<r>
 *   RESULT mode=stdin len=<L>
 *
 * 编译（MSVC）：
 *   cl -nologo -O2 -Fe:lcs_c.exe lcs_c.c
 * 编译（gcc/clang）：
 *   cc -O2 -march=native -o lcs_c lcs_c.c
 *
 * 字符集固定为 "ACGT" 的前 alphabet 个字符，生成器与 Python / Java 版逐位一致
 * （同一个 LCG 常量），因此三种语言吃的是同一份输入。
 */
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>

#ifdef _WIN32
#include <windows.h>
static double now_ms(void) {
    static LARGE_INTEGER freq;
    static int init = 0;
    LARGE_INTEGER c;
    if (!init) { QueryPerformanceFrequency(&freq); init = 1; }
    QueryPerformanceCounter(&c);
    return (double)c.QuadPart * 1000.0 / (double)freq.QuadPart;
}
#else
#include <time.h>
static double now_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec * 1000.0 + ts.tv_nsec / 1e6;
}
#endif

static const char ALPHA[] = "ACGT";

/* 任意字符 -> 0..255 的映射表（stdin 模式下字符集不限于 ACGT） */
static unsigned char CHAR_ID[256];

static void init_char_id(void) {
    for (int i = 0; i < 256; i++) CHAR_ID[i] = (unsigned char)i;
}

/* 与 Python / Java 完全一致的 LCG（Knuth MMIX 常量） */
static uint64_t lcg_next(uint64_t *s) {
    *s = *s * 6364136223846793005ULL + 1442695040888963407ULL;
    return *s;
}

static void gen_string(char *buf, int n, uint64_t seed, int alpha) {
    uint64_t s = seed;
    for (int i = 0; i < n; i++) {
        buf[i] = ALPHA[(lcg_next(&s) >> 33) % (uint64_t)alpha];
    }
    buf[n] = '\0';
}

/* ---------------- DP：两行滚动 ---------------- */
static int lcs_dp(const char *x, int m, const char *y, int n) {
    if (m == 0 || n == 0) return 0;
    uint32_t *prev = (uint32_t *)calloc((size_t)n + 1, sizeof(uint32_t));
    uint32_t *cur  = (uint32_t *)calloc((size_t)n + 1, sizeof(uint32_t));
    if (!prev || !cur) { fprintf(stderr, "oom\n"); exit(1); }
    for (int i = 1; i <= m; i++) {
        const char xi = x[i - 1];
        uint32_t left = 0;
        for (int j = 1; j <= n; j++) {
            if (xi == y[j - 1]) {
                left = prev[j - 1] + 1;
            } else {
                uint32_t up = prev[j];
                if (up > left) left = up;
            }
            cur[j] = left;
        }
        uint32_t *t = prev; prev = cur; cur = t;
    }
    int r = (int)prev[n];
    free(prev); free(cur);
    return r;
}

/* ---------------- 位并行 ---------------- */
/*
 * ids[256] 把字符映射到 0..sigma-1 的紧凑编号（sigma = 实际出现过的字符数）。
 * 用紧凑编号而不是直接拿 ASCII 当索引，是为了让位图数组大小 = sigma*W 而不是 256*W。
 */
static int lcs_bitset(const char *x, int m, const char *y, int n,
                      const unsigned char *ids, int sigma) {
    if (m == 0 || n == 0) return 0;
    const int W = (m + 63) >> 6;

    uint64_t *masks = (uint64_t *)calloc((size_t)sigma * W, sizeof(uint64_t));
    uint64_t *V     = (uint64_t *)malloc((size_t)W * sizeof(uint64_t));
    if (!masks || !V) { fprintf(stderr, "oom\n"); exit(1); }

    /* 建位图：masks[c*W + w] 的第 b 位 = pattern 中下标 (w*64+b) 是否为字符 c */
    for (int i = 0; i < m; i++) {
        int c = ids[(unsigned char)x[i]];
        masks[(size_t)c * W + (i >> 6)] |= 1ULL << (i & 63);
    }

    /* V 初值全 1（前 m 位）。last_mask 用于每轮清掉第 m 位以上的脏位，
       否则这些位会在 V+U 时向上进位、并被 popcount 计入，结果偏小。 */
    const uint64_t last_mask = (m & 63) ? ((1ULL << (m & 63)) - 1) : ~0ULL;
    for (int w = 0; w < W; w++) V[w] = ~0ULL;
    V[W - 1] = last_mask;

    for (int j = 0; j < n; j++) {
        int c = ids[(unsigned char)y[j]];
        const uint64_t *M = masks + (size_t)c * W;
        uint64_t carry = 0, borrow = 0;
        for (int w = 0; w < W; w++) {
            const uint64_t u = V[w] & M[w];
            /* V + U，跨字进位 */
            uint64_t a = V[w] + u;
            uint64_t c1 = (a < V[w]);
            uint64_t a2 = a + carry;
            uint64_t c2 = (a2 < a);
            /* V - U，跨字借位 */
            uint64_t b = V[w] - u;
            uint64_t b1 = (V[w] < u);
            uint64_t b2 = (b < borrow);
            V[w] = a2 | (b - borrow);
            carry = c1 | c2;
            borrow = b1 | b2;
        }
        /* 关键：清掉最高字里第 m 位以上的溢出位。
           位并行公式要求 V 始终是 m 位向量；V+U 会把 bit m 及更上面填成 1，
           这些脏位下一轮会被 popcount 计入 ⇒ 长度偏小（实测 1308 被算成 1260）。 */
        V[W - 1] &= last_mask;
    }

    int len = m;
    for (int w = 0; w < W; w++) {
#ifdef _MSC_VER
        len -= (int)__popcnt64(V[w]);
#else
        len -= __builtin_popcountll(V[w]);
#endif
    }
    free(masks); free(V);
    return len;
}

/* 给 x/y 里出现过的字符分配紧凑编号，返回 sigma（不同字符数）。 */
static int build_ids(const char *x, int m, const char *y, int n, unsigned char *ids) {
    int seen[256] = {0};
    int sigma = 0;
    for (int i = 0; i < m; i++) {
        unsigned char c = (unsigned char)x[i];
        if (!seen[c]) { seen[c] = 1; ids[c] = (unsigned char)sigma++; }
    }
    for (int j = 0; j < n; j++) {
        unsigned char c = (unsigned char)y[j];
        if (!seen[c]) { seen[c] = 1; ids[c] = (unsigned char)sigma++; }
    }
    return sigma;
}

/* 读一整行（去掉行尾 CR/LF），返回长度。用 fgets 而非 getline：后者是 POSIX 扩展，
   MSVC 的 UCRT 不提供，会导致 Windows 上编译失败。 */
static int read_line(char *buf, int cap) {
    if (!fgets(buf, cap, stdin)) { buf[0] = '\0'; return 0; }
    int len = (int)strlen(buf);
    while (len > 0 && (buf[len - 1] == '\n' || buf[len - 1] == '\r')) buf[--len] = '\0';
    return len;
}

/* stdin mode: read two lines, run both algorithms and cross-check.
 *
 * NOTE: this implementation compares **bytes** (char array). A UTF-8 Chinese
 * character occupies 3 bytes, so "中" may share a byte with "文" -- the result
 * would disagree with Python's per-codepoint comparison. That is a deliberate
 * limitation: the bit-parallel bitmap is one bit per *character*, and
 * multi-byte encodings need decoding into an int32 codepoint array first.
 * We reject non-ASCII input instead of returning a plausible-but-wrong number.
 *
 * Messages here are kept in ASCII on purpose: MSVC reads .c files using the
 * system codepage (936 on Chinese Windows), and a UTF-8 string literal can
 * swallow its closing quote when a multi-byte sequence ends in 0x5C. */
static int run_stdin(void) {
    enum { MAXLEN = 1 << 20 };
    char *line[2];
    line[0] = (char *)malloc(MAXLEN);
    line[1] = (char *)malloc(MAXLEN);
    if (!line[0] || !line[1]) { fprintf(stderr, "oom\n"); return 1; }
    int m = read_line(line[0], MAXLEN);
    int n = read_line(line[1], MAXLEN);

    /* reject non-ASCII: high bytes mean multi-byte encoding, byte-wise compare is meaningless */
    for (int k = 0; k < 2; k++) {
        int len = (k == 0) ? m : n;
        for (int i = 0; i < len; i++) {
            if ((unsigned char)line[k][i] >= 0x80) {
                fprintf(stderr, "ERROR: non-ASCII byte in input (UTF-8 multi-byte). "
                                "This C build compares bytes; use ASCII or the Python/Java build.\n");
                free(line[0]); free(line[1]);
                return 3;
            }
        }
    }

    unsigned char ids[256];
    init_char_id();
    int sigma = build_ids(line[0], m, line[1], n, ids);
    int a = lcs_dp(line[0], m, line[1], n);
    int b = lcs_bitset(line[0], m, line[1], n, ids, sigma);
    printf("RESULT mode=stdin len=%d bitset=%d sigma=%d agree=%d\n", a, b, sigma, a == b);
    free(line[0]); free(line[1]);
    return a == b ? 0 : 1;
}

int main(int argc, char **argv) {
    if (argc >= 3 && strcmp(argv[2], "stdin") == 0) return run_stdin();
    if (argc < 6) {
        fprintf(stderr, "usage: %s dp|bitset <n> <seed> <alpha> <reps>\n", argv[0]);
        fprintf(stderr, "       echo -e \"abc\\ndef\" | %s dp stdin\n", argv[0]);
        return 2;
    }
    const int is_bitset = strcmp(argv[1], "bitset") == 0;
    const int n = atoi(argv[2]);
    const uint64_t seed = strtoull(argv[3], NULL, 10);
    const int alpha = atoi(argv[4]);
    const int reps = atoi(argv[5]);
    if (n < 0 || alpha < 1 || alpha > 4 || reps < 1) { fprintf(stderr, "bad args\n"); return 2; }

    char *x = (char *)malloc((size_t)n + 1);
    char *y = (char *)malloc((size_t)n + 1);
    if (!x || !y) { fprintf(stderr, "oom\n"); return 1; }
    gen_string(x, n, seed, alpha);
    gen_string(y, n, seed ^ 0x9E3779B97F4A7C15ULL, alpha);   /* 同种子派生，长度相同 */

    unsigned char ids[256];
    init_char_id();
    int sigma = build_ids(x, n, y, n, ids);

    int len = 0;
    double best = 1e18;
    for (int r = 0; r < reps; r++) {
        double t0 = now_ms();
        len = is_bitset ? lcs_bitset(x, n, y, n, ids, sigma) : lcs_dp(x, n, y, n);
        double dt = now_ms() - t0;
        if (dt < best) best = dt;
    }

    printf("RESULT mode=%s n=%d alpha=%d len=%d best_ms=%.4f reps=%d\n",
           is_bitset ? "bitset" : "dp", n, alpha, len, best, reps);
    free(x); free(y);
    return 0;
}
