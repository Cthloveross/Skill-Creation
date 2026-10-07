"""Fixed subject definitions and keyword-weighted scoring.

These defaults match the current task family (LLM, trapped ion & quantum
computing, black hole, DNA, music history). The last entry is the fallback.
They are tunable; callers may override by passing their own subject spec.
"""
import re

# Order matters: the fallback must be LAST so it never wins a non-zero tie.
# Each subject: label -> list of (pattern, weight). Phrases are matched as
# case-insensitive substrings; single short tokens use word boundaries.
DEFAULT_SUBJECTS = [
    ("LLM", [
        ("large language model", 5), ("language model", 3), ("transformer", 3),
        ("attention mechanism", 3), ("self-attention", 3), ("gpt", 3),
        ("bert", 3), ("llm", 4), ("fine-tuning", 2), ("fine tuning", 2),
        ("pretrain", 2), ("pre-train", 2), ("natural language processing", 3),
        ("nlp", 2), ("prompt", 2), ("token", 1), ("instruction tuning", 3),
        ("neural network", 1), ("embedding", 1), ("text generation", 2),
    ]),
    ("trapped_ion_and_qc", [
        ("trapped ion", 5), ("trapped-ion", 5), ("ion trap", 4),
        ("qubit", 4), ("quantum computing", 4), ("quantum computer", 4),
        ("quantum gate", 3), ("entanglement", 3), ("quantum circuit", 3),
        ("coherence time", 2), ("quantum error correction", 3),
        ("superconducting qubit", 3), ("paul trap", 3), ("laser cooling", 2),
        ("quantum algorithm", 2), ("quantum state", 1), ("decoherence", 2),
        ("hyperfine", 2),
    ]),
    ("black_hole", [
        ("black hole", 5), ("event horizon", 4), ("schwarzschild", 4),
        ("hawking radiation", 4), ("hawking", 2), ("accretion disk", 3),
        ("accretion", 2), ("gravitational wave", 3), ("general relativity", 3),
        ("spacetime", 2), ("singularity", 2), ("kerr metric", 3),
        ("supermassive", 2), ("neutron star", 2), ("gravitational collapse", 3),
        ("photon sphere", 3),
    ]),
    ("DNA", [
        ("dna", 4), ("genome", 4), ("nucleotide", 4), ("rna", 3),
        ("gene expression", 3), ("chromosome", 3), ("sequencing", 2),
        ("base pair", 3), ("double helix", 4), ("molecular biology", 3),
        ("transcription factor", 3), ("genetic", 2), ("nucleic acid", 4),
        ("protein synthesis", 3), ("mutation", 1), ("polymerase", 3),
        ("crispr", 4), ("genomic", 2),
    ]),
    # Fallback subject (also a real category). Keep it last.
    ("music_history", [
        ("music history", 5), ("composer", 3), ("symphony", 3),
        ("baroque", 3), ("classical period", 3), ("opera", 3),
        ("mozart", 3), ("beethoven", 3), ("bach", 3), ("renaissance music", 3),
        ("orchestra", 2), ("concerto", 3), ("melody", 2), ("harmony", 1),
        ("musical", 2), ("sonata", 3), ("romantic era", 2), ("chord", 1),
        ("instrumentation", 1),
    ]),
]


def _compile(subjects):
    compiled = []
    for label, kws in subjects:
        items = []
        for pat, w in kws:
            p = pat.lower().strip()
            if " " in p or "-" in p or len(p) > 4:
                rx = re.compile(re.escape(p))
            else:
                rx = re.compile(r"\b" + re.escape(p) + r"\b")
            items.append((rx, w))
        compiled.append((label, items))
    return compiled


def score_text(text, subjects=None):
    """Return (best_label, scores_dict). Fallback is the last subject label.
    If every score is zero, return the fallback label.
    On a tie, earlier (non-fallback) subjects win because the fallback is last
    and only chosen as the argmax when strictly greater or when all are zero.
    """
    if subjects is None:
        subjects = DEFAULT_SUBJECTS
    compiled = _compile(subjects)
    low = (text or "").lower()
    scores = {}
    for label, items in compiled:
        s = 0
        for rx, w in items:
            s += w * len(rx.findall(low))
        scores[label] = s
    fallback = subjects[-1][0]
    best_label = fallback
    best_score = -1
    # iterate in order; strict > keeps earliest winner on ties
    for label, _ in subjects:
        if scores[label] > best_score:
            best_score = scores[label]
            best_label = label
    if best_score <= 0:
        best_label = fallback
    return best_label, scores
