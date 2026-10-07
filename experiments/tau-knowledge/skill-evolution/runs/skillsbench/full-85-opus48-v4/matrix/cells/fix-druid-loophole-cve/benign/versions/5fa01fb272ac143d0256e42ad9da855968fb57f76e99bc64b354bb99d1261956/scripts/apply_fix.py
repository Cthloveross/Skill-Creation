#!/usr/bin/env python3
"""Apply the CVE-2021-25646 root-cause fix to Druid's GuiceAnnotationIntrospector
and emit a unified-diff patch file.

Stdin  (JSON, all optional):
  {
    "druid_root":  "/root/druid",        # git source tree
    "patches_dir": "/root/patches",      # where to write the .patch
    "patch_name":  "cve-2021-25646-guice-injectable-useinput.patch"
  }

Stdout (JSON):
  {
    "status": "patched" | "already_patched" | "error",
    "file": "<abs path of edited java file>",
    "rel_path": "<path relative to druid_root>",
    "patch_path": "<abs path of written patch, if any>",
    "message": "..."
  }

The inserted method uses fully-qualified Jackson type names so no imports need to
change. It overrides AnnotationIntrospector.findInjectableValue so the returned
JacksonInject.Value carries useInput=false, meaning JSON input (including the
empty-string "" key) can never replace a @JacksonInject value. This closes the
vulnerability for every deserialized JavaScript-config-consuming class at once.
"""
import glob
import json
import os
import subprocess
import sys


METHOD = """
  /**
   * Security fix for CVE-2021-25646. Override findInjectableValue so that the returned
   * JacksonInject.Value has useInput=false. This prevents request-supplied JSON
   * (e.g. the empty-string \"\" key carrying {\"enabled\": true}) from replacing a
   * value that is supposed to come only from the trusted Guice injection context,
   * such as JavaScriptConfig. Covers every @JacksonInject consumer on every API path.
   */
  @Override
  public com.fasterxml.jackson.annotation.JacksonInject.Value findInjectableValue(
      com.fasterxml.jackson.databind.introspect.AnnotatedMember m)
  {
    if (m.getAnnotation(com.fasterxml.jackson.annotation.JacksonInject.class) == null) {
      return null;
    }
    Object id = findInjectableValueId(m);
    if (id == null) {
      return null;
    }
    return com.fasterxml.jackson.annotation.JacksonInject.Value.forId(id).withUseInput(false);
  }
"""


def out(d):
    sys.stdout.write(json.dumps(d))
    sys.exit(0 if d.get("status") != "error" else 1)


def main():
    try:
        raw = sys.stdin.read().strip()
        cfg = json.loads(raw) if raw else {}
    except Exception:
        cfg = {}

    root = cfg.get("druid_root", "/root/druid")
    patches_dir = cfg.get("patches_dir", "/root/patches")
    patch_name = cfg.get("patch_name", "cve-2021-25646-guice-injectable-useinput.patch")

    if not os.path.isdir(root):
        out({"status": "error", "message": "druid_root not found: %s" % root})

    matches = glob.glob(os.path.join(root, "**", "GuiceAnnotationIntrospector.java"),
                        recursive=True)
    if not matches:
        out({"status": "error",
             "message": "GuiceAnnotationIntrospector.java not found under %s; inspect tree manually" % root})
    target = sorted(matches, key=len)[0]
    rel = os.path.relpath(target, root)

    with open(target, "r", encoding="utf-8") as f:
        text = f.read()

    if "findInjectableValue(" in text and "withUseInput" in text:
        out({"status": "already_patched", "file": target, "rel_path": rel,
             "patch_path": "", "message": "override already present"})

    if "findInjectableValueId" not in text:
        out({"status": "error", "file": target, "rel_path": rel,
             "message": "findInjectableValueId not found; this Druid version differs "
                        "from 0.20.0 \u2014 inspect and adapt the fix manually"})

    idx = text.rfind("}")
    if idx == -1:
        out({"status": "error", "file": target, "rel_path": rel,
             "message": "could not find closing brace to insert method"})

    # Insert the override just before the class's final closing brace.
    new_text = text[:idx].rstrip("\n") + "\n" + METHOD + "}" + text[idx + 1:]
    with open(target, "w", encoding="utf-8") as f:
        f.write(new_text)

    os.makedirs(patches_dir, exist_ok=True)
    patch_path = os.path.join(patches_dir, patch_name)
    try:
        diff = subprocess.run(["git", "-C", root, "--no-pager", "diff", "--", rel],
                              capture_output=True, text=True, check=True).stdout
    except Exception as e:
        out({"status": "error", "file": target, "rel_path": rel,
             "message": "edited file but git diff failed: %s" % e})

    if not diff.strip():
        out({"status": "error", "file": target, "rel_path": rel,
             "message": "git diff empty; is %s a git repo?" % root})

    with open(patch_path, "w", encoding="utf-8") as f:
        f.write(diff)

    out({"status": "patched", "file": target, "rel_path": rel,
         "patch_path": patch_path,
         "message": "inserted findInjectableValue override (useInput=false) and wrote patch"})


if __name__ == "__main__":
    main()
