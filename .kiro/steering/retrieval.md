---
inclusion: fileMatch
fileMatchPattern: ["backend/app/retrieval.py", "backend/app/embeddings.py", "backend/app/topicality.py", "backend/app/config.py", "supabase/migrations/**", "backend/eval/**"]
---

# Retrieval changes

- Measure before and after: `cd backend && .venv/Scripts/python -m eval.retrieval_eval --provider all`
  and `-m eval.coverage_eval`. Record the table in the commit message or `docs/HANDOFF.md`.
- Off-topic false positives must stay 0.00. Tune on the `tune` half of `eval/questions.json`, report
  the `holdout` half too.
- A new embedder needs its own floors in `EMBEDDER_FLOORS` (`--sweep`, choose mid-plateau).
- Bedrock embeddings: `--provider bedrock` calls AWS (cost, data leaves the machine). Adopt only if
  they match fastembed (paraphrase recall 0.88+, F1 0.80) with zero off-topic hits.
- Never trade RLS or restricted-study handling for a better score.
