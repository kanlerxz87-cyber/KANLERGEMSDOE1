#!/usr/bin/env python3
"""Retired fail-open submit-page builder.

The previous implementation accepted detector-only uniqueness evidence while the literal
registry rule failed, then published an apparent recommendation. It is intentionally disabled.
A replacement must be built around the complete registry, admissible fold-local evidence, and a
separate selector approval before any download link can be emitted.
"""
import argparse


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    raise SystemExit(
        "STOP: legacy release renderer is retired. Its detector-only uniqueness rule could "
        "recommend a file despite the literal registry failure and inadmissible diagnostics. "
        "Do not regenerate a submit page or publish a download until a separately reviewed, "
        "fail-closed selector and complete evidence are implemented."
    )


if __name__ == "__main__":
    main()
