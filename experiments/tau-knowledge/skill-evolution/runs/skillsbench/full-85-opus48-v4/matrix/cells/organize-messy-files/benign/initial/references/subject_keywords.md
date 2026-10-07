# Subject keyword reference

The runtime scoring lives in `scripts/subjects.py` (`DEFAULT_SUBJECTS`). This
file documents the intent and is a place to record tuning decisions. Edit the
Python module to change behaviour; keep this note in sync.

Subjects are evaluated in order; the **last** subject is the fallback and only
wins when it is the strict argmax or when every score is zero. For the current
task, `music_history` is both a real subject and the fallback.

## Discriminative cues per subject

- **LLM**: large language model, transformer, attention, GPT/BERT, fine-tuning,
  NLP, prompt, token, pretraining, text generation.
- **trapped_ion_and_qc**: trapped ion / ion trap, qubit, quantum computing,
  quantum gate, entanglement, quantum circuit, coherence time, Paul trap, laser
  cooling, quantum error correction, decoherence, hyperfine.
- **black_hole**: black hole, event horizon, Schwarzschild, Hawking radiation,
  accretion disk, gravitational wave, general relativity, spacetime,
  singularity, Kerr metric, photon sphere.
- **DNA**: DNA, genome, nucleotide, RNA, gene expression, chromosome,
  sequencing, base pair, double helix, molecular biology, CRISPR, polymerase.
- **music_history** (fallback): music history, composer, symphony, Baroque,
  classical period, opera, Mozart/Beethoven/Bach, concerto, sonata, orchestra.

## Tuning guidance

- Prefer multi-word phrases with higher weights; they are far less ambiguous
  than single tokens (e.g. "quantum computing" vs. the bare word "quantum").
- If a spot check (`dry_run`) shows a cluster of files misrouted to the
  fallback, add the missing discriminative phrases for the correct subject
  rather than lowering the fallback — the fallback must stay the "fits nothing
  else" bucket.
- Watch for cross-domain overlap: "quantum" appears in both physics subjects;
  "model"/"network" appear broadly. Weight the specific phrases, not the generic
  words.
- Re-run `organize.py` with `"dry_run": true` after any change and inspect
  `counts` and a sample of `moved` entries before performing the real move.
