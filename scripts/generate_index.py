#!/usr/bin/env python3
"""Generate a directory listing index.html for GitHub Pages.

Year/month directories under data/prices/ are rendered as collapsible
<details> elements.  Only the current year and current month are expanded
by default.
"""

import re
from datetime import date
from pathlib import Path

WHITELIST = ["data", "web", "docs", "README.md"]
IGNORE_FILES = {".gitkeep", ".DS_Store"}

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="pl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>CenyPradu — directory listing</title>
  <style>
    body {{ background: #1a1a2e; color: #e0e0e0; font-family: 'Courier New', monospace; padding: 2rem; margin: 0; }}
    a {{ color: #64b5f6; text-decoration: none; }}
    a:hover {{ text-decoration: underline; color: #90caf9; }}
    h1 {{ color: #bb86fc; font-size: 1.4rem; margin-bottom: 0.5rem; }}
    .muted {{ color: #888; font-size: 0.85rem; }}
    .tree {{ font-size: 14px; line-height: 1.6; white-space: pre; overflow-x: auto; }}
    .tree details {{ display: inline; }}
    .tree summary {{ display: list-item; cursor: pointer; list-style: none; }}
    .tree summary::-webkit-details-marker {{ display: none; }}
  </style>
</head>
<body>
  <h1>CenyPradu/</h1>
  <p class="muted">Tymczasowy directory listing — dane z TGE i taryfy dystrybucyjne</p>
<div class="tree">
{tree}
</div>
</body>
</html>
"""

TODAY = date.today()
CURRENT_YEAR = str(TODAY.year)
CURRENT_MONTH = f"{TODAY.month:02d}"

# Pattern to detect year (e.g. "2026") and month (e.g. "04") directory names
YEAR_RE = re.compile(r"^\d{4}$")
MONTH_RE = re.compile(r"^\d{2}$")


def _is_prices_year_dir(entry: Path) -> bool:
    return (
        entry.is_dir()
        and YEAR_RE.match(entry.name) is not None
        and entry.parent.name == "prices"
    )


def _is_prices_month_dir(entry: Path) -> bool:
    return (
        entry.is_dir()
        and MONTH_RE.match(entry.name) is not None
        and YEAR_RE.match(entry.parent.name) is not None
        and entry.parent.parent.name == "prices"
    )


def _should_collapse(entry: Path) -> bool:
    """Return True if this directory should be rendered as a collapsible <details>."""
    return _is_prices_year_dir(entry) or _is_prices_month_dir(entry)


def _is_expanded(entry: Path) -> bool:
    """Return True if this collapsible directory should be open by default."""
    if _is_prices_year_dir(entry):
        return entry.name == CURRENT_YEAR
    if _is_prices_month_dir(entry):
        return entry.parent.name == CURRENT_YEAR and entry.name == CURRENT_MONTH
    return True


def build_tree(directory: Path, prefix: str = "", root: Path | None = None) -> str:
    if root is None:
        root = directory

    entries = sorted(directory.iterdir(), key=lambda e: (not e.is_dir(), e.name))
    entries = [e for e in entries if e.name not in IGNORE_FILES]

    # Filter out empty directories
    filtered = []
    for e in entries:
        if e.is_dir():
            if any(
                f for f in e.rglob("*") if f.is_file() and f.name not in IGNORE_FILES
            ):
                filtered.append(e)
        else:
            filtered.append(e)

    lines = []
    for i, entry in enumerate(filtered):
        is_last = i == len(filtered) - 1
        connector = "└── " if is_last else "├── "
        child_prefix = prefix + ("    " if is_last else "│   ")

        if entry.is_dir():
            if _should_collapse(entry):
                open_attr = " open" if _is_expanded(entry) else ""
                file_count = sum(
                    1
                    for f in entry.rglob("*")
                    if f.is_file() and f.name not in IGNORE_FILES
                )
                label = f"{entry.name}/ ({file_count})"
                subtree = build_tree(entry, child_prefix, root)
                lines.append(
                    f"{prefix}{connector}"
                    f"<details{open_attr}><summary>{label}</summary>"
                    f"\n{subtree}</details>"
                )
            else:
                lines.append(f"{prefix}{connector}{entry.name}/")
                lines.append(build_tree(entry, child_prefix, root))
        else:
            rel = entry.relative_to(root)
            lines.append(f'{prefix}{connector}<a href="{rel}">{entry.name}</a>')

    return "\n".join(lines)


def main():
    repo_root = Path(__file__).resolve().parent.parent
    entries = []
    for name in WHITELIST:
        path = repo_root / name
        if path.exists():
            entries.append(path)

    lines = []
    for i, entry in enumerate(sorted(entries, key=lambda e: (not e.is_dir(), e.name))):
        is_last = i == len(entries) - 1
        connector = "└── " if is_last else "├── "
        child_prefix = "    " if is_last else "│   "

        if entry.is_dir():
            lines.append(f"{connector}{entry.name}/")
            lines.append(build_tree(entry, child_prefix, repo_root))
        else:
            lines.append(f'{connector}<a href="{entry.name}">{entry.name}</a>')

    tree = "\n".join(lines)
    html = HTML_TEMPLATE.format(tree=tree)
    out = repo_root / "index.html"
    out.write_text(html)
    print(f"Generated {out}")


if __name__ == "__main__":
    main()
