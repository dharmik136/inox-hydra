"""
Ed25519 Signatures, in Pure Python.
===================================
The reference algorithm from RFC 8032, section 6, for the offline licence: a
licence is signed once by the vendor with a key that never leaves the
vendor's machine, and verified by the studio with the public key it ships.

Pure Python so the studio needs no compiled cryptography package for one
verification at start-up. This is the RFC's own code, checked against the
RFC's test vectors in tests/test_licensing.py. It is not constant time, which
matters only when signing, and signing happens on the vendor's machine
(tools/licence_keys.py), never inside the studio.

Strict Invariants:
- Zero em-dashes in any code, docstring or comment.
- Verification never raises on malformed input: it answers False.
"""

import hashlib

_P = 2 ** 255 - 19
_Q = 2 ** 252 + 27742317777372353535851937790883648493


def _inv(x: int) -> int:
    return pow(x, _P - 2, _P)


_D = -121665 * _inv(121666) % _P
_SQRT_M1 = pow(2, (_P - 1) // 4, _P)


def _sha512_modq(data: bytes) -> int:
    return int.from_bytes(hashlib.sha512(data).digest(), "little") % _Q


def _add(a, b):
    # Extended coordinates (X, Y, Z, T) with x = X/Z, y = Y/Z, x*y = T/Z.
    p_a, p_b = (a[1] - a[0]) * (b[1] - b[0]) % _P, (a[1] + a[0]) * (b[1] + b[0]) % _P
    p_c, p_d = 2 * a[3] * b[3] * _D % _P, 2 * a[2] * b[2] % _P
    e, f, g, h = p_b - p_a, p_d - p_c, p_d + p_c, p_b + p_a
    return (e * f, g * h, f * g, e * h)


def _mul(s: int, point):
    result = (0, 1, 1, 0)
    while s > 0:
        if s & 1:
            result = _add(result, point)
        point = _add(point, point)
        s >>= 1
    return result


def _equal(a, b) -> bool:
    if (a[0] * b[2] - b[0] * a[2]) % _P != 0:
        return False
    return (a[1] * b[2] - b[1] * a[2]) % _P == 0


def _recover_x(y: int, sign: int):
    if y >= _P:
        return None
    x2 = (y * y - 1) * _inv(_D * y * y + 1)
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P != 0:
        x = x * _SQRT_M1 % _P
    if (x * x - x2) % _P != 0:
        return None
    if (x & 1) != sign:
        x = _P - x
    return x


_G_Y = 4 * _inv(5) % _P
_G_X = _recover_x(_G_Y, 0)
_G = (_G_X, _G_Y, 1, _G_X * _G_Y % _P)


def _compress(point) -> bytes:
    z_inv = _inv(point[2])
    x = point[0] * z_inv % _P
    y = point[1] * z_inv % _P
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _decompress(data: bytes):
    if len(data) != 32:
        return None
    y = int.from_bytes(data, "little")
    sign = y >> 255
    y &= (1 << 255) - 1
    x = _recover_x(y, sign)
    if x is None:
        return None
    return (x, y, 1, x * y % _P)


def _expand(secret: bytes):
    if len(secret) != 32:
        raise ValueError("an Ed25519 secret key is 32 bytes")
    digest = hashlib.sha512(secret).digest()
    a = int.from_bytes(digest[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, digest[32:]


def public_key(secret: bytes) -> bytes:
    a, _prefix = _expand(secret)
    return _compress(_mul(a, _G))


def sign(secret: bytes, message: bytes) -> bytes:
    a, prefix = _expand(secret)
    public = _compress(_mul(a, _G))
    r = _sha512_modq(prefix + message)
    r_point = _compress(_mul(r, _G))
    h = _sha512_modq(r_point + public + message)
    s = (r + h * a) % _Q
    return r_point + int.to_bytes(s, 32, "little")


def verify(public: bytes, message: bytes, signature: bytes) -> bool:
    if not isinstance(public, (bytes, bytearray)) or len(public) != 32:
        return False
    if not isinstance(signature, (bytes, bytearray)) or len(signature) != 64:
        return False
    a_point = _decompress(bytes(public))
    if a_point is None:
        return False
    r_bytes = bytes(signature[:32])
    r_point = _decompress(r_bytes)
    if r_point is None:
        return False
    s = int.from_bytes(signature[32:], "little")
    if s >= _Q:
        return False
    h = _sha512_modq(r_bytes + bytes(public) + message)
    return _equal(_mul(s, _G), _add(r_point, _mul(h, a_point)))
