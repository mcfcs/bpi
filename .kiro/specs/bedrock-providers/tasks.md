# Tasks: Bedrock providers

- [x] 1. Add `provider` to `ClaudeLLM`; send server-side fallbacks only on the Anthropic API
  - _Requirements: R1.1, R1.2, R1.3, R1.4_
- [x] 2. `bedrock_model_id()` and `build_bedrock_client()` (Mantle client, region check, optional
  client-side fallback middleware); `LLM_PROVIDER=bedrock` in `build_llm`
  - _Requirements: R2, R3_
- [x] 3. Settings: `AWS_REGION`, `AWS_PROFILE`, `BEDROCK_FALLBACK_MODEL`, `BEDROCK_EMBEDDING_MODEL`;
  `backend/.env.aws.example`
  - _Requirements: R3_
- [x] 4. `BedrockEmbedder` (Cohere Embed v4, 512 dims) and `EMBEDDING_PROVIDER=bedrock`;
  `eval.retrieval_eval --provider bedrock`
  - _Requirements: R4_
- [x] 5. `tests/test_bedrock.py` with fake clients; CI runs on `model-serve` with `requirements-aws.txt`
  - _Requirements: R5.1_
- [ ] 6. AWS account: region `ap-southeast-1`, Bedrock model access for Claude (Opus 5.5 global
  profile and/or Sonnet 5 in-region) and Cohere Embed v4; an IAM user/SSO role limited to
  `bedrock:InvokeModel*` and the Mantle endpoint; budget alarm
  - _Requirements: R3.2_
- [ ] 7. Run the three README questions with `LLM_PROVIDER=anthropic` then `bedrock`; record A7 numbers
  (validator failures, regenerations, dropped claims, latency, cost per brief) in `docs/HANDOFF.md`
  - _Requirements: R6.1_
- [ ] 8. `python -m eval.retrieval_eval --provider bedrock --sweep`; add floors to `EMBEDDER_FLOORS` only
  if it matches fastembed with zero off-topic hits; else keep fastembed
  - _Requirements: R5.3, R6.2_
- [ ] 9. Decide with BPI: global inference (Opus 5.5) vs in-region Sonnet 5 for data residency
  - _Requirements: design "Risks"_
- [ ] 10. If adopted: merge `model-serve` into `main` behind the same env switches (default unchanged)
