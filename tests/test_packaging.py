import json

import pytest

from scripts.package import DOCUMENTS, OUTPUTS, submission_files


@pytest.fixture
def submission(tmp_path):
    for name in DOCUMENTS:
        (tmp_path / name).write_text("Submission documentation")
    for directory in ("linkedin_graph", "tests", "scripts"):
        (tmp_path / directory).mkdir()
        (tmp_path / directory / "included.py").write_text("# Included source")
    dataset = tmp_path / "output/real"
    (dataset / "sources").mkdir(parents=True)
    manifest = []
    for index in range(10):
        path = f"sources/person-{index}.html"
        (dataset / path).write_text(f"<h1>Person {index}</h1>")
        manifest.append({"path": path, "is_synthetic": False})
    for name in OUTPUTS:
        (dataset / name).write_text("{}")
    (dataset / "manifest.json").write_text(json.dumps(manifest))
    return tmp_path, dataset, manifest


def test_packaging_excludes_unrelated_outputs_and_private_inputs(submission):
    root, dataset, _ = submission
    unrelated = [
        dataset / "old-profiles.json",
        dataset / "sources/extra.html",
        root / "output/demo/profiles.json",
        root / "data/local/browser-export.json",
        root / "linkedin_graph/__pycache__/cached.py",
    ]
    for path in unrelated:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("PRIVATE_SENTINEL")
    files = submission_files(root)
    assert not set(files).intersection(unrelated)
    assert dataset / "interactive.html" in files
    assert len([path for path in files if path.parent == dataset / "sources"]) == 10


def test_packaging_can_rebuild_when_generated_outputs_are_missing(submission):
    root, dataset, _ = submission
    (dataset / "interactive.html").unlink()
    assert dataset / "manifest.json" in submission_files(root, include_outputs=False)
    with pytest.raises(ValueError, match="Missing or unsafe"):
        submission_files(root)


def test_packaging_rejects_sources_outside_the_snapshot_directory(submission):
    root, dataset, manifest = submission
    (root / "leak.html").write_text("PRIVATE_SENTINEL")
    manifest[0]["path"] = "../../leak.html"
    (dataset / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="inside output/real/sources"):
        submission_files(root)
