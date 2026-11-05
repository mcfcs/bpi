# AWS and Kiro plan

How the S&I evidence assistant could run on AWS, and how the team could use Kiro on this repo.
BPI said it "will maybe experiment with AWS (no migration though)", so this is a plan for small,
reversible experiments, not a migration. Nothing here has been built or run yet. Facts were checked
on 30 Oct 2026 (sources at the end). Costs are estimates.

## Status (branch `model-serve`, 5 Nov 2026)

Phase (a)'s code is built on the `model-serve` branch and tested with fake clients; nothing has
called AWS yet. `main` stays the submission demo.

| Done on `model-serve` | Still needs an AWS account |
|---|---|
| `LLM_PROVIDER=bedrock`: `ClaudeLLM` through `AnthropicBedrockMantle`, same prompt and structured output, no server-side fallback, optional client-side fallback (`BEDROCK_FALLBACK_MODEL`) | Model access in `ap-southeast-1`; an SSO role limited to Bedrock invoke; a budget alarm |
| `EMBEDDING_PROVIDER=bedrock`: Cohere Embed v4 at 512 dims; `eval.retrieval_eval --provider bedrock` | The A7 comparison runs and the embedding sweep (spec tasks 7–8) |
| `requirements-aws.txt`, `backend/.env.aws.example`, `tests/test_bedrock.py`, CI on `model-serve` | BPI's answer on global inference vs in-region Sonnet 5 |
| Kiro: `.kiro/steering/`, `.kiro/specs/bedrock-providers/`, `.kiro/hooks/` | Confirm hook trigger names in Kiro's hook panel (docs list `FileSave`/`AgentStop`) |

To try it: `pip install -r backend/requirements-aws.txt`, `aws configure sso`, copy the lines you need
from `backend/.env.aws.example` into `backend/.env.local`, restart the backend; `/api/health` then
reports `bedrock:anthropic.claude-opus-5-5`.

## 1. Recommendation

Start with **Claude through Amazon Bedrock behind the existing `LLM` protocol**, run from a laptop
against the local database: no hosting, no data migration, one new client path in
`backend/app/llm.py`, one environment variable to switch back. It tests what a bank cares about
most: prompts stay inside AWS, and model providers "don't have access to Amazon Bedrock logs or to
customer prompts and completions". Record the A7 numbers (validator failures, regenerations,
latency, cost per brief) for the Anthropic API and Bedrock side by side. Optionally evaluate a
Bedrock embedding model with `backend/eval/retrieval_eval.py`. Only then run a short-lived hosted
demo in Singapore, deleted after the pitch. Build the Bedrock provider as the team's first **Kiro
spec**, so both trainings feed one deliverable.

> **Slide version.** *Today:* runs anywhere: Postgres row-level security, local embeddings, Claude
> optional. *On AWS:* Claude on Bedrock (prompts stay in AWS), Postgres on RDS with the same
> RLS rules, Cognito sign-in, S3 for reports. *How we would try it:* (1) swap the model, (2) a demo
> in Singapore, (3) a bank-grade design only with BPI's security team. Permissions stay in the
> database, so nothing about who sees what changes.

## 2. Service mapping

| Today | On AWS | What changes in our code | Effort |
|---|---|---|---|
| Claude via Anthropic API (`ClaudeLLM`) | **Amazon Bedrock**: Claude Opus 5.5 (`anthropic.claude-opus-5-5`) or Sonnet 5 | `app/llm.py`: client `AnthropicBedrockMantle(aws_region=…)`, or `Anthropic` with base URL `https://bedrock-runtime.{region}.amazonaws.com/anthropic`. Drop `fallbacks="default"` and its beta (no server-side fallback on Bedrock); refusals already become `LLMError` → templates. Structured outputs and prompt caching work. `app/config.py`: `LLM_PROVIDER=bedrock`, `AWS_REGION`, model ID | S |
| fastembed, local (`app/embeddings.py`) | Keep it in the container, **or** Bedrock Cohere Embed | `app/embeddings.py`: `BedrockEmbedder` (`search_document`/`search_query` map onto `embed`/`embed_query`); a new `EMBEDDER_FLOORS` entry in `app/config.py`. Column is `vector(512)`: Embed v4 can output 512 dimensions; Embed Multilingual v3 outputs 1024 and would need a migration | S–M |
| Postgres + pgvector + RLS (`supabase/migrations/`, `app/db.py`) | **RDS for PostgreSQL** (demo); Aurora later | `app/db.py` unchanged. Apply the migrations **plus** `supabase/local/supabase_shim.sql` (no Supabase, so the shim supplies `auth.uid()` and the roles). Add a login role granted `authenticated` | S–M |
| HS256 JWT (`app/auth.py`) | **Amazon Cognito** (Essentials) | `app/auth.py`: verify RS256 tokens against Cognito's JWKS; check `iss`, `token_use`, `client_id` instead of `aud="authenticated"`. The `decode_token` call in `main.py` changes; `as_user()` does not. Seed `profiles.id` with the Cognito `sub` (a UUID Cognito won't let you change). Frontend sign-in is S6 | M |
| PDFs as `bytea` | **S3** (private, SSE-KMS) + presigned GET | Store an object key. The download endpoint checks `can_read()` under `as_user()` first, then presigns for ~60 s | M |
| Scanned PDFs (not handled) | **Amazon Textract** (in `ap-southeast-1`) | `app/ingestion.py`: OCR before `extract_study_card`; output still goes to the review queue | M |
| Next.js proxy + uvicorn (`next.config.mjs`, `scripts/tailnet.ps1`) | **ECS on Fargate**: one task, two containers, behind an ALB | Two Dockerfiles. `BACKEND_URL=http://127.0.0.1:8000` unchanged, so the backend stays on loopback as in `tailnet.ps1`. ALB idle timeout ≥ 300 s to match `proxyTimeout` | M |
| `backend/.env.local`, `.run/*.log` | **Secrets Manager** (as ECS env vars), **CloudWatch Logs** | None: `config.py` reads the environment; logs go to stdout | S |
| Nightly jobs (P4) | EventBridge Scheduler → ECS RunTask | None | S |

