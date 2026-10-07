"""Recover the exact byte form of evidence-audit.md bound as audit_sha256 at
bc290ef (544977b1...), which a core.autocrlf checkout later rewrote.

Content is unchanged (every candidate normalizes to the same LF blob); only the
line-ending pattern can vary. Search structured masks: uniform k-segment
patterns (k<=4) and small Hamming-distance flips from pure CRLF/LF.

Usage: python recover_audit_bytes.py  (prints any hit; exit 0)
"""
import hashlib
import itertools
import sys

REPO = r"C:\Users\Kevin\AppData\Local\Temp\scout008-target"
PATH = r".ai\work\PILOT-BUG-01\evidence-audit.md"
TARGET = "544977b162351a3a0114c079dc4904a29fdc736fe8141ed0fafaa9c12213439c"

import argparse

_parser = argparse.ArgumentParser()
_parser.add_argument("--repo", default=REPO)
_parser.add_argument("--path", default=PATH)
_parser.add_argument("--target", default=TARGET)
_parser.add_argument("--restore", action="store_true")
_args, _ = _parser.parse_known_args()
REPO = _args.repo
PATH = _args.path
TARGET = _args.target

raw = open(REPO + "\\" + PATH, "rb").read()
lf = raw.replace(b"\r\n", b"\n")
parts = lf.split(b"\n")
nb = len(parts) - 1  # number of line breaks


def build(mask):
    out = []
    for i in range(nb):
        out.append(parts[i])
        out.append(b"\r\n" if mask[i] else b"\n")
    out.append(parts[-1])
    return b"".join(out)


def digest(mask):
    return hashlib.sha256(build(mask)).hexdigest()


hits = []
print("breaks:", nb)
print("pure CRLF:", digest([True] * nb), "pure LF:", digest([False] * nb))
print("BOM+LF   :", hashlib.sha256(b"\xef\xbb\xbf" + lf).hexdigest())
print("BOM+CRLF :", hashlib.sha256(b"\xef\xbb\xbf" + build([True] * nb)).hexdigest())

# k-segment uniform patterns
for k in (1, 2, 3, 4):
    for cuts in itertools.combinations(range(1, nb), k - 1):
        bounds = (0,) + cuts + (nb,)
        for styles in itertools.product((False, True), repeat=k):
            mask = []
            for s in range(k):
                mask.extend([styles[s]] * (bounds[s + 1] - bounds[s]))
            if digest(mask) == TARGET:
                hits.append(("segments", cuts, styles))
                print("HIT segments cuts=%r styles=%r" % (cuts, styles))
    print("done k=%d, hits=%d" % (k, len(hits)))

# small flips from uniform bases
for base in (True, False):
    base_mask = [base] * nb
    for d in (1, 2, 3):
        for flips in itertools.combinations(range(nb), d):
            mask = base_mask[:]
            for f in flips:
                mask[f] = not base
            if digest(mask) == TARGET:
                hits.append(("flips", base, flips))
                print("HIT flips base=%r flips=%r" % (base, flips))
    print("done flips base=%r, hits=%d" % (base, len(hits)))

print("TOTAL HITS:", len(hits))
for h in hits:
    print(h)

# --restore: write the first matching byte form back to the worktree file.
if _args.restore:
    if not hits:
        print("no matching pattern; nothing restored")
        sys.exit(1)
    h0 = hits[0]
    if h0[0] == "segments":
        _, cuts, styles = h0
        bounds = (0,) + cuts + (nb,)
        mask = []
        for s in range(len(styles)):
            mask.extend([styles[s]] * (bounds[s + 1] - bounds[s]))
    else:
        _, base, flips = h0
        mask = [base] * nb
        for f in flips:
            mask[f] = not base
    data = build(mask)
    assert hashlib.sha256(data).hexdigest() == TARGET
    open(REPO + "\\" + PATH, "wb").write(data)
    print("RESTORED %d bytes to worktree (sha256 %s)" % (len(data), TARGET))