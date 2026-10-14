#!/usr/bin/env python3
"""
Reproducible Lines of Code (LOC) and Code Quality Auditor.
AI Data Intelligence Cloud - Engineering Standards Tool

Conforms to Master Project Specification Section 8:
- Excludes .git, virtual environments, node_modules, build/dist, caches, and generated artifacts.
- Separates production source, tests, and documentation.
- Groups results by language and module.
- Detects duplicate files or suspiciously repetitive source.
- Reports authentic repository statistics without artificial padding.
"""

import hashlib
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Directories strictly excluded from LOC auditing
EXCLUDED_DIRS: Set[str] = {
    ".git",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    ".pytest_cache",
    ".vitest",
    "coverage",
    "htmlcov",
    ".vscode",
    ".idea",
    ".system_generated",
    ".gemini",
    "data",
    "uploads",
    "mlruns",
}

# File extensions or names excluded
EXCLUDED_EXTENSIONS: Set[str] = {
    ".pyc",
    ".pyo",
    ".pyd",
    ".lock",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".tsbuildinfo",
}

EXCLUDED_FILENAMES: Set[str] = {
    "package-lock.json",
    ".DS_Store",
    "Thumbs.db",
}

EXTENSION_LANGUAGE_MAP: Dict[str, str] = {
    ".py": "Python",
    ".ts": "TypeScript",
    ".tsx": "TypeScript (React)",
    ".js": "JavaScript",
    ".jsx": "JavaScript (React)",
    ".css": "CSS",
    ".html": "HTML",
    ".md": "Markdown",
    ".yml": "YAML",
    ".yaml": "YAML",
    ".toml": "TOML",
    ".json": "JSON",
    ".sh": "Shell",
    ".ps1": "PowerShell",
}


class FileStats:
    def __init__(self, path: Path, rel_path: str, category: str, language: str):
        self.path = path
        self.rel_path = rel_path
        self.category = category  # 'Production', 'Test', 'Documentation/Config'
        self.language = language
        self.total_lines = 0
        self.blank_lines = 0
        self.comment_lines = 0
        self.code_lines = 0
        self.sha256 = ""
        self.repetitive_lines_ratio = 0.0


def classify_category(rel_path: str) -> str:
    """Classify a relative file path into Production, Test, or Documentation/Config."""
    normalized = rel_path.replace("\\", "/").lower()

    if "/tests/" in normalized or normalized.startswith("tests/") or ".test." in normalized or "/test/" in normalized:
        return "Test"

    if (
        normalized.endswith(".md")
        or normalized.startswith("docs/")
        or normalized.endswith(".example")
        or normalized.endswith(".toml")
        or normalized.endswith(".yml")
        or normalized.endswith(".yaml")
        or normalized.endswith("docker-compose.yml")
    ):
        return "Documentation/Config"

    return "Production"


def determine_module(rel_path: str) -> str:
    """Identify the module boundary for the file."""
    parts = Path(rel_path).parts
    if len(parts) > 1:
        return parts[0]
    return "root"


def analyze_file(file_path: Path, root_path: Path) -> FileStats:
    """Parse line metrics and content fingerprint for a given file."""
    rel_path = str(file_path.relative_to(root_path))
    ext = file_path.suffix.lower()
    language = EXTENSION_LANGUAGE_MAP.get(ext, "Other")
    category = classify_category(rel_path)

    stats = FileStats(file_path, rel_path, category, language)

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception:
        return stats

    stats.total_lines = len(lines)
    hasher = hashlib.sha256()

    line_counts: Dict[str, int] = defaultdict(int)

    for line in lines:
        hasher.update(line.encode("utf-8", errors="replace"))
        stripped = line.strip()

        if not stripped:
            stats.blank_lines += 1
        elif (
            stripped.startswith("#")
            or stripped.startswith("//")
            or stripped.startswith("/*")
            or stripped.startswith("*")
        ):
            stats.comment_lines += 1
        else:
            stats.code_lines += 1
            if len(stripped) > 5:
                line_counts[stripped] += 1

    stats.sha256 = hasher.hexdigest()

    # Detect suspiciously repeated lines (>4 repetitions of identical non-trivial lines)
    repeated_instances = sum(c - 1 for c in line_counts.values() if c > 3)
    if stats.code_lines > 0:
        stats.repetitive_lines_ratio = repeated_instances / stats.code_lines

    return stats


