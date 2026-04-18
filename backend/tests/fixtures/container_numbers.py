# backend/tests/fixtures/container_numbers.py
"""Known-good and known-bad ISO 6346 container numbers for validator tests.

Per Testing Spec §2.5: "ISO 6346 test data: include at least 5 known-good and
5 known-bad container numbers in tests/fixtures/container_numbers.py. Compute
check digits manually and document the expected results."

The check-digit algorithm:
- Map each letter A..Z to its ISO 6346 value (A=10, B=12, ..., skipping 11/22/33).
- Letters occupy positions 0..3; serial digits occupy positions 4..9.
- Multiply each value by 2**i for i in 0..9.
- Sum, take mod 11. A remainder of 10 becomes 0.
- Compare to the 11th character (the check digit).

Each entry below documents the computed check digit so fixture drift is
immediately visible in a diff.
"""

from __future__ import annotations

VALID_CONTAINER_NUMBERS: list[str] = [
    # CSQU3054383 — standard reference valid container number (many sources).
    # C=13, S=30, Q=28, U=32 + digits 3,0,5,4,3,8
    # sum = 13 + 60 + 112 + 256 + 48 + 0 + 320 + 512 + 768 + 4096 = 6185
    # 6185 % 11 = 3 → check digit 3 ✓
    "CSQU3054383",
    # MSCU1234566 — Maersk-style prefix with sequential digits.
    # M=24, S=30, C=13, U=32 + 1,2,3,4,5,6
    # sum = 24 + 60 + 52 + 256 + 16 + 64 + 192 + 512 + 1280 + 3072 = 5528
    # 5528 % 11 = 6 → check digit 6 ✓
    "MSCU1234566",
    # HJCU1234562 — Hapag-Lloyd-style prefix, same serial.
    # H=18, J=20, C=13, U=32 + 1,2,3,4,5,6
    # sum = 18 + 40 + 52 + 256 + 16 + 64 + 192 + 512 + 1280 + 3072 = 5502
    # 5502 % 11 = 2 → check digit 2 ✓
    "HJCU1234562",
    # APLU4567893
    # A=10, P=27, L=23, U=32 + 4,5,6,7,8,9
    # sum = 10 + 54 + 92 + 256 + 64 + 160 + 384 + 896 + 2048 + 4608 = 8572
    # 8572 % 11 = 3 → check digit 3 ✓
    "APLU4567893",
    # TCLU9999996
    # T=31, C=13, L=23, U=32 + 9,9,9,9,9,9
    # sum = 31 + 26 + 92 + 256 + 144 + 288 + 576 + 1152 + 2304 + 4608 = 9477
    # 9477 % 11 = 6 → check digit 6 ✓
    "TCLU9999996",
]


# Same prefixes as above, but with deliberately wrong check digits.
INVALID_CHECK_DIGIT: list[str] = [
    "CSQU3054384",  # should be 3, is 4
    "MSCU1234567",  # should be 6, is 7
    "HJCU1234560",  # should be 2, is 0
    "APLU4567890",  # should be 3, is 0
    "TCLU9999999",  # should be 6, is 9
]


# Wrong-format cases — rejected before any check-digit math.
INVALID_FORMAT: list[str] = [
    "ABC1234567",  # 3 letters + 7 digits
    "MSCU123456",  # 10 characters total
    "MSCU12345678",  # 12 characters total
    "1234567MSCU",  # digits then letters
    "mscu1234566",  # lowercase
    "MSC-1234566",  # hyphen instead of letter
    "MSCU 1234566",  # whitespace in middle
    "",  # empty string
]
