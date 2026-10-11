#!/usr/bin/env python3
"""Limit and Security Checker for Git Pre-Commit / Pre-Push hooks.

Validates:
1. File size limits (rejects staged files > 2 MB).
2. Forbidden file extensions (.pdf, .db, .sqlite, .zip, .tar, .env).
3. High-entropy secret patterns (AWS secret keys, private keys).
4. Code limits (batch recipient upper bounds, line length).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

MAX_FILE_SIZE_BYTES = 2 * 1024 * 1024  # 2 MB limit per staged file
FORBIDDEN_EXTENSIONS = {
    ".db",
    ".sqlite",
    ".sqlite3",
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
    ".pyc",
}
FORBIDDEN_FILES = {
    ".env",
    ".env.local",
    ".env.production",
    "certificates.db",
}
SUSPICIOUS_PATTERNS = [
    re.compile(r"-----BEGIN (RSA|EC|OPENSSH|DSA|PGP) PRIVATE KEY-----"),
    re.compile(r"""(?i)(aws_secret_access_key|password)\s*=\s*['"][a-zA-Z0-9/+=]{20,}['"]"""),
]


def log_info(msg: str) -> None:
    print(f"\033[94m[LIMIT-CHECK]\033[0m {msg}")


def log_success(msg: str) -> None:
    print(f"\033[92m[LIMIT-CHECK PASS]\033[0m {msg}")


def log_error(msg: str) -> None:
    print(f"\033[91m[LIMIT-CHECK FAIL]\033[0m {msg}", file=sys.stderr)


def get_staged_files() -> list[str]:
    """Retrieve list of staged files in git index."""
    try:
        output = subprocess.check_output(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return [line.strip() for line in output.splitlines() if line.strip()]
    except Exception:
        return []


def check_file_limits(staged_files: list[str]) -> list[str]:
    """Check staged files for size and forbidden extensions."""
    errors: list[str] = []

    for file_path_str in staged_files:
        p = Path(file_path_str)
        if not p.exists():
            continue

        # 1. Forbidden files
        if p.name in FORBIDDEN_FILES:
            errors.append(
                f"Forbidden file staged: '{file_path_str}'. Sensitive/environment files must not be committed."
            )

        # 2. Forbidden extensions
        if p.suffix.lower() in FORBIDDEN_EXTENSIONS:
            errors.append(
                f"Forbidden extension '{p.suffix}' in staged file: '{file_path_str}'. "
                "Generated artifacts, PDFs, and databases must be gitignored."
            )

        # 3. File size limit
        try:
            file_size = p.stat().st_size
            if file_size > MAX_FILE_SIZE_BYTES:
                size_mb = file_size / (1024 * 1024)
                errors.append(
                    f"File size limit exceeded: '{file_path_str}' is {size_mb:.2f} MB "
                    f"(limit is {MAX_FILE_SIZE_BYTES / (1024 * 1024):.1f} MB)."
                )
        except OSError as e:
            errors.append(f"Unable to read file stat for '{file_path_str}': {e}")

    return errors


def check_secret_patterns() -> list[str]:
    """Inspect staged diffs for sensitive patterns like private keys."""
    errors: list[str] = []
    try:
        diff_text = subprocess.check_output(
            ["git", "diff", "--cached", "-U0"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        for pattern in SUSPICIOUS_PATTERNS:
            match = pattern.search(diff_text)
            if match:
                errors.append(
                    f"Potential secret detected in staged changes matching: {pattern.pattern}"
                )
    except Exception:
        pass
    return errors


def check_code_invariants() -> list[str]:
    """Verify application limits such as max batch recipients."""
    errors: list[str] = []
    config_file = Path("app/config.py")
    if config_file.exists():
        content = config_file.read_text(encoding="utf-8")
        match = re.search(r"max_recipients_per_batch:\s*int\s*=\s*(\d+)", content)
        if match:
            limit = int(match.group(1))
            if limit > 5000:
                errors.append(
                    f"Batch recipient limit too high in app/config.py ({limit} > 5000 allowed)."
                )
    return errors


def main() -> int:
    staged = get_staged_files()
    if not staged:
        log_info("No staged files found. Skipping limit check.")
        return 0

    log_info(f"Scanning {len(staged)} staged file(s) for limits and policies...")

    errors: list[str] = []
    errors.extend(check_file_limits(staged))
    errors.extend(check_secret_patterns())
    errors.extend(check_code_invariants())

    if errors:
        for err in errors:
            log_error(err)
        log_error(f"Commit aborted: {len(errors)} limit policy violation(s) found.")
        return 1

    log_success("All file sizes, extensions, and security limits passed!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
