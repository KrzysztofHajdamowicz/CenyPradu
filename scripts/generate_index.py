#!/usr/bin/env python3
"""Generate a directory listing index.html for GitHub Pages."""

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
    pre {{ font-size: 14px; line-height: 1.6; white-space: pre; overflow-x: auto; }}
    a {{ color: #64b5f6; text-decoration: none; }}
    a:hover {{ text-decoration: underline; color: #90caf9; }}
    h1 {{ color: #bb86fc; font-size: 1.4rem; margin-bottom: 0.5rem; }}
    .muted {{ color: #888; font-size: 0.85rem; }}
  </style>
</head>
<body>
  <h1>CenyPradu/</h1>
  <p class="muted">Tymczasowy directory listing — dane z TGE i taryfy dystrybucyjne</p>
<pre>
{tree}
</pre>
</body>
</html>
"""


def build_tree(directory: Path, prefix: str = "", root: Path | None = None) -> str:
    if root is None:
        root = directory

    entries = sorted(directory.iterdir(), key=lambda e: (not e.is_dir(), e.name))
    entries = [e for e in entries if e.name not in IGNORE_FILES]

    # Filter out empty directories (no real files inside)
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

    # Build tree from whitelisted entries directly
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