**Ruled out for now.** *Amplify Hosting* documents Next.js "up through Next.js 15" (we use 16),
doesn't support Next.js streaming, and users report a 30 s SSR timeout; a brief takes minutes.
*App Runner* is closed to new customers; AWS points to ECS Express Mode.

## 3. Phases

### (a) Zero-risk experiment: laptop only, synthetic data

1. Create an AWS account, set the region to `ap-southeast-1`, and request Bedrock model access.
2. Add the Bedrock path to `ClaudeLLM`. Test it with a fake client, as the existing Claude tests
   do; `OfflineLLM` and `HashingEmbedder` stay the test defaults (invariant 7).
3. Run the three README questions with `LLM_PROVIDER=anthropic` and then `bedrock`, and record the
   A7 metrics.
4. Optional: add `BedrockEmbedder`, then run `python -m eval.retrieval_eval --sweep` against the
   fastembed baseline (paraphrase recall 0.90, Taglish 0.88, off-topic false positives 0.00).

**Region facts that matter:** from Singapore, Opus 5.5 is offered **only through global
cross-region inference** (`global.anthropic.claude-opus-5-5`), which can route anywhere. AWS
announced Sonnet 5 **in-region** in Singapore on 29 Sep 2026. Anthropic says regional endpoints
cost 10 % more than global ones. Cohere Embed Multilingual is in-region in Singapore; Titan Text
Embeddings V2 is not.

**Exit criteria:** `pytest` passes; the briefs from Bedrock pass the validators at a rate similar
to the Anthropic API; A7 numbers are recorded in `docs/HANDOFF.md`. Adopt Bedrock embeddings only
if they match or beat fastembed with zero off-topic hits. Otherwise keep fastembed, which sends no
data anywhere.

### (b) Hosted demo, torn down after 27 Nov

Use RDS PostgreSQL (single-AZ), ECS Fargate in public subnets with tight security groups (no NAT
gateway), Cognito, Secrets Manager and CloudWatch. Seed only the synthetic corpus. Keep
`DEMO_MODE` off and sign in with Cognito personas.

**Exit criteria:** `test_permissions.py`-style checks pass against RDS with real Cognito tokens
(backlog P3); Carla still sees the SME survey only as a restricted match; the audit log refuses
UPDATE and DELETE; the stack can be deleted in one command.

### (c) What a bank-grade deployment would need (questions for BPI, not claims)

- **Network:** private subnets; VPC endpoints (PrivateLink) for Bedrock, S3, Secrets Manager, ECR,
  CloudWatch; no public database; WAF on the ALB.
- **Keys and identity:** customer-managed KMS keys; a task role limited to approved model ARNs (an
  SCP can deny global inference profiles); sign-in federated to BPI's identity provider.
- **Audit:** CloudTrail organisation trail; `audit_log` exported to S3 Object Lock; Multi-AZ,
  backups, penetration test.
- **Regulation (ask BPI):** which BSP outsourcing, cloud and IT-risk rules apply, and whether BSP
  notification or approval is needed; Data Privacy Act / NPC obligations; whether Singapore is
  acceptable. There is **no AWS Region in the Philippines** (a proposed AWS investment was reported
  in July 2026). The Manila Local Zone (parent `ap-southeast-1`) offers EC2, EBS, ECS, EKS, ALB and
  RDS, not Bedrock.

