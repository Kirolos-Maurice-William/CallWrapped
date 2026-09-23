"""
Global test setup: ensures UTF-8 console encoding across platforms (especially Windows).
Imported at the top of test files to guarantee clean output for Arabic and special characters.
"""
import sys

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
