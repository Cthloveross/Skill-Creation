"""End-to-end: discover -> extract -> classify -> move -> reconcile.

stdin JSON (all optional):
  {
    "source_dir": "/root/papers/all",
    "dest_root": "/root/papers",
    "subjects": null,
    "fallback": "music_history",
    "run_download": false,
    "download_script": "/tmp/download_papers.sh",
    "dry_run": false,
    "max_chars": 60000
  }
stdout JSON: summary (see SKILL.md).

Moves preserve filename and bytes (shutil.move). Destination folders are the
subject labels under dest_root. Files already inside a destination folder are
skipped from discovery. Never overwrites: a name collision is reported, not
resolved by renaming (the task forbids renaming).
"""
import sys, os, json, shutil, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import subjects as subjmod
import extract_text


def _subject_labels(subs):
    return [s[0] for s in subs]


def run(req):
    source_dir = req.get("source_dir", "/root/papers/all")
    dest_root = req.get("dest_root", os.path.dirname(source_dir.rstrip("/")) or "/root/papers")
    subs = req.get("subjects") or subjmod.DEFAULT_SUBJECTS
    subs = [(s[0], [tuple(k) for k in s[1]]) for s in subs]
    fallback = req.get("fallback") or subs[-1][0]
    labels = _subject_labels(subs)
    dest_dirs = {lab: os.path.join(dest_root, lab) for lab in labels}
    dry_run = bool(req.get("dry_run", False))
    max_chars = int(req.get("max_chars", 60000))

    if req.get("run_download"):
        script = req.get("download_script", "/tmp/download_papers.sh")
        if os.path.exists(script):
            try:
                subprocess.run(["bash", script], check=False, timeout=550)
            except Exception:
                pass

    # Discover source files, skipping destination folders and hidden/system files.
    dest_abs = {os.path.abspath(p) for p in dest_dirs.values()}
    files = []
    for rootd, dirs, fnames in os.walk(source_dir):
        # don't descend into destination folders if nested under source
        dirs[:] = [d for d in dirs if os.path.abspath(os.path.join(rootd, d)) not in dest_abs]
        for fn in fnames:
            fp = os.path.join(rootd, fn)
            if os.path.abspath(os.path.dirname(fp)) in dest_abs:
                continue
            if fn.startswith("."):
                continue
            files.append(fp)

    if not dry_run:
        for d in dest_dirs.values():
            os.makedirs(d, exist_ok=True)

    moved, unreadable, collisions, leftover = [], [], [], []
    counts = {lab: 0 for lab in labels}

    for fp in files:
        try:
            ext = extract_text.extract(fp, max_chars)
        except Exception:
            ext = {"text": "", "method": "error", "ok": False}
        if not ext["ok"]:
            unreadable.append(os.path.basename(fp))
        label, _scores = subjmod.score_text(ext["text"], subs)
        if label not in dest_dirs:
            label = fallback
        name = os.path.basename(fp)
        target = os.path.join(dest_dirs[label], name)
        if dry_run:
            counts[label] += 1
            moved.append({"name": name, "label": label, "method": ext["method"]})
            continue
        if os.path.abspath(fp) == os.path.abspath(target):
            counts[label] += 1
            continue
        if os.path.exists(target):
            collisions.append(name)
            leftover.append(fp)
            continue
        try:
            shutil.move(fp, target)
            counts[label] += 1
            moved.append({"name": name, "label": label, "method": ext["method"]})
        except Exception as e:
            leftover.append("%s (%s)" % (fp, e))

    ok = (len(leftover) == 0)
    return {
        "source_dir": source_dir,
        "dest_root": dest_root,
        "total_source": len(files),
        "counts": counts,
        "moved": moved,
        "unreadable": unreadable,
        "collisions": collisions,
        "leftover": leftover,
        "dry_run": dry_run,
        "ok": ok,
    }


def main():
    try:
        req = json.load(sys.stdin)
    except Exception:
        req = {}
    json.dump(run(req), sys.stdout)


if __name__ == "__main__":
    main()