## 4. Keeping our trust invariants on AWS

| Invariant | What to watch |
|---|---|
| RLS decides what anyone sees | Same migrations. The app logs in as a dedicated role granted `authenticated`, **not** the RDS master user and not `bypassrls`. Check the shim's `bypassrls` `service_role` works under `rds_superuser`. `set local` / `set_config(…, true)` are transaction-scoped: test before adding RDS Proxy or a pooler. Keep team and role out of the token; `current_team_id()` reads `profiles`. |
| Restricted findings never reach the model | **No Bedrock Knowledge Bases or Agents for answering.** A knowledge base queries the vector store with its own credentials, so RLS can't see the user; its access control is a metadata filter *the application builds*, i.e. a second copy of `can_read()` that can drift. `RetrieveAndGenerate` also skips `divergence.py` and `validators.py`. Bedrock invocation logs would store prompts containing findings: keep them off, or KMS-encrypted and S&I-only. |
| No LLM numbers; claims validated | Unchanged (code). |
| Humans decide | Textract and Claude extraction feed the review queue. |
| Audit log append-only | Triggers carry over, but `rds_superuser` could disable them: master credentials break-glass only; export the log to S3 Object Lock. |
| Tests offline | New providers behind the existing protocols, tested with fakes; CI keeps pgserver. |

## 5. Kiro on this repo

Kiro reads `AGENTS.md` directly, so **`AGENTS.md` stays the single source of truth**. Add
`.kiro/steering/` files only where Kiro adds something:

| Steering file | Inclusion | Content |
|---|---|---|
| `product.md`, `tech.md`, `structure.md` | always (Kiro's defaults) | Short pointers to the matching `AGENTS.md` sections ("What this is", "Commands", "Layout"), not copies |
| `invariants.md` | always | The seven invariants, plus "update `docs/HANDOFF.md` at the end of a session" |
| `frontend.md` | fileMatch `frontend/**` | "Read `frontend/AGENTS.md`; Next 16 differs from training data", plus the BPI colour rules |
| `retrieval.md` | fileMatch `backend/app/{retrieval,embeddings,config}.py`, `supabase/migrations/**` | Run the retrieval eval and record its numbers |

**First specs** (`.kiro/specs/`; requirements → design → tasks):

1. **Bedrock providers** (phase a). EARS-style acceptance criteria map directly onto tests, for
   example "WHEN `LLM_PROVIDER=bedrock` THE SYSTEM SHALL …".
2. **Production auth (S6)**: Cognito sign-in, JWKS verification in `app/auth.py`, persona switching
   hidden outside `DEMO_MODE`.
3. **Headline vs unresolved conflict (A4)**, once S&I confirms the rule on 4 Nov.

**Hooks** (`.kiro/hooks/`, shell actions):

| Trigger | Action |
|---|---|
| File Save, `backend/**/*.py` | `.venv/Scripts/python -m pytest -q` (~20 s) |
| File Save on retrieval, embeddings, config or migrations | `python -m eval.retrieval_eval --provider hashing` |
| File Save, `frontend/**` | `npm run typecheck` |
| Pre Tool Use (writes) | Block edits to `backend/.env.local`, `frontend/.env.local` and the acceptance/red-team tests |
| Agent Stop | Remind the agent to update `docs/HANDOFF.md` |

**Alongside Claude Code.** Commit `.kiro/` next to `.claude/`; one agent per branch or worktree;
both read `AGENTS.md` and update `HANDOFF.md`; link specs from their `IMPROVEMENTS.md` rows.

**Pricing:** free plan 50 credits a month; Pro $20 for 1,000. Kiro for Students (1,000 credits a
month for a year) listed no Philippine university as of October 2026.

## 6. Rough monthly cost: demo scale (estimates)

Assumptions: `ap-southeast-1`, running 24/7, at most 20 users, about 500 briefs a month, and roughly
12k input tokens plus 4k output tokens per brief, with 30 % of briefs regenerated from cache. The
Claude figures use Anthropic's list prices ($4/$20 per million tokens for Opus 5.5, $2/$10 for
Sonnet 5). Bedrock sets its own prices, so check the Bedrock pricing page.

| Item | Estimate / month |
|---|---|
| Fargate on ARM: backend 0.5 vCPU / 2 GB (fastembed in memory) + frontend 0.25 vCPU / 0.5 GB | ~$30 |
| Application Load Balancer | ~$20–25 |
| RDS PostgreSQL `db.t4g.micro`, 20 GB | ~$20–25 |
| Public IPv4 addresses, CloudWatch Logs, Secrets Manager ($0.40 per secret), S3 | ~$10–15 |
| Cognito Essentials (free up to 10,000 monthly active users) | $0 |
| Claude: Opus 5.5 ≈ $0.15 per brief / Sonnet 5 about half (+10 % for a regional endpoint) | ~$40–80 |
| **Total** | **~$120–175** |

