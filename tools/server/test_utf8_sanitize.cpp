// Unit tests for sanitize_utf8_stream — validates SSE UTF-8 fix
// Compile: g++ -std=c++17 -Wall -o /tmp/test_utf8_sanitize tools/server/test_utf8_sanitize.cpp && /tmp/test_utf8_sanitize
#include <string>
#include <cstdio>
#include <cstdlib>
#include <cstring>

// Copy of sanitize_utf8_stream from server-omni.cpp (must stay in sync)
static inline bool utf8_cont(unsigned char c) { return (c & 0xC0) == 0x80; }

static std::string sanitize_utf8_stream(std::string & pending,
                                        const std::string & fragment,
                                        bool flush = false) {
    static const std::string replacement = "\xEF\xBF\xBD";
    std::string input = pending + fragment;
    pending.clear();

    std::string out;
    size_t i = 0;
    while (i < input.size()) {
        const unsigned char c = static_cast<unsigned char>(input[i]);
        if (c < 0x80) {
            out.push_back(static_cast<char>(c));
            i++;
            continue;
        }

        int need = 0;
        if (c >= 0xC2 && c <= 0xDF) {
            need = 1;
        } else if (c >= 0xE0 && c <= 0xEF) {
            need = 2;
        } else if (c >= 0xF0 && c <= 0xF4) {
            need = 3;
        } else {
            out += replacement;
            i++;
            continue;
        }

        if (i + need >= input.size()) {
            pending = input.substr(i);
            break;
        }

        bool ok = true;
        for (int j = 1; j <= need; ++j) {
            ok = ok && utf8_cont(static_cast<unsigned char>(input[i + j]));
        }
        if (ok && c == 0xE0) {
            ok = static_cast<unsigned char>(input[i + 1]) >= 0xA0;
        } else if (ok && c == 0xED) {
            ok = static_cast<unsigned char>(input[i + 1]) < 0xA0;
        } else if (ok && c == 0xF0) {
            ok = static_cast<unsigned char>(input[i + 1]) >= 0x90;
        } else if (ok && c == 0xF4) {
            ok = static_cast<unsigned char>(input[i + 1]) < 0x90;
        }

        if (!ok) {
            out += replacement;
            i++;
            continue;
        }

        out.append(input, i, need + 1);
        i += need + 1;
    }

    if (flush && !pending.empty()) {
        out += replacement;
        pending.clear();
    }
    return out;
}

static int tests = 0, passed = 0, failed = 0;

#define TEST(name) do { tests++; printf("TEST %d: %s ... ", tests, name); } while(0)
#define PASS() do { passed++; printf("PASS\n"); } while(0)
#define FAIL(msg) do { failed++; printf("FAIL: %s\n", msg); } while(0)
#define ASSERT_EQ(a, b) do { if ((a) != (b)) { FAIL("assertion failed"); return; } } while(0)
#define ASSERT_STREQ(a, b) do { if (std::string(a) != std::string(b)) { \
    fprintf(stderr, "  expected: "); for(auto c:std::string(b)) fprintf(stderr,"%02x",(unsigned char)c); \
    fprintf(stderr, "\n  got:      "); for(auto c:std::string(a)) fprintf(stderr,"%02x",(unsigned char)c); \
    fprintf(stderr,"\n"); FAIL("string mismatch"); return; } } while(0)

// ── Test 1: SSE_ASCII_TEST — ASCII fragments pass through unchanged ──
void test_ascii_pass_through() {
    TEST("SSE_ASCII_TEST");
    std::string pending;
    std::string out = sanitize_utf8_stream(pending, "Hello, World!", false);
    ASSERT_STREQ(out, "Hello, World!");
    ASSERT_EQ(pending.size(), (size_t)0);
    PASS();
}

// ── Test 2: SSE_CHINESE_TEST — Chinese multi-byte characters correct ──
void test_chinese_pass_through() {
    TEST("SSE_CHINESE_TEST");
    std::string pending;
    std::string chinese = "\xe4\xbd\xa0\xe5\xa5\xbd\xef\xbc\x81"; // "你好！"
    std::string out = sanitize_utf8_stream(pending, chinese, false);
    ASSERT_STREQ(out, chinese);
    ASSERT_EQ(pending.size(), (size_t)0);
    PASS();
}

