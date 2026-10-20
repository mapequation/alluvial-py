"""``js_log2`` reproduces V8's ``Math.log2`` bit for bit (used by the similarity in ``getSimilarModules``).

The vectors are ``Math.log2`` results from node v24 (arm64), found by the differential fuzzer's math sweep
(``tools/ts-fixtures/fuzz``): ``math.log2`` is 1 ulp off for ~1.6 % of inputs in (0, 2).
"""

from __future__ import annotations

import math

import pytest

from alluvial.engine._utils import _fma_exact, _log2, js_div, js_log2

# (x, V8 Math.log2(x)), as float.hex
V8_VECTORS = [
    # math.log2 differs from V8 here
    ("0x1.a3d3f0319d1a4p-1", "-0x1.2537d6bab25e7p-2"),
    ("0x1.911d96b92c404p-1", "-0x1.6893aa942b1eep-2"),
    ("0x1.695b77c34b875p+0", "0x1.fd378c7672320p-2"),
    ("0x1.ba28146e8f692p-1", "-0x1.b15444c7fac1fp-3"),
    # plain (unfused) fdlibm arithmetic differs from the arm64 V8 build here
    ("0x1.69e056612b66cp+0", "0x1.ff565d04dfa4ap-2"),
    ("0x1.553a833d48dcfp-1", "-0x1.2bba4140d8aaep-1"),
    # exact and special values
    ("0x1.0000000000000p+0", "0x0.0p+0"),
    ("0x1.0000000000000p+1", "0x1.0000000000000p+0"),
    ("0x1.0000000000000p-1", "-0x1.0000000000000p+0"),
    ("0x0.0000000000001p-1022", "-0x1.0c80000000000p+10"),
    ("0x1.fffffffffffffp+1023", "0x1.0000000000000p+10"),
]


@pytest.mark.parametrize(("x", "expected"), V8_VECTORS)
def test_js_log2_matches_v8(x: str, expected: str) -> None:
    assert js_log2(float.fromhex(x)).hex() == float.fromhex(expected).hex()


def test_js_log2_specials() -> None:
    assert js_log2(0.0) == -math.inf
    assert js_log2(-0.0) == -math.inf
    assert math.isnan(js_log2(-1.0))
    assert math.isnan(js_log2(math.nan))
    assert js_log2(math.inf) == math.inf
    # entropy.ts log2 guard: non-positive / non-finite -> 0
    assert _log2(0.0) == 0.0
    assert _log2(math.inf) == 0.0


def test_math_log2_would_differ() -> None:
    """Guard that the vectors still exercise the difference (else the port could silently regress)."""
    x, expected = V8_VECTORS[0]
    assert math.log2(float.fromhex(x)) != float.fromhex(expected)


def test_fma_fallback_matches_math_fma() -> None:
    if not hasattr(math, "fma"):
        pytest.skip("math.fma needs Python 3.13")
    vals = [0.1, -0.3, 1 / 3, 2.0**-60, 1e300, -7.25, 0.6666666666666735]
    for a in vals:
        for b in vals:
            for c in vals:
                if math.isfinite(a * b + c):
                    assert _fma_exact(a, b, c) == math.fma(a, b, c)


def test_js_div_uses_js_log2() -> None:
    p, q = [0.25, 0.75], [0.5, 0.5]
    mix = [0.375, 0.625]
    expected = 0.5 * (
        (0 + 0.25 * js_log2(0.25 / 0.375) + 0.75 * js_log2(0.75 / 0.625))
        + (0 + 0.5 * js_log2(0.5 / 0.375) + 0.5 * js_log2(0.5 / 0.625))
    )
    assert js_div(p, q) == expected
    assert mix == [0.5 * (a + b) for a, b in zip(p, q)]
