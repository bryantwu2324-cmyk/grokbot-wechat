#!/usr/bin/env python3
"""Check vendored wheels against SHA256SUMS. No network."""
import hashlib, os, sys

ROOT = os.path.dirname(os.path.abspath(__file__))


def main():
    sums = os.path.join(ROOT, "SHA256SUMS")
    wheels = os.path.join(ROOT, "wheels")
    if not os.path.isfile(sums) or not os.path.isdir(wheels):
        print("SHA256SUMS or wheels/ is missing")
        return 1
    expected = {}
    with open(sums, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            digest, name = line.split()
            if "/" in name or name.startswith("."):
                print("unexpected wheel name")
                return 1
            expected[name] = digest
    found = set(os.listdir(wheels))
    if found != set(expected):
        print("wheel set does not match SHA256SUMS")
        return 1
    for name, digest in expected.items():
        path = os.path.join(wheels, name)
        got = hashlib.sha256(open(path, "rb").read()).hexdigest()
        if got != digest:
            print("hash mismatch: %s" % name)
            return 1
    print("wheel hashes ok (%d files)" % len(expected))
    return 0


if __name__ == "__main__":
    sys.exit(main())
