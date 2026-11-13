"""Import sanitized DOM snapshots exported from an ordinary browser session."""

from pathlib import Path

from .cli import extract_manifest
from .common import dump_json, load_json, profile_url
from .extract import sanitize_html


def import_session(input_path, output_dir):
    data = load_json(input_path)
    if not isinstance(data, dict):
        raise ValueError("Browser export must be a JSON object")
    captures = data.get("captures", [data])
    out = Path(output_dir)
    (out / "sources").mkdir(parents=True, exist_ok=True)
    manifest, failed = [], []
    for capture in captures:
        url = profile_url(capture["url"])
        if capture.get("final_url") and profile_url(capture["final_url"]) != url:
            raise ValueError("Captured URL does not match the requested profile")
        if capture.get("status", "saved") != "saved":
            failed.append(
                {"url": url, "status": "failed", "reason": capture.get("error", "capture_failed")}
            )
            continue
        slug = url.rsplit("/", 1)[-1]
        path = f"sources/{slug}.html"
        (out / path).write_text(sanitize_html(capture["html"]), encoding="utf-8")
        manifest.append(
            {
                "url": url,
                "path": path,
                "is_synthetic": False,
                "source_kind": "existing_chrome_dom",
                "collected_at": capture.get("collected_at"),
            }
        )
    dump_json(out / "manifest.json", manifest)
    if not manifest:
        dump_json(out / "profiles.json", [])
        receipt = {
            "requested": data.get("requested", len(captures)),
            "saved": 0,
            "acquisition_complete": False,
            "profile_completeness_established": False,
            "results": failed,
        }
    else:
        profiles, receipt = extract_manifest(out / "manifest.json", out)
        receipt["requested"] = data.get("requested", len(captures))
        receipt["results"].extend(failed)
        receipt["acquisition_complete"] = receipt["saved"] == receipt["requested"]
        dump_json(out / "collection_status.json", receipt)
        return profiles, receipt
    dump_json(out / "collection_status.json", receipt)
    return [], receipt