def scan_repository(root_path: Path) -> Tuple[List[FileStats], List[Tuple[str, str]], List[str]]:
    """Walk repository tree filtering excluded items and analyzing files."""
    file_stats_list: List[FileStats] = []
    seen_hashes: Dict[str, str] = {}
    duplicates: List[Tuple[str, str]] = []
    suspicious_files: List[str] = []

    for current_root, dirs, files in os.walk(root_path):
        # Prune excluded directories in-place
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS and not d.startswith(".venv")]

        for filename in files:
            if filename in EXCLUDED_FILENAMES:
                continue

            file_path = Path(current_root) / filename
            ext = file_path.suffix.lower()

            if ext in EXCLUDED_EXTENSIONS:
                continue

            stats = analyze_file(file_path, root_path)
            if stats.total_lines == 0:
                continue

            # Duplicate detection
            if stats.sha256 in seen_hashes:
                duplicates.append((stats.rel_path, seen_hashes[stats.sha256]))
            else:
                seen_hashes[stats.sha256] = stats.rel_path

            # Repetition anomaly detection
            if stats.repetitive_lines_ratio > 0.40 and stats.code_lines > 30:
                suspicious_files.append(
                    f"{stats.rel_path} ({stats.repetitive_lines_ratio:.1%} repeated lines)"
                )

            file_stats_list.append(stats)

    return file_stats_list, duplicates, suspicious_files


def print_report(root_path: Path) -> None:
    """Generate structured, formatted audit report."""
    files, duplicates, suspicious = scan_repository(root_path)

    print("=" * 80)
    print(" AI DATA INTELLIGENCE CLOUD - REPRODUCIBLE LOC & QUALITY AUDIT REPORT")
    print("=" * 80)

    # Category Breakdown
    cat_metrics: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    lang_metrics: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    mod_metrics: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

    total_files = len(files)
    total_total = sum(f.total_lines for f in files)
    total_code = sum(f.code_lines for f in files)
    total_comments = sum(f.comment_lines for f in files)
    total_blanks = sum(f.blank_lines for f in files)

    for f in files:
        module = determine_module(f.rel_path)
        for d in [cat_metrics[f.category], lang_metrics[f.language], mod_metrics[module]]:
            d["files"] += 1
            d["total"] += f.total_lines
            d["code"] += f.code_lines
            d["comments"] += f.comment_lines
            d["blanks"] += f.blank_lines

    # 1. Summary by Category
    print("\n--- 1. METRICS BY CATEGORY ---")
    print(f"{'Category':<24} {'Files':>6} {'Code LOC':>10} {'Comments':>10} {'Blanks':>8} {'Total':>10}")
    print("-" * 72)
    for cat in ["Production", "Test", "Documentation/Config"]:
        m = cat_metrics[cat]
        print(f"{cat:<24} {m['files']:>6} {m['code']:>10} {m['comments']:>10} {m['blanks']:>8} {m['total']:>10}")
    print("-" * 72)
    print(f"{'TOTAL REPOSITORY':<24} {total_files:>6} {total_code:>10} {total_comments:>10} {total_blanks:>8} {total_total:>10}")

    # 2. Metrics by Language
    print("\n--- 2. METRICS BY LANGUAGE ---")
    print(f"{'Language':<24} {'Files':>6} {'Code LOC':>10} {'Comments':>10} {'Blanks':>8} {'Total':>10}")
    print("-" * 72)
    for lang, m in sorted(lang_metrics.items(), key=lambda x: x[1]["code"], reverse=True):
        print(f"{lang:<24} {m['files']:>6} {m['code']:>10} {m['comments']:>10} {m['blanks']:>8} {m['total']:>10}")

    # 3. Metrics by Module
    print("\n--- 3. METRICS BY MODULE ---")
    print(f"{'Module':<24} {'Files':>6} {'Code LOC':>10} {'Comments':>10} {'Blanks':>8} {'Total':>10}")
    print("-" * 72)
    for mod, m in sorted(mod_metrics.items(), key=lambda x: x[1]["code"], reverse=True):
        print(f"{mod:<24} {m['files']:>6} {m['code']:>10} {m['comments']:>10} {m['blanks']:>8} {m['total']:>10}")

    # 4. Integrity and Duplication Audit
    print("\n--- 4. CODE INTEGRITY & ANTI-PADDING AUDIT ---")
    if duplicates:
        print(f"[!] WARNING: Found {len(duplicates)} exact duplicate file pairs:")
        for dup, orig in duplicates:
            print(f"    - {dup} is identical to {orig}")
    else:
        print("  [OK] Zero duplicate files detected (100% unique source trees).")

    if suspicious:
        print(f"[!] WARNING: Found {len(suspicious)} suspiciously repetitive files:")
        for s in suspicious:
            print(f"    - {s}")
    else:
        print("  [OK] Zero artificially padded or repetitive filler files detected.")

    print("\n" + "=" * 80)
    prod_code = cat_metrics["Production"]["code"]
    test_code = cat_metrics["Test"]["code"]
    print(f" AUTHENTIC PRODUCTION LOC: {prod_code:,}")
    print(f" AUTHENTIC TEST LOC:       {test_code:,}")
    ratio = test_code / max(prod_code, 1)
    print(f" TEST-TO-CODE RATIO:       {ratio:.2f}x")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parent.parent
    print_report(repo_root)
