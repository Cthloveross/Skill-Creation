"""Classify a document into a fixed subject.

stdin JSON:
  {"text": "..."}                       # classify given text, OR
  {"path": "/abs/file", "max_chars": N}  # extract then classify
  optional: {"subjects": [[label,[[pat,w],...]],...], "fallback": "..."}
stdout JSON:
  {"label": "...", "scores": {...}, "method": "..."}

If no keyword evidence is found, the fallback (last subject) is returned.
"""
import sys, json, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import subjects as subjmod
import extract_text


def classify(req):
    subs = req.get("subjects") or subjmod.DEFAULT_SUBJECTS
    # normalize tuples (JSON gives lists)
    subs = [(s[0], [tuple(k) for k in s[1]]) for s in subs]
    method = "text"
    if "text" in req and req["text"] is not None:
        text = req["text"]
    else:
        ext = extract_text.extract(req["path"], int(req.get("max_chars", 60000)))
        text = ext["text"]
        method = ext["method"]
    label, scores = subjmod.score_text(text, subs)
    return {"label": label, "scores": scores, "method": method}


def main():
    req = json.load(sys.stdin)
    json.dump(classify(req), sys.stdout)


if __name__ == "__main__":
    main()
