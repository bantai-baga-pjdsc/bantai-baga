"""Run notebooks 01 to 05 in order, rebuild app/data, and compare the results with the committed version.

Needs the raw data in data/raw (see data/README.md). Run from the repository root:
    python scripts/run_pipeline.py          run the notebooks and app/build_app_data.py, then compare
    python scripts/run_pipeline.py --check  compare only, without running anything

The comparison prints PASS when every value in results/metrics.json and results/forecast_drivers.json equals the
committed value (numbers within a relative tolerance of 1e-6) and app/data holds the same copies; otherwise it
lists the values that changed and exits with an error. Without a .git folder (for example a ZIP download) there is
no committed version, so it compares the results with the app/data copies only and says so.
"""
import argparse
import json
import math
import re
import subprocess
import sys
import time
from pathlib import Path

import nbformat
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS = sorted((ROOT / "notebooks").glob("[0-9][0-9]_*.ipynb"))
COMPARED = ["results/metrics.json", "results/forecast_drivers.json"]
APP_COPIES = {"results/metrics.json": "app/data/metrics.json",
              "results/forecast_drivers.json": "app/data/forecast_drivers.json"}
REL_TOL = 1e-6
ABS_TOL = 1e-9  # plume index percentiles near zero
CELL_TIMEOUT_S = 3600


def path_pattern(path):
    """Regex for a local path written with either slash, doubled backslashes or another drive-letter case."""
    return re.compile(r"[\\/]+".join(re.escape(part.rstrip("\\/")) for part in path.parts), re.I)


LOCAL_PATHS = [(path_pattern(ROOT), "."), (path_pattern(Path.home()), "~")]


def strip_local_paths(nb):
    """Replace the repository and home folders in cell outputs, so saved notebooks hold no local paths."""
    def clean(text):
        for pattern, replacement in LOCAL_PATHS:
            text = pattern.sub(replacement, text)
        return text

    for cell in nb.cells:
        for output in cell.get("outputs", []):
            if "text" in output:
                output["text"] = clean(output["text"])
            for mime, value in output.get("data", {}).items():
                if isinstance(value, str) and not mime.startswith("image/"):
                    output["data"][mime] = clean(value)
            if "traceback" in output:
                output["traceback"] = [clean(line) for line in output["traceback"]]
                output["evalue"] = clean(output["evalue"])


def run_notebook(path):
    """Execute one notebook from the notebooks folder and save it with its outputs."""
    nb = nbformat.read(path, as_version=4)
    NotebookClient(nb, timeout=CELL_TIMEOUT_S, kernel_name="python3",
                   resources={"metadata": {"path": str(path.parent)}}).execute()
    strip_local_paths(nb)
    nbformat.write(nb, path)


def flatten(value, prefix=""):
    """Nested JSON as {"a.b.c": leaf value}."""
    if isinstance(value, dict):
        return {k: v for key, item in value.items() for k, v in flatten(item, f"{prefix}{key}.").items()}
    if isinstance(value, list):
        return {k: v for i, item in enumerate(value) for k, v in flatten(item, f"{prefix}{i}.").items()}
    return {prefix.rstrip("."): value}


def same_value(a, b):
    """Equal, with numbers compared within the tolerance."""
    numbers = (int, float)
    if isinstance(a, numbers) and isinstance(b, numbers) and not isinstance(a, bool) and not isinstance(b, bool):
        return math.isclose(a, b, rel_tol=REL_TOL, abs_tol=ABS_TOL)
    return a == b


def changed_values(old, new):
    """Lines describing every value that differs between two JSON documents."""
    old, new = flatten(old), flatten(new)
    lines = []
    for key in sorted(old.keys() | new.keys()):
        if key not in new:
            lines.append(f"  {key}: removed (was {old[key]!r})")
        elif key not in old:
            lines.append(f"  {key}: added ({new[key]!r})")
        elif not same_value(old[key], new[key]):
            lines.append(f"  {key}: {old[key]!r} -> {new[key]!r}")
    return lines


def committed_json(relative_path):
    """A JSON file as committed in git (HEAD)."""
    shown = subprocess.run(["git", "show", f"HEAD:{relative_path}"], cwd=ROOT, capture_output=True, text=True,
                           encoding="utf-8")
    if shown.returncode != 0:
        raise SystemExit(f"Cannot read the committed {relative_path} from git: {shown.stderr.strip()}")
    return json.loads(shown.stdout)


def compare():
    """Compare the results with the committed version and the app copies; True when nothing changed."""
    passed = True
    has_git = (ROOT / ".git").exists()
    if not has_git:
        print("skipped: no .git folder, so the results are compared with the app/data copies only")
    for relative_path in COMPARED:
        current = json.loads((ROOT / relative_path).read_text(encoding="utf-8"))
        checks = [(APP_COPIES[relative_path], json.loads((ROOT / APP_COPIES[relative_path]).read_text(
            encoding="utf-8")))]
        if has_git:
            checks.insert(0, ("committed version", committed_json(relative_path)))
        for label, reference in checks:
            lines = changed_values(reference, current)
            if lines:
                passed = False
                print(f"CHANGED: {relative_path} differs from {label}:")
                print("\n".join(lines))
            else:
                print(f"same: {relative_path} and {label} ({len(flatten(current))} values)")
    return passed


def main():
    """Run the notebooks and the app data build (unless --check), then compare the results."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="only compare the results, without running anything")
    args = parser.parse_args()

    if not args.check:
        start = time.perf_counter()
        for path in NOTEBOOKS:
            notebook_start = time.perf_counter()
            run_notebook(path)
            print(f"{path.name}: {time.perf_counter() - notebook_start:.0f} s")
        build = subprocess.run([sys.executable, "app/build_app_data.py"], cwd=ROOT, capture_output=True, text=True,
                               encoding="utf-8")
        if build.returncode != 0:
            print(build.stdout + build.stderr)
            raise SystemExit("app/build_app_data.py failed")
        print(f"app/data rebuilt, {build.stdout.strip().splitlines()[-1]}")
        print(f"pipeline: {(time.perf_counter() - start) / 60:.1f} min")

    if not compare():
        raise SystemExit("FAIL: results differ from the committed version")
    print("PASS")


if __name__ == "__main__":
    main()
