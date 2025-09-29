#!/usr/bin/env python3
import argparse
import os
import re
import shutil
import sys
import textwrap
from datetime import datetime
from pathlib import Path

BUNDLE_DEFAULT_NAME = "hunter_feedback_bundle"

def find_latest_results(root: Path) -> Path | None:
    base = root / "results"
    if not base.exists():
        return None
    # Match directories like hunter-YYYYmmdd-HHMMSS
    pattern = re.compile(r"^hunter-\d{8}-\d{6}$")
    candidates = [p for p in base.iterdir() if p.is_dir() and pattern.match(p.name)]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)

def read_cmds(results_root: Path) -> list[tuple[Path, str]]:
    cmds: list[tuple[Path,str]] = []
    for cmd_path in results_root.glob("**/cmd.txt"):
        try:
            cmds.append((cmd_path.relative_to(results_root), cmd_path.read_text(encoding="utf-8", errors="ignore").strip()))
        except Exception:
            continue
    return cmds

def copy_if_exists(src: Path, dst: Path) -> bool:
    if src.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return True
    return False

def collect_runs(results_root: Path, bundle_root: Path, include_logs: bool) -> dict:
    stats = {"runs": 0, "summaries": 0, "logs": 0, "opponents": set(), "seeds": set()}
    # Expect structure: results_root/<opponent>/seed-<n>/(A|B)/{summary.json,stdout.log}
    for opp_dir in sorted([p for p in results_root.iterdir() if p.is_dir()]):
        opponent = opp_dir.name
        stats["opponents"].add(opponent)
        for seed_dir in sorted([p for p in opp_dir.iterdir() if p.is_dir()]):
            stats["seeds"].add(seed_dir.name)
            for side in ("A","B"):
                run_dir = seed_dir / side
                if not run_dir.exists():
                    continue
                dst_dir = bundle_root / "results" / opponent / seed_dir.name / side
                sum_ok = copy_if_exists(run_dir / "summary.json", dst_dir / "summary.json")
                log_ok = False
                if include_logs:
                    log_ok = copy_if_exists(run_dir / "stdout.log", dst_dir / "stdout.log")
                if sum_ok or log_ok:
                    stats["runs"] += 1
                    stats["summaries"] += int(sum_ok)
                    stats["logs"] += int(log_ok)
    # Convert sets to sorted lists for later reporting
    stats["opponents"] = sorted(stats["opponents"])
    stats["seeds"] = sorted(stats["seeds"])
    return stats

def write_readme(bundle_root: Path, results_root: Path, stats: dict, name: str, include_logs: bool):
    readme = bundle_root / "README.txt"
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    text = f"""\
    BATTLE — Hunter Feedback Bundle
    Name: {name}
    Created: {ts}
    Source results: {results_root}

    Contents:
      - configs/run_notes.txt           # aggregated command lines used
      - results/<opponent>/seed-*/A|B/  # summary.json (+ stdout.log if included)
      - summary/summary.csv             # if present in results root
      - summary/leaderboard.txt         # if present in results root

    Stats:
      Opponents: {', '.join(stats.get('opponents', [])) or 'NA'}
      Seeds: {', '.join(stats.get('seeds', [])) or 'NA'}
      Runs captured: {stats.get('runs', 0)}
      Summaries: {stats.get('summaries', 0)}
      Logs included: {'yes' if include_logs else 'no'} (count={stats.get('logs', 0)})

    How to generate more data:
      - Use test_hunter.sh (set PARALLEL_JOBS for speed)
      - Ensure --record is on so summary.json is emitted
      - Re-run this collector to refresh the bundle

    How to share:
      - Send the ZIP (or .tar.gz) of this folder.
    """.rstrip() + "\n"
    readme.parent.mkdir(parents=True, exist_ok=True)
    readme.write_text(text, encoding="utf-8")

def aggregate_run_notes(bundle_root: Path, results_root: Path):
    out = bundle_root / "configs" / "run_notes.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    cmds = read_cmds(results_root)
    if not cmds:
        out.write_text("# No cmd.txt files found under results root.\n", encoding="utf-8")
        return
    with out.open("w", encoding="utf-8") as fh:
        fh.write("# Aggregated command lines from cmd.txt files\n\n")
        for rel_path, cmd in sorted(cmds, key=lambda x: str(x[0])):
            fh.write(f"[{rel_path}]\n{cmd}\n\n")

def copy_summaries(bundle_root: Path, results_root: Path):
    # Copy summary.csv and leaderboard.txt if present
    summary_dir = bundle_root / "summary"
    summary_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    for fname in ("summary.csv", "leaderboard.txt"):
        src = results_root / fname
        if src.exists():
            shutil.copy2(src, summary_dir / fname)
            copied += 1
    return copied

def compress_bundle(bundle_root: Path, make_tgz: bool) -> tuple[Path, Path | None]:
    zip_path = bundle_root.with_suffix(".zip")
    # shutil.make_archive expects base_name without suffix and a format
    base_name = str(bundle_root)
    shutil.make_archive(base_name, "zip", root_dir=bundle_root.parent, base_dir=bundle_root.name)
    tgz_path = None
    if make_tgz:
        shutil.make_archive(base_name, "gztar", root_dir=bundle_root.parent, base_dir=bundle_root.name)
        tgz_path = bundle_root.with_suffix(".tar.gz")
    return zip_path, tgz_path

def main():
    ap = argparse.ArgumentParser(description="Collect BATTLE hunter test artifacts into a sharable bundle.")
    ap.add_argument("--results-root", type=Path, default=None,
                    help="Path to a results directory (e.g., results/hunter-YYYYmmdd-HHMMSS). If omitted, auto-detect newest under ./results.")
    ap.add_argument("--name", type=str, default=BUNDLE_DEFAULT_NAME, help="Bundle folder name (default: hunter_feedback_bundle).")
    ap.add_argument("--include-logs", dest="include_logs", action="store_true", default=True, help="Include stdout.log files (default).")
    ap.add_argument("--no-logs", dest="include_logs", action="store_false", help="Exclude stdout.log files.")
    ap.add_argument("--tgz", action="store_true", help="Also create a .tar.gz in addition to .zip.")
    args = ap.parse_args()

    cwd = Path.cwd()
    # Resolve results root
    results_root = args.results_root
    if results_root is None:
        latest = find_latest_results(cwd)
        if latest is None:
            print("No results found under ./results. Provide --results-root.", file=sys.stderr)
            return 2
        results_root = latest
    else:
        if not results_root.exists():
            print(f"results-root not found: {results_root}", file=sys.stderr)
            return 2
        # Accept passing the parent (e.g., ./results) and still try to pick latest child
        if results_root.name == "results":
            auto = find_latest_results(results_root.parent)
            if auto:
                results_root = auto

    bundle_root = cwd / args.name
    if bundle_root.exists():
        print(f"Removing existing bundle dir: {bundle_root}")
        shutil.rmtree(bundle_root)

    # Create structure and collect
    stats = collect_runs(results_root, bundle_root, include_logs=args.include_logs)
    aggregate_run_notes(bundle_root, results_root)
    copy_summaries(bundle_root, results_root)
    write_readme(bundle_root, results_root, stats, args.name, args.include_logs)

    zip_path, tgz_path = compress_bundle(bundle_root, make_tgz=args.tgz)
    print(f"Bundle directory: {bundle_root}")
    print(f"ZIP created: {zip_path}")
    if tgz_path:
        print(f"TGZ created: {tgz_path}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
