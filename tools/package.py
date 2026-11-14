"""Build dist/bot.zip for upload and prove it works the way the server runs it.

    python3.11 tools/package.py                 # build + verify (Stage 1 match)
    python3.11 tools/package.py --stage 2       # verify with a Stage 2 match
    python3.11 tools/package.py --no-verify     # build only

Steps:
 1. Collect bot/*.py (flat, bot.py at the top level of the zip, Rulebook 5.10).
 2. Lint for things the sandbox forbids (processes, sockets, file writes, stdout prints).
 3. Check the 5 MB limit.
 4. Unzip into a fresh temp dir, make it read-only, and play a full match with
    the starter engine against the starter bot. Fail on any notice or forfeit.
"""
import argparse
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOT_DIR = os.path.join(ROOT, "bot")
DIST = os.path.join(ROOT, "dist", "bot.zip")
MAX_BYTES = 5 * 1024 * 1024

FORBIDDEN = [
    (r"^\s*(import|from)\s+(subprocess|socket|multiprocessing|urllib|http|requests|asyncio)\b",
     "process/network module (Rulebook 5.4)"),
    (r"\bos\.(system|popen|fork|exec\w*|spawn\w*)\b", "starting processes (Rulebook 5.4)"),
    (r"open\([^)]*,\s*(mode\s*=\s*)?['\"][^'\"]*[wax+]", "writing files: filesystem is read-only"),
    (r"^\s*print\((?![^)]*file\s*=)", "print() to stdout outside bot.py breaks the protocol"),
]


def lint(files):
    problems = []
    for path in files:
        name = os.path.basename(path)
        with open(path, encoding="utf-8") as f:
            for no, line in enumerate(f, 1):
                for pattern, why in FORBIDDEN:
                    if re.search(pattern, line):
                        problems.append(f"{name}:{no}: {why}: {line.strip()}")
    return problems


def build():
    files = sorted(os.path.join(BOT_DIR, f) for f in os.listdir(BOT_DIR) if f.endswith(".py"))
    if "bot.py" not in {os.path.basename(f) for f in files}:
        sys.exit("bot/bot.py is missing")
    problems = lint(files)
    if problems:
        print("LINT FAILED:\n  " + "\n  ".join(problems))
        sys.exit(1)
    os.makedirs(os.path.dirname(DIST), exist_ok=True)
    with zipfile.ZipFile(DIST, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            z.write(f, arcname=os.path.basename(f))  # flat: bot.py at top level
    size = os.path.getsize(DIST)
    print(f"built {DIST}: {len(files)} files, {size / 1024:.1f} KB")
    if size > MAX_BYTES:
        sys.exit(f"zip is {size} bytes, limit is {MAX_BYTES}")


def _make_read_only(path):
    for dirpath, dirnames, filenames in os.walk(path):
        for f in filenames:
            os.chmod(os.path.join(dirpath, f), stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        os.chmod(dirpath, stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP)


def _make_writable(path):
    for dirpath, dirnames, filenames in os.walk(path):
        os.chmod(dirpath, stat.S_IRWXU)
        for f in filenames:
            os.chmod(os.path.join(dirpath, f), stat.S_IRUSR | stat.S_IWUSR)


def verify(stage, python, opponent):
    tmp = tempfile.mkdtemp(prefix="pb_verify_")
    sandbox = os.path.join(tmp, "submission")
    logs = os.path.join(tmp, "logs")
    try:
        with zipfile.ZipFile(DIST) as z:
            z.extractall(sandbox)
        _make_read_only(sandbox)
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            print("warning: running as root, so the read-only check is not enforced")
        cmd = [python, os.path.join(ROOT, "engine", "engine.py"),
               os.path.join(sandbox, "bot.py"), os.path.join(ROOT, "opponents", opponent + ".py"),
               "--stage", str(stage), "--seed", "package-check", "--log-dir", logs]
        print("verifying:", " ".join(cmd[1:3]), "... (read-only dir)")
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=600,
                             env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        print(out.stdout.strip())
        line_a = next((l for l in out.stdout.splitlines() if l.strip().startswith("A ")), "")
        ok = out.returncode == 0 and "forfeit" not in out.stdout and line_a.rstrip().endswith("notices 0")
        stderr_a = os.path.join(logs, "A_leg1_stderr.txt")
        if os.path.exists(stderr_a) and os.path.getsize(stderr_a):
            print("note: bot wrote to stderr in leg 1 (first lines):")
            with open(stderr_a, errors="replace") as f:
                print("  " + "".join(f.readlines()[:5]).strip())
        print("VERIFY OK" if ok else "VERIFY FAILED")
        return ok
    finally:
        _make_writable(tmp)
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--stage", type=int, choices=(1, 2), default=1)
    p.add_argument("--python", default=sys.executable, help="interpreter for the bots (use python3.11)")
    p.add_argument("--opponent", default="starter")
    p.add_argument("--no-verify", action="store_true")
    a = p.parse_args()
    build()
    if not a.no_verify and not verify(a.stage, a.python, a.opponent):
        sys.exit(1)


if __name__ == "__main__":
    main()
