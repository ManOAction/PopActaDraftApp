"""Proves the test harness actually runs.

The 2025 app had no tests anywhere (LEG-8), so every change was a guess. This
file's only job is to fail if pytest cannot import the package — i.e. to make
CI's green tick mean something before Phase 1 supplies real domain tests.
"""

import sys

import popacta


def test_package_imports():
    assert popacta.__version__ == "0.1.0"


def test_python_is_at_least_313():
    """`pyproject.toml` claims >=3.13; check the interpreter agrees."""
    assert sys.version_info >= (3, 13)
