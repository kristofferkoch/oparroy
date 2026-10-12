// KLEE proof: the soft integer runtime's width-generic algorithm
// (firmware/node/runtime.hpp), exhausted at 8 bits. Over fully symbolic
// operands — every input pair, no sampling — the templates match the
// harness's native arithmetic: on the host target `*`, `/`, `%` lower
// to real LLVM instructions (never to the libcalls under test), so the
// native operators are the oracle; integer promotion computes them in
// int and the cast back is the mod-2^N wrap the runtime must return.
// The edges C++ calls UB are guarded and proved against the RISC-V M
// extension's hardware semantics instead: divide-by-zero returns
// quotient all-ones / remainder = dividend, and INT_MIN / -1 wraps to
// the dividend with remainder 0 — the values a future M-extension part
// would produce in silicon.
//
// Why 8 bits proves the target code: the 32/64-bit libcalls
// (runtime.cpp) are one-line wrappers over these same templates, and
// the algorithm has no width-dependent branch — top-bit alignment
// saturation, both hardware-semantics edges, sign handling — so
// exhausting one width proves the logic at every width; wider widths
// would add no new paths, only solver time. And solver time is the
// boundary: the final multiplier/divider equivalence query is a hard
// SAT instance — measured: Z3 wants ~110 s for a 16-bit multiply and
// doesn't crack 16-bit division (or 32-bit anything) in 5 minutes, STP
// is slower still — while 8 bits proves in seconds. The width-specific
// residues this leaves — word-size constants, the shift counter — are
// pinned at 32/64 bits by the host unit tests (test_runtime.cpp).

#include "../runtime.hpp"
#include "../../lib/klee.hpp"

#include <cstdint>
#include <limits>

namespace {

// The entry points, not these functions, must own the symbolic
// variables: the nix cc-wrapper compiles at -O2, and a single-call
// static function gets inlined — the LLVM inliner then plants lifetime
// markers for its locals (not covered by the recipe's
// -disable-lifetime-markers, which only governs CodeGen) and klee 3.2
// has no lifetime handler. Values-in keeps every alloca in the entry
// function, where the flag applies (the protocol harnesses' shape).
template <typename U> void prove_mul(U a, U b) {
    KLEE_PROVE(oparroy::runtime::umul(a, b) == static_cast<U>(a * b));
}

template <typename U> void prove_udivmod(U a, U b) {
    const auto [q, r] = oparroy::runtime::udivmod(a, b);
    if (b == 0) {
        // Hardware semantics: quotient all-ones, remainder = dividend.
        KLEE_PROVE(q == std::numeric_limits<U>::max());
        KLEE_PROVE(r == a);
        return;
    }
    KLEE_PROVE(q == static_cast<U>(a / b));
    KLEE_PROVE(r == static_cast<U>(a % b));
}

// NOLINTNEXTLINE(bugprone-easily-swappable-parameters)
template <typename S, typename U> void prove_sdivmod(U a, U b) {
    // The same bit patterns read as signed cover the signed domain.
    const S sa = static_cast<S>(a);
    const S sb = static_cast<S>(b);
    const S q = oparroy::runtime::signed_quotient(sa, sb);
    const S r = oparroy::runtime::signed_remainder(sa, sb);
    if (b == 0) {
        // Hardware semantics are sign-independent.
        KLEE_PROVE(q == static_cast<S>(-1));
        KLEE_PROVE(r == sa);
        return;
    }
    if (sa == std::numeric_limits<S>::min() && sb == -1) {
        // Hardware overflow: quotient = dividend, remainder 0.
        KLEE_PROVE(q == std::numeric_limits<S>::min());
        KLEE_PROVE(r == 0);
        return;
    }
    KLEE_PROVE(q == static_cast<S>(sa / sb));
    KLEE_PROVE(r == static_cast<S>(sa % sb));
}

template <typename S, typename U> void prove_width(U a, U b) {
    prove_mul(a, b);
    prove_udivmod(a, b);
    prove_sdivmod<S>(a, b);
}

} // namespace

extern "C" int klee_runtime8() {
    uint8_t a = 0;
    uint8_t b = 0;
    klee_make_symbolic(&a, sizeof a, "a8");
    klee_make_symbolic(&b, sizeof b, "b8");
    prove_width<int8_t>(a, b);
    return 0;
}
