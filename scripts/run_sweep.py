"""One command for the main experiment: every policy x k on one suite, then a results table.

    python scripts/run_sweep.py                 # run what is missing (3 runs at a time), then summarise
    python scripts/run_sweep.py --dry-run       # only print the commands
    python scripts/run_sweep.py --summary-only  # skip running; just rebuild the table from data/results/runs/

Needs OPENROUTER_API_KEY (or OPENAI_API_KEY) in the environment. Each run calls the model and costs money.
A configuration whose results already exist is skipped unless --force is given.
"""
import _paths  # noqa: F401  (sets up imports; see project_paths.py)

import argparse
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from summarize_runs import summarise

KS = [0, 1, 2, 3, 5]


def finished(runs_dir, t):
    """A run counts as done only if run_real.py got to the end (it prints a 'task completed' line)."""
    log = runs_dir / f"{t}.log"
    return log.exists() and "task completed (utility)" in log.read_text(encoding="utf-8", errors="replace")


def configs(suite, prompt_version):
    yield dict(policy="full_approve", k=0)                       # no escalations, so k does not matter
    for k in KS:
        yield dict(policy="full_escalate", k=k)
    for k in KS:
        yield dict(policy="rules_semantic", k=k, prompt_version=prompt_version)


def tag(c, suite, attack, reviewer, run_id):
    pv = f"_{c['prompt_version']}" if c.get("prompt_version") else ""
    return f"{suite}_{attack}_{c['policy']}{pv}_{reviewer}_k{c['k']}_run{run_id}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", default="banking")
    ap.add_argument("--attack", default="important_instructions")
    ap.add_argument("--prompt-version", default="V1")
    ap.add_argument("--reviewer", default="simulated")
    ap.add_argument("--run-id", type=int, default=0)
    ap.add_argument("--parallel", type=int, default=3, help="runs at the same time (keep small to avoid rate limits)")
    ap.add_argument("--force", action="store_true", help="re-run configurations that already have results")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--summary-only", action="store_true")
    a = ap.parse_args()

    runs_dir = _paths.RESULTS_DIR / "runs"
    todo = []
    for c in configs(a.suite, a.prompt_version):
        t = tag(c, a.suite, a.attack, a.reviewer, a.run_id)
        done = finished(runs_dir, t)
        cmd = [sys.executable, str(_paths.ROOT / "scripts" / "run_real.py"), "--policy", c["policy"], "--k", str(c["k"]),
               "--suite", a.suite, "--attack", a.attack, "--reviewer", a.reviewer, "--run-id", str(a.run_id)]
        if c.get("prompt_version"):
            cmd += ["--prompt-version", c["prompt_version"]]
        status = "skip (already done)" if done and not a.force else "run"
        print(f"{status:20s} {t}")
        if status == "run":
            todo.append((t, cmd))

    if a.summary_only or a.dry_run:
        if a.dry_run:
            for t, cmd in todo:
                print("  " + " ".join(cmd))
        if a.summary_only:
            summarise(runs_dir)
        return

    if todo and not (os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")):
        sys.exit("Set OPENROUTER_API_KEY first (PowerShell: $env:OPENROUTER_API_KEY=\"sk-or-...\").")

    runs_dir.mkdir(parents=True, exist_ok=True)

    def run_one(t, cmd, tries=3):
        start = time.time()
        for attempt in range(1, tries + 1):          # network errors stop a whole run, so retry it
            with open(runs_dir / f"{t}.log", "w", encoding="utf-8") as log:
                rc = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, cwd=_paths.ROOT).returncode
            if rc == 0 or attempt == tries:
                break
            print(f"retry  {t}  (attempt {attempt} failed; waiting 60 s, see its .log)")
            time.sleep(60)
        return t, rc, time.time() - start

    print(f"\nStarting {len(todo)} runs, {a.parallel} at a time. Progress is written to data/results/runs/<run>.log\n")
    failed = []
    with ThreadPoolExecutor(max_workers=a.parallel) as pool:
        for fut in as_completed([pool.submit(run_one, t, c) for t, c in todo]):
            t, rc, secs = fut.result()
            print(f"{'done  ' if rc == 0 else 'FAILED'} {t}  ({secs / 60:.1f} min)")
            if rc != 0:
                failed.append(t)
    if failed:
        print("\nFailed runs (see their .log files; re-run this script to retry only these):")
        for t in failed:
            print("  " + t)
    summarise(runs_dir)


if __name__ == "__main__":
    main()
