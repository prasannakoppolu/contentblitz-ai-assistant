"""Render the Mermaid diagrams in README.md and docs/architecture.md to SVG.

The Markdown files stay the single source of truth (GitHub renders them inline);
this produces standalone SVGs in docs/diagrams/ for slides, PDFs and reviewers
outside GitHub.

    python -m scripts.render_diagrams          # needs `mmdc` (npm i -g @mermaid-js/mermaid-cli) or npx
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {"README.md": "readme", "docs/architecture.md": "architecture"}
OUT = ROOT / "docs" / "diagrams"


def slug(text: str) -> str:
    text = re.sub(r"^[\d.]+\s*", "", text.strip())
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "diagram"


def extract(path: Path, prefix: str):
    """Yield (name, mermaid_source) using the nearest preceding heading as the name."""
    heading, seen = prefix, {}
    lines = path.read_text(encoding="utf-8").splitlines()
    i = 0
    while i < len(lines):
        m = re.match(r"^#{1,4}\s+(.*)", lines[i])
        if m:
            heading = slug(re.sub(r"[^\w\s.-]", "", m.group(1)))
        if lines[i].strip() == "```mermaid":
            block = []
            i += 1
            while i < len(lines) and lines[i].strip() != "```":
                block.append(lines[i])
                i += 1
            name = f"{prefix}-{heading}"
            seen[name] = seen.get(name, 0) + 1
            if seen[name] > 1:
                name += f"-{seen[name]}"
            yield name, "\n".join(block) + "\n"
        i += 1


def renderer() -> list:
    if shutil.which("mmdc"):
        return ["mmdc"]
    if shutil.which("npx"):
        return ["npx", "-y", "@mermaid-js/mermaid-cli@11.4.2"]
    sys.exit("Install the Mermaid CLI: npm i -g @mermaid-js/mermaid-cli")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    cmd = renderer()
    rendered, failed = [], []
    with tempfile.TemporaryDirectory() as tmp:
        for rel, prefix in SOURCES.items():
            for name, src in extract(ROOT / rel, prefix):
                mmd = Path(tmp) / f"{name}.mmd"
                mmd.write_text(src, encoding="utf-8")
                svg = OUT / f"{name}.svg"
                res = subprocess.run(cmd + ["-q", "-i", str(mmd), "-o", str(svg), "-b", "white"],
                                     capture_output=True, text=True)
                (rendered if res.returncode == 0 else failed).append(name)
                if res.returncode:
                    print(f"FAILED {name}: {res.stderr.strip()[:300]}", file=sys.stderr)
    index = ["# Diagrams", "", "Rendered from the Mermaid sources in `README.md` and `docs/architecture.md` "
             "by `make diagrams`. Edit the Markdown, then re-render.", ""]
    index += [f"- [{n}]({n}.svg)" for n in rendered]
    (OUT / "README.md").write_text("\n".join(index) + "\n", encoding="utf-8")
    print(f"Rendered {len(rendered)} diagram(s) to {OUT.relative_to(ROOT)}" + (f"; {len(failed)} failed" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