Scaling ECS to zero and stopping RDS between demos cuts the infrastructure lines. New AWS accounts
get $100 in credits, plus up to $100 more for onboarding tasks, on a six-month free plan. Check
whether Claude (billed through AWS Marketplace) is allowed on the free plan. AWS Academy Learner Lab
credits do not cover Bedrock.

## 7. Open questions for BPI

1. Is an AWS experiment with synthetic data acceptable to BPI's security team, and in whose
   account: ours or a BPI sandbox?
2. Is Singapore acceptable? Must inference stay in-region (Sonnet 5), or is global routing
   acceptable (Opus 5.5)?
3. Which BSP and NPC requirements apply to cloud and AI services for internal research data?
4. Does BPI already have an AWS landing zone, an approved list of Bedrock models, or an identity
   provider we should federate to?
5. How long must the audit log be kept, and where?
6. Bedrock or the Anthropic API directly: does BPI prefer one for procurement or data handling?

## Sources

- Claude docs: [Claude in Amazon Bedrock](https://platform.claude.com/docs/en/build-with-claude/claude-in-amazon-bedrock), [Claude Platform on AWS](https://platform.claude.com/docs/en/build-with-claude/claude-platform-on-aws); `claude-api` skill (`shared/platform-availability.md`, Provider Clients)
- AWS Bedrock: [Opus 5.5 model card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-opus-5-5.html), [Claude region expansion, 29 Sep 2026](https://aws.amazon.com/about-aws/whats-new/2026/09/claude-region-expansion-in-sk/), [Regional availability](https://docs.aws.amazon.com/bedrock/latest/userguide/models-region-compatibility.html), [Titan Embeddings V2](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-titan-text-embeddings-v2.html), [Cohere Embed v4](https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters-embed-v4.html), [Cohere Embed Multilingual](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-cohere-embed-multilingual.html), [Data protection](https://docs.aws.amazon.com/bedrock/latest/userguide/data-protection.html), [KB metadata-filter access control](https://aws.amazon.com/blogs/machine-learning/access-control-for-vector-stores-using-metadata-filtering-with-knowledge-bases-for-amazon-bedrock/), [Pricing](https://aws.amazon.com/bedrock/pricing/)
- Data and identity: [PostgreSQL RLS on AWS](https://aws.amazon.com/blogs/database/multi-tenant-data-isolation-with-postgresql-row-level-security), [pgvector 0.8.0 on Aurora](https://aws.amazon.com/about-aws/whats-new/2025/04/pgvector-0-8-0-aurora-postgresql), [Cognito pre token generation](https://docs.aws.amazon.com/cognito/latest/developerguide/user-pool-lambda-pre-token-generation.html), [Cognito pricing](https://aws.amazon.com/cognito/pricing/), [S3 presigned URLs](https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html), [Textract endpoints](https://docs.aws.amazon.com/general/latest/gr/textract.html), [Secrets Manager pricing](https://aws.amazon.com/secrets-manager/pricing/)
- Hosting: [Amplify Next.js support](https://docs.aws.amazon.com/amplify/latest/userguide/ssr-amplify-support.html), [Amplify timeout issue](https://github.com/aws-amplify/amplify-hosting/issues/3223), [App Runner availability change](https://docs.aws.amazon.com/apprunner/latest/dg/apprunner-availability-change.html), [Fargate prices (third-party)](https://vmprices.com/serverless/fargate/)
- Region: [Local Zones features](https://aws.amazon.com/about-aws/global-infrastructure/localzones/features/), [Manila Local Zone (DCD)](https://www.datacenterdynamics.com/en/news/aws-launches-local-zone-in-manila-philippines/), [Proposed PH investment (Newsbytes)](https://newsbytes.ph/2026/07/08/marcos-jr-meets-aws-execs-over-proposed-5-b-cloud-investment-in-ph/)
- Credits: [AWS Free Tier $200 / 6-month plan](https://aws.amazon.com/about-aws/whats-new/2025/07/aws-free-tier-credits-month-free-plan/), [AWS student programmes 2026](https://builder.aws.com/content/3J0F6sCj6NWuOC3jqP6ZYMRyxrc/aws-educate-and-free-credit-programs-for-students-whats-actually-available-in-2026)
- Kiro: [Pricing](https://kiro.dev/pricing/), [Specs](https://kiro.dev/docs/specs/), [Steering](https://kiro.dev/docs/steering/), [Hooks](https://kiro.dev/docs/hooks/), [Hook types](https://kiro.dev/docs/hooks/types/), [MCP](https://kiro.dev/docs/mcp/), [Students](https://kiro.dev/students/)