// ── Test 3: SSE_SPLIT_UTF8_TEST — Chinese byte split across fragments ──
void test_split_utf8_fragment() {
    TEST("SSE_SPLIT_UTF8_TEST");

    // "你" = E4 BD A0. Split after E4 BD.
    std::string pending;
    std::string frag1 = "\xe4\xbd";       // incomplete — lead byte E4 expects 2 continuation bytes, got 1
    std::string frag2 = "\xa0";            // completion byte

    std::string out1 = sanitize_utf8_stream(pending, frag1, false);
    // frag1 = E4 BD: lead byte E4 expects 2 continuation bytes (need=2).
    // i=0: c=E4, need=2. i+need=2 >= input.size()=2 → pending = input.substr(0) = E4 BD, break.
    // out1 should be empty
    ASSERT_STREQ(out1, "");
    ASSERT_STREQ(pending, "\xe4\xbd");

    std::string out2 = sanitize_utf8_stream(pending, frag2, false);
    // pending + frag2 = E4 BD A0 → complete "你"
    ASSERT_STREQ(out2, "\xe4\xbd\xa0");
    ASSERT_STREQ(pending, "");

    PASS();
}

// ── Test 3b: SSE_SPLIT_UTF8_ACROSS_THREE — 3-byte char split 1+2 ──
void test_split_utf8_three_bytes() {
    TEST("SSE_SPLIT_UTF8_3BYTE_1_2");

    // "好" = E5 A5 BD. Split as E5 | A5 BD
    std::string pending;
    std::string frag1 = "\xe5";           // lead byte alone
    std::string frag2 = "\xa5\xbd";       // 2 continuation bytes

    std::string out1 = sanitize_utf8_stream(pending, frag1, false);
    ASSERT_STREQ(out1, "");
    ASSERT_EQ(pending.size(), (size_t)1);
    ASSERT_EQ((unsigned char)pending[0], 0xE5);

    std::string out2 = sanitize_utf8_stream(pending, frag2, false);
    ASSERT_STREQ(out2, "\xe5\xa5\xbd");
    ASSERT_STREQ(pending, "");

    PASS();
}

// ── Test 4: SSE_INVALID_UTF8_TEST — Invalid bytes → U+FFFD ──
void test_invalid_utf8_replacement() {
    TEST("SSE_INVALID_UTF8_REPLACEMENT");

    std::string pending;
    // 0xFF is never valid in UTF-8
    std::string out = sanitize_utf8_stream(pending, std::string("\xff", 1), false);
    ASSERT_STREQ(out, "\xef\xbf\xbd");  // U+FFFD
    ASSERT_STREQ(pending, "");

    PASS();
}

// ── Test 5: SSE_FLUSH_PENDING — flush replaces pending with U+FFFD ──
void test_flush_pending() {
    TEST("SSE_FLUSH_PENDING");

    std::string pending;
    std::string frag1 = "\xe4\xbd";  // incomplete "你"
    std::string out1 = sanitize_utf8_stream(pending, frag1, false);
    ASSERT_STREQ(out1, "");
    ASSERT_STREQ(pending, "\xe4\xbd");

    // Flush with empty fragment — incomplete bytes become U+FFFD
    std::string out2 = sanitize_utf8_stream(pending, "", true);
    ASSERT_STREQ(out2, "\xef\xbf\xbd");
    ASSERT_STREQ(pending, "");

    PASS();
}

// ── Test 6: SSE_MIXED_ASCII_UTF8 — Mixed valid content ──
void test_mixed_ascii_utf8() {
    TEST("SSE_MIXED_ASCII_UTF8");

    std::string pending;
    // "Hello 你好 World" = 48 65 6C 6C 6F 20 | E4 BD A0 E5 A5 BD | 20 57 6F 72 6C 64
    std::string mixed = "Hello " "\xe4\xbd\xa0\xe5\xa5\xbd" " World";
    std::string out = sanitize_utf8_stream(pending, mixed, false);
    ASSERT_STREQ(out, mixed);
    ASSERT_STREQ(pending, "");

    PASS();
}

// ── Test 7: SSE_OVERLONG_UTF8 — Overlong sequences rejected ──
void test_overlong_utf8() {
    TEST("SSE_OVERLONG_UTF8");

    std::string pending;
    // C0 80 is an overlong encoding of U+0000 (should never appear in valid UTF-8)
    // c = 0xC0: c < 0xC2 → need stays 0 → replacement path
    std::string out = sanitize_utf8_stream(pending, std::string("\xc0\x80", 2), false);
    // Both bytes get replaced: C0 is invalid lead, 80 is continuation without lead
    ASSERT_STREQ(out, "\xef\xbf\xbd\xef\xbf\xbd");
    ASSERT_STREQ(pending, "");

    PASS();
}

int main() {
    printf("=== sanitize_utf8_stream Unit Tests ===\n\n");

    test_ascii_pass_through();
    test_chinese_pass_through();
    test_split_utf8_fragment();
    test_split_utf8_three_bytes();
    test_invalid_utf8_replacement();
    test_flush_pending();
    test_mixed_ascii_utf8();
    test_overlong_utf8();

    printf("\n=== Results: %d/%d passed", passed, tests);
    if (failed > 0) printf(", %d FAILED", failed);
    printf(" ===\n");

    return failed > 0 ? 1 : 0;
}
