-- Robustness tiers, population metadata and structured findings.
--
-- Follows the S&I consultation: studies are not on equal footing (method, sample size and
-- recency matter), apparent conflicts are usually differences in who was sampled, and answers
-- need charts built from the actual numbers.
--
-- robustness_tier is computed in application code (backend/app/tiers.py), never by the LLM, on
-- ingestion, whenever method, sample size or fieldwork_end changes, and by a nightly job because
-- recency decays. Analysts can override it at review with a stated reason; every override change
-- is written to the audit log by the trigger below.

alter table public.studies
  add column method_type          text check (method_type in ('quant', 'qual', 'mixed')),
  add column sample_size          int check (sample_size > 0),  -- respondents; for qual, number of participants
  add column fieldwork_end        date,
  add column population           jsonb check (population is null or jsonb_typeof(population) = 'object'),
                                  -- {"age_min":20,"age_max":40,"regions":["NCR"],"segment":"SME owners"}
  add column robustness_tier      text check (robustness_tier in ('A', 'B', 'C')),
  add column tier_override        text check (tier_override in ('A', 'B', 'C')),
  add column tier_override_reason text,
  add column tier_computed_at     timestamptz,
  add column effective_tier       text generated always as (coalesce(tier_override, robustness_tier)) stored;

alter table public.studies
  add constraint studies_tier_override_needs_reason
  check (tier_override is null or length(btrim(coalesce(tier_override_reason, ''))) > 0);

alter table public.findings
  add column finding_type text check (finding_type in ('quant_stat', 'qual_theme', 'verbatim')),
  add column metric_key   text,     -- e.g. 'barrier:fees'
  add column value        numeric,  -- quant_stat only
  add column unit         text check (unit in ('%', 'rank', 'score')),
  add column base_n       int check (base_n > 0),  -- base for this specific number
  add column subgroup     jsonb check (subgroup is null or jsonb_typeof(subgroup) = 'object'),
                          -- {"age_band":"20-40","region":"Cebu"}
  -- Whether the finding shows the metric as prominent (high) or not (low). Divergence between
  -- studies is detected in code by comparing directions on the same metric_key or theme; the
  -- extraction step proposes a value and the analyst confirms it at review.
  add column direction    text check (direction in ('high', 'low', 'neutral'));

alter table public.findings
  add constraint findings_value_is_quant_only check (value is null or finding_type = 'quant_stat');

create index findings_metric_key_idx on public.findings (metric_key) where finding_type = 'quant_stat';

create or replace function public.audit_tier_override()
returns trigger
language plpgsql security definer
set search_path = public, pg_temp
as $$
begin
  insert into public.audit_log (actor_id, action, entity_type, entity_id, details)
  values (
    auth.uid(),
    case when new.tier_override is null then 'study.tier_override_cleared' else 'study.tier_override_set' end,
    'study', new.id::text,
    jsonb_build_object(
      'from', old.tier_override,
      'to', new.tier_override,
      'reason', new.tier_override_reason,
      'computed_tier', new.robustness_tier
    )
  );
  return new;
end $$;

revoke execute on function public.audit_tier_override() from public, anon;

create trigger studies_audit_tier_override
  after update of tier_override, tier_override_reason on public.studies
  for each row
  when (old.tier_override is distinct from new.tier_override
        or old.tier_override_reason is distinct from new.tier_override_reason)
  execute function public.audit_tier_override();
