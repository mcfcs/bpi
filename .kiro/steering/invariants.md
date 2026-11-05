---
inclusion: always
---

# Trust invariants (do not break)

The full list, with the tests that guard it, is "Invariants" in `AGENTS.md`. In short:

1. RLS decides what anyone sees; user queries go through `Database.as_user()`.
2. Restricted findings never reach the LLM, on any provider.
3. The LLM never supplies numbers, tiers, divergence classes or confidence.
4. Every claim is validated; failing briefs regenerate once, then failing claims are dropped.
5. Humans decide: the system never approves, grants or commissions on its own.
6. The audit log is append-only.
7. Tests use `OfflineLLM` and `HashingEmbedder`; new providers are tested with fake clients.

On AWS specifically (#[[file:docs/AWS_PLAN.md]] section 4): do not answer questions through Bedrock
Knowledge Bases or Agents — they read data with their own credentials, bypassing RLS, the divergence
classifier and the validators. Retrieval and permissions stay in Postgres.

At the end of a session, update `docs/HANDOFF.md`.
