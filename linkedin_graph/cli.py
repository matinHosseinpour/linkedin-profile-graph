"""CLI: demo, extract, collect and analyze."""

import argparse
import json
import sys
from pathlib import Path

from .analyze import analyze
from .collect import collect_profiles
from .common import dump_json, load_json, profile_url, utc_now
from .demo import write_demo
from .extract import extract_profile


def extract_manifest(manifest_path, output_dir):
    manifest_path = Path(manifest_path).resolve()
    entries = load_json(manifest_path)
    if not isinstance(entries, list) or not entries:
        raise ValueError("Manifest must be a nonempty JSON array")
    profiles, results, seen = [], [], set()
    for entry in entries:
        url = profile_url(entry["url"])
        if url in seen:
            raise ValueError("Duplicate manifest URL; use one combined HTML snapshot per profile")
        seen.add(url)
        path = (manifest_path.parent / entry["path"]).resolve()
        if not path.is_relative_to(manifest_path.parent):
            raise ValueError("HTML paths must stay inside the manifest directory")
        synthetic = entry.get("is_synthetic", False)
        if not isinstance(synthetic, bool):
            raise ValueError("is_synthetic must be a JSON boolean")
        try:
            # Preserve source bytes, including CR line endings, for the provenance hash.
            html = path.read_bytes().decode("utf-8")
            profile = extract_profile(
                html,
                url,
                source_kind=entry.get("source_kind", "saved_html"),
                is_synthetic=synthetic,
                collected_at=entry.get("collected_at"),
            )
            profiles.append(profile)
            results.append({"url": url, "status": "saved", "path": entry["path"]})
        except (OSError, ValueError) as error:
            reason = str(error) if isinstance(error, ValueError) else "input_file_unreadable"
            results.append({"url": url, "status": "failed", "reason": reason})
    receipt = {
        "generated_at": utc_now(),
        "requested": len(entries),
        "saved": len(profiles),
        "acquisition_complete": len(profiles) == len(entries),
        "profile_completeness_established": False,
        "results": results,
    }
    out = Path(output_dir)
    dump_json(out / "profiles.json", profiles)
    dump_json(out / "collection_status.json", receipt)
    return profiles, receipt


def parser():
    root = argparse.ArgumentParser(description="Public profile extraction and skill graph analysis")
    commands = root.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo", help="Generate and extract ten fictional HTML fixtures")
    demo.add_argument("--out", type=Path, default=Path("output/demo"))
    extract = commands.add_parser("extract", help="Extract locally saved visible profile HTML")
    extract.add_argument("--manifest", type=Path, required=True)
    extract.add_argument("--out", type=Path, default=Path("output/live"))
    collect = commands.add_parser("collect", help="Fetch allowed guest public pages sequentially")
    collect.add_argument("--urls", type=Path, required=True, help="One HTTPS profile URL per line")
    collect.add_argument("--interval", type=float, default=5)
    collect.add_argument("--out", type=Path, default=Path("output/live"))
    session = commands.add_parser("import-session", help="Import rendered browser DOM exports")
    session.add_argument("--input", type=Path, required=True)
    session.add_argument("--out", type=Path, default=Path("output/real"))
    analysis = commands.add_parser("analyze", help="Analyze an existing profiles.json")
    analysis.add_argument("--input", type=Path, required=True)
    analysis.add_argument("--out", type=Path, default=Path("output/live"))
    for command in (demo, extract, collect, session, analysis):
        command.add_argument("--organization", help="Exact normalized current employer name")
        command.add_argument(
            "--threshold",
            type=float,
            default=0.25,
            help="Jaccard threshold in (0, 1], default 0.25",
        )
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if not 0 < args.threshold <= 1:
            raise ValueError("The Jaccard threshold must be in (0, 1]")
        receipt = None
        if args.command == "demo":
            manifest = write_demo(args.out)
            profiles, receipt = extract_manifest(manifest, args.out)
        elif args.command == "extract":
            profiles, receipt = extract_manifest(args.manifest, args.out)
        elif args.command == "collect":
            urls = [
                line.strip()
                for line in args.urls.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.lstrip().startswith("#")
            ]
            if any("/in/fictional-fixture-" in url for url in urls):
                raise ValueError("Fictional demo URLs must never be fetched; use the demo command")
            profiles, receipt = collect_profiles(urls, args.out, interval=args.interval)
        elif args.command == "import-session":
            from .session import import_session

            profiles, receipt = import_session(args.input, args.out)
        else:
            profiles = load_json(args.input)
            if not isinstance(profiles, list):
                raise ValueError("profiles.json must be a JSON array")
        artifact = analyze(
            profiles, args.out, organization=args.organization, threshold=args.threshold
        )
        print(
            json.dumps(
                {"output": str(args.out.resolve()), **artifact["metadata"]},
                ensure_ascii=False,
                indent=2,
            )
        )
        # Useful partial artifacts are retained, but acquisition failure is machine-readable.
        if receipt and not receipt["acquisition_complete"]:
            print("Collection is partial or blocked; see collection_status.json", file=sys.stderr)
            return 2
        if not artifact["nodes"]:
            print("No profiles matched the analysis cohort", file=sys.stderr)
            return 2
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
