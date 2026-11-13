"""Rebuild and package the assessment submission using an explicit file allowlist."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = ("README.md", "notes.md", "requirements.txt", "pyproject.toml", ".gitignore", "LICENSE")
OUTPUTS = (
    "manifest.json",
    "profiles.json",
    "collection_status.json",
    "graph.json",
    "graph.png",
    "interactions.json",
    "activity_graph.json",
    "activity_graph.png",
    "interactive.html",
    "report.md",
    "selection.md",
)


def submission_files(root, *, include_outputs=True):
    root = Path(root).resolve()
    dataset = root / "output" / "real"
    manifest = json.loads((dataset / "manifest.json").read_text(encoding="utf-8"))
    if len(manifest) != 10 or any(entry.get("is_synthetic") is not False for entry in manifest):
        raise ValueError("The submission requires exactly ten observed, non-synthetic profiles")
    selected = [root / name for name in DOCUMENTS]
    for directory in ("linkedin_graph", "tests", "scripts"):
        selected.extend(
            path
            for path in (root / directory).rglob("*")
            if path.is_file()
            and path.suffix in {".py", ".js", ".html", ".css"}
            and "__pycache__" not in path.parts
        )
    selected.extend(
        dataset / name
        for name in (OUTPUTS if include_outputs else ("manifest.json", "selection.md"))
    )
    for entry in manifest:
        source = dataset / entry["path"]
        if not source.resolve().is_relative_to(dataset / "sources") or source.suffix != ".html":
            raise ValueError("Source snapshots must be HTML files inside output/real/sources")
        selected.append(source)
    for path in selected:
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError(f"Missing or unsafe submission file: {path.relative_to(root)}")
    return sorted(set(selected))


def main():
    # Validate inputs before regenerating; never package unrelated output files by glob.
    submission_files(ROOT, include_outputs=False)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "linkedin_graph",
            "extract",
            "--manifest",
            "output/real/manifest.json",
            "--out",
            "output/real",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise ValueError(f"Submission regeneration failed: {result.stderr.strip()}")
    profiles = json.loads((ROOT / "output/real/profiles.json").read_text(encoding="utf-8"))
    sections = ("basic", "experience", "education", "skills", "interests", "activity")
    if len(profiles) != 10 or any(
        profile["provenance"]["is_synthetic"] or any(not profile[section] for section in sections)
        for profile in profiles
    ):
        raise ValueError("Ten observed profiles with entries in every required section are needed")
    selected = submission_files(ROOT)
    destination = ROOT / "dist" / "linkedin-profile-graph.zip"
    destination.parent.mkdir(exist_ok=True)
    with NamedTemporaryFile(dir=destination.parent, suffix=".zip", delete=False) as handle:
        temporary = Path(handle.name)
    try:
        with ZipFile(temporary, "w", compression=ZIP_DEFLATED) as archive:
            for path in selected:
                archive.write(path, "linkedin-profile-graph/" + path.relative_to(ROOT).as_posix())
        with ZipFile(temporary) as archive:
            if archive.testzip() is not None:
                raise ValueError("ZIP integrity check failed")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.with_suffix(".zip.sha256").write_text(
        f"{digest}  {destination.name}\n", encoding="utf-8"
    )
    print(f"Rebuilt data, graphs, report and interactive HTML; packaged {len(selected)} files.")
    print(f"{destination}\n{destination.stat().st_size:,} bytes\nSHA-256: {digest}")


if __name__ == "__main__":
    main()
