"""Smoke test: verifies the package imports and the entry point exists.

Real tests start in Slice 1.
"""

import reddit_corpus


def test_package_imports() -> None:
    assert reddit_corpus is not None


def test_main_callable_exists() -> None:
    assert callable(reddit_corpus.main)
