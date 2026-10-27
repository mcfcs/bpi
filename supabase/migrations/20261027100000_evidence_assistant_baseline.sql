-- Evidence assistant: baseline schema.
--
-- Content (studies and findings), the people who use it (teams and profiles) and the approved
-- governance layer:
--   * row-level security, with can_read() as the single read rule for study content
--   * grants and the access-request flow (checkpoint 2: the owning team or S&I decides)
--   * the S&I review queue (checkpoint 1: nothing is searchable until a study card is approved)
--   * analyst escalation (checkpoint 3: "Ask an analyst")
--   * the append-only audit log
-- plus hybrid (pgvector + full-text) search that runs as the caller, so RLS always applies.
--
-- Supabase provides the auth schema, auth.uid() and the anon/authenticated roles. On a plain
-- Postgres, apply supabase/local/supabase_shim.sql first.

create schema if not exists extensions;
create extension if not exists vector with schema extensions;

-- ---------------------------------------------------------------------------
-- Teams and profiles
-- ---------------------------------------------------------------------------

create table public.teams (
  id   uuid primary key default gen_random_uuid(),
  name text not null unique,
  kind text not null check (kind in ('si', 'bu'))
);

create table public.profiles (
  id           uuid primary key references auth.users (id) on delete cascade,
  email        text not null unique,
  display_name text not null,
  team_id      uuid not null references public.teams (id),
  role         text not null default 'bu_user'
               check (role in ('bu_user', 'bu_approver', 'si_analyst'))
);

create or replace function public.current_team_id()
returns uuid
language sql stable security definer
set search_path = public, pg_temp
as $$
  select team_id from public.profiles where id = auth.uid()
$$;

create or replace function public.current_app_role()
returns text
language sql stable security definer
set search_path = public, pg_temp
as $$
  select role from public.profiles where id = auth.uid()
$$;

create or replace function public.is_si()
returns boolean
language sql stable security definer
set search_path = public, pg_temp
as $$
  select coalesce(public.current_app_role() = 'si_analyst', false)
$$;

-- ---------------------------------------------------------------------------
-- Studies and findings
-- ---------------------------------------------------------------------------

create sequence public.study_code_seq start 100;

create table public.studies (
  id            uuid primary key default gen_random_uuid(),
  code          text not null unique
                default ('SI-' || to_char(now(), 'YYYY') || '-' || lpad(nextval('public.study_code_seq')::text, 3, '0')),
  title         text not null,
  summary       text,
  owner_team_id uuid not null references public.teams (id),
  -- open: S&I-funded and readable bank-wide. restricted: owner team plus explicit grants.
  access_level  text not null default 'restricted' check (access_level in ('open', 'restricted')),
  -- Checkpoint 1: a study is searchable only after an S&I analyst approves its card.
  review_status text not null default 'pending_review'
                check (review_status in ('pending_review', 'approved', 'rejected')),
  source_name   text,
  source_text   text,
  created_by    uuid references public.profiles (id),
  created_at    timestamptz not null default now(),
  reviewed_by   uuid references public.profiles (id),
  reviewed_at   timestamptz,
  review_note   text,
  updated_at    timestamptz not null default now()
);

create table public.findings (
  id         uuid primary key default gen_random_uuid(),
  study_id   uuid not null references public.studies (id) on delete cascade,
  ordinal    int not null default 0,
  text       text not null,
  theme      text,
  embedding  extensions.vector(512),
  tsv        tsvector generated always as (
               to_tsvector('english'::regconfig,
                           coalesce(text, '') || ' ' || replace(coalesce(theme, ''), '_', ' '))
             ) stored,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index findings_study_idx on public.findings (study_id);
create index findings_tsv_idx on public.findings using gin (tsv);
create index findings_embedding_idx on public.findings using hnsw (embedding extensions.vector_cosine_ops);

create or replace function public.touch_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at := now();
  return new;
end $$;

create trigger studies_touch_updated_at before update on public.studies
  for each row execute function public.touch_updated_at();
create trigger findings_touch_updated_at before update on public.findings
  for each row execute function public.touch_updated_at();

-- ---------------------------------------------------------------------------
-- Grants and access requests (checkpoint 2)
-- ---------------------------------------------------------------------------

create table public.access_requests (
  id                uuid primary key default gen_random_uuid(),
  study_id          uuid not null references public.studies (id) on delete cascade,
  requester_id      uuid not null references public.profiles (id),
  requester_team_id uuid not null references public.teams (id),
  purpose           text not null check (length(btrim(purpose)) >= 10),
  status            text not null default 'pending' check (status in ('pending', 'approved', 'denied')),
  decided_by        uuid references public.profiles (id),
  decided_at        timestamptz,
  decision_note     text,
  created_at        timestamptz not null default now()
);

create unique index access_requests_one_pending
  on public.access_requests (study_id, requester_id) where status = 'pending';

create table public.study_grants (
  id         uuid primary key default gen_random_uuid(),
  study_id   uuid not null references public.studies (id) on delete cascade,
  team_id    uuid references public.teams (id),
  user_id    uuid references public.profiles (id),
  granted_by uuid references public.profiles (id),
  request_id uuid references public.access_requests (id),
  expires_at timestamptz,
  created_at timestamptz not null default now(),
  constraint study_grants_one_grantee check ((team_id is null) <> (user_id is null))
);

create index study_grants_study_idx on public.study_grants (study_id);

-- The single read rule for study content.
create or replace function public.can_read(p_study_id uuid)
returns boolean
language sql stable security definer
set search_path = public, pg_temp
as $$
  select exists (
    select 1
    from public.studies s
    where s.id = p_study_id
      and s.review_status = 'approved'
      and (
        s.access_level = 'open'
        or s.owner_team_id = public.current_team_id()
        or public.is_si()
        or exists (
          select 1
          from public.study_grants g
          where g.study_id = s.id
            and (g.team_id = public.current_team_id() or g.user_id = auth.uid())
            and (g.expires_at is null or g.expires_at > now())
        )
      )
  )
$$;

-- S&I, or an approver in the team that owns (paid for) the study.
create or replace function public.can_decide_access(p_study_id uuid)
returns boolean
language sql stable security definer
set search_path = public, pg_temp
as $$
  select public.is_si() or exists (
    select 1
    from public.studies s
    join public.profiles p on p.id = auth.uid()
    where s.id = p_study_id
      and p.role = 'bu_approver'
      and p.team_id = s.owner_team_id
  )
$$;

-- ---------------------------------------------------------------------------
-- Briefs, escalation (checkpoint 3) and the audit log
-- ---------------------------------------------------------------------------

create table public.briefs (
  id                    uuid primary key default gen_random_uuid(),
  user_id               uuid not null default auth.uid() references public.profiles (id),
  question              text not null,
  payload               jsonb not null,
  confidence            text check (confidence in ('high', 'medium', 'low')),
  retrieved_finding_ids uuid[] not null default '{}',
  model                 text,
  created_at            timestamptz not null default now()
);

create table public.escalations (
  id           uuid primary key default gen_random_uuid(),
  brief_id     uuid references public.briefs (id) on delete set null,
  requested_by uuid not null default auth.uid() references public.profiles (id),
  reason       text not null check (reason in ('user_request', 'unresolved_conflict', 'low_confidence')),
  note         text,
  status       text not null default 'open' check (status in ('open', 'answered', 'closed')),
  response     text,
  responded_by uuid references public.profiles (id),
  responded_at timestamptz,
  created_at   timestamptz not null default now()
);

create table public.audit_log (
  id          bigint generated always as identity primary key,
  occurred_at timestamptz not null default now(),
  actor_id    uuid,  -- null for scheduled jobs
  action      text not null,
  entity_type text not null,
  entity_id   text,
  details     jsonb not null default '{}'::jsonb
);

create index audit_log_entity_idx on public.audit_log (entity_type, entity_id);

create or replace function public.audit_log_append_only()
returns trigger
language plpgsql
as $$
begin
  raise exception 'audit_log is append-only' using errcode = '42501';
end $$;

create trigger audit_log_no_update_delete before update or delete on public.audit_log
  for each row execute function public.audit_log_append_only();
create trigger audit_log_no_truncate before truncate on public.audit_log
  for each statement execute function public.audit_log_append_only();

-- The only write path into audit_log for API users. The actor is always the caller.
create or replace function public.log_audit(
  p_action      text,
  p_entity_type text,
  p_entity_id   text,
  p_details     jsonb default '{}'::jsonb
)
returns void
language sql security definer
set search_path = public, pg_temp
as $$
  insert into public.audit_log (actor_id, action, entity_type, entity_id, details)
  values (auth.uid(), p_action, p_entity_type, p_entity_id, coalesce(p_details, '{}'::jsonb))
$$;

create or replace function public.decide_access_request(
  p_request_id uuid,
  p_approve    boolean,
  p_note       text default null,
  p_expires_at timestamptz default null
)
returns public.access_requests
language plpgsql security definer
set search_path = public, pg_temp
as $$
declare
  r public.access_requests;
begin
  select * into r from public.access_requests where id = p_request_id for update;
  if not found then
    raise exception 'access request not found' using errcode = 'P0002';
  end if;
  if r.status <> 'pending' then
    raise exception 'access request already decided' using errcode = '55000';
  end if;
  if not public.can_decide_access(r.study_id) then
    raise exception 'not allowed to decide this request' using errcode = '42501';
  end if;
  if r.requester_id = auth.uid() then
    raise exception 'cannot decide your own request' using errcode = '42501';
  end if;

  update public.access_requests
     set status = case when p_approve then 'approved' else 'denied' end,
         decided_by = auth.uid(),
         decided_at = now(),
         decision_note = p_note
   where id = r.id
  returning * into r;

  if p_approve then
    insert into public.study_grants (study_id, team_id, granted_by, request_id, expires_at)
    values (r.study_id, r.requester_team_id, auth.uid(), r.id, p_expires_at);
  end if;

  insert into public.audit_log (actor_id, action, entity_type, entity_id, details)
  values (
    auth.uid(),
    case when p_approve then 'access.approved' else 'access.denied' end,
    'access_request', r.id::text,
    jsonb_build_object('study_id', r.study_id, 'requester_id', r.requester_id,
                       'team_id', r.requester_team_id, 'expires_at', p_expires_at, 'note', p_note)
  );
  return r;
end $$;

-- ---------------------------------------------------------------------------
-- Search
-- ---------------------------------------------------------------------------

-- Any-word full-text query built from the English lexemes of free text.
create or replace function public.or_tsquery(p_text text)
returns tsquery
language sql immutable
as $$
  select to_tsquery('simple', array_to_string(array(
    select quote_literal(lexeme)
    from unnest(tsvector_to_array(to_tsvector('english'::regconfig, coalesce(p_text, '')))) as lexeme
  ), ' | '))
$$;

-- Hybrid search over approved findings, fused with reciprocal rank fusion. SECURITY INVOKER:
-- it runs as the caller, so the RLS policies below decide which findings can be returned.
create or replace function public.match_findings(
  query_embedding extensions.vector,
  query_text      text,
  match_count     int   default 24,
  min_similarity  float default 0.12,
  rrf_k           int   default 50
)
returns table (finding_id uuid, similarity float, text_rank float, score float)
language sql stable security invoker
set search_path = public, extensions, pg_temp
as $$
  with semantic as (
    select f.id,
           row_number() over (order by f.embedding <=> query_embedding) as rank_ix
    from public.findings f
    join public.studies s on s.id = f.study_id
    where s.review_status = 'approved' and f.embedding is not null
    order by f.embedding <=> query_embedding
    limit match_count * 2
  ),
  lexical as (
    select f.id,
           row_number() over (order by ts_rank_cd(f.tsv, public.or_tsquery(query_text)) desc) as rank_ix
    from public.findings f
    join public.studies s on s.id = f.study_id
    where s.review_status = 'approved' and f.tsv @@ public.or_tsquery(query_text)
    order by ts_rank_cd(f.tsv, public.or_tsquery(query_text)) desc
    limit match_count * 2
  ),
  fused as (
    select coalesce(sem.id, lex.id) as id,
           (coalesce(1.0 / (rrf_k + sem.rank_ix), 0.0) + coalesce(1.0 / (rrf_k + lex.rank_ix), 0.0))::float as score
    from semantic sem
    full outer join lexical lex on lex.id = sem.id
  )
  select f.id,
         (1 - (f.embedding <=> query_embedding))::float,
         ts_rank_cd(f.tsv, public.or_tsquery(query_text))::float,
         fu.score
  from fused fu
  join public.findings f on f.id = fu.id
  where 1 - (f.embedding <=> query_embedding) >= min_similarity
  order by fu.score desc
  limit match_count
$$;

-- Approved studies that match the question but that the caller cannot read. SECURITY DEFINER so
-- it can see them; it returns catalogue metadata only (never finding text) for "Request access".
create or replace function public.restricted_study_matches(
  query_embedding extensions.vector,
  match_count     int   default 5,
  min_similarity  float default 0.2
)
returns table (study_id uuid, code text, title text, owner_team text, similarity float)
language sql stable security definer
set search_path = public, extensions, pg_temp
as $$
  select s.id, s.code, s.title, t.name, max(1 - (f.embedding <=> query_embedding))::float as similarity
  from public.findings f
  join public.studies s on s.id = f.study_id
  join public.teams t on t.id = s.owner_team_id
  where auth.uid() is not null
    and s.review_status = 'approved'
    and f.embedding is not null
    and not public.can_read(s.id)
  group by s.id, s.code, s.title, t.name
  having max(1 - (f.embedding <=> query_embedding)) >= min_similarity
  order by similarity desc
  limit match_count
$$;

-- Catalogue metadata (never content) for studies the caller has asked to access or may decide on,
-- so a requester can see what they asked for although they cannot read the study itself.
create or replace function public.requested_study_catalogue()
returns table (study_id uuid, code text, title text, owner_team text)
language sql stable security definer
set search_path = public, pg_temp
as $$
  select s.id, s.code, s.title, t.name
  from public.studies s
  join public.teams t on t.id = s.owner_team_id
  where auth.uid() is not null
    and (s.id in (select r.study_id from public.access_requests r where r.requester_id = auth.uid())
         or public.can_decide_access(s.id))
$$;

-- ---------------------------------------------------------------------------
-- Row-level security
-- ---------------------------------------------------------------------------

alter table public.teams enable row level security;
alter table public.profiles enable row level security;
alter table public.studies enable row level security;
alter table public.findings enable row level security;
alter table public.access_requests enable row level security;
alter table public.study_grants enable row level security;
alter table public.briefs enable row level security;
alter table public.escalations enable row level security;
alter table public.audit_log enable row level security;

create policy teams_read on public.teams for select to authenticated using (true);
create policy profiles_read on public.profiles for select to authenticated using (true);

create policy studies_read on public.studies for select to authenticated
  using (public.can_read(id) or public.is_si());
create policy studies_insert on public.studies for insert to authenticated
  with check (public.is_si());
create policy studies_update on public.studies for update to authenticated
  using (public.is_si()) with check (public.is_si());

create policy findings_read on public.findings for select to authenticated
  using (public.can_read(study_id) or public.is_si());
create policy findings_insert on public.findings for insert to authenticated
  with check (public.is_si());
create policy findings_update on public.findings for update to authenticated
  using (public.is_si()) with check (public.is_si());

create policy access_requests_read on public.access_requests for select to authenticated
  using (requester_id = auth.uid() or public.can_decide_access(study_id));
create policy access_requests_insert on public.access_requests for insert to authenticated
  with check (
    requester_id = auth.uid()
    and requester_team_id = public.current_team_id()
    and status = 'pending'
    and decided_by is null
  );
-- Decisions go through decide_access_request(); there is no update policy.

create policy study_grants_read on public.study_grants for select to authenticated
  using (
    public.is_si()
    or team_id = public.current_team_id()
    or user_id = auth.uid()
    or public.can_decide_access(study_id)
  );
-- Grants are written only by decide_access_request().

create policy briefs_read on public.briefs for select to authenticated
  using (user_id = auth.uid() or public.is_si());
create policy briefs_insert on public.briefs for insert to authenticated
  with check (user_id = auth.uid());

create policy escalations_read on public.escalations for select to authenticated
  using (requested_by = auth.uid() or public.is_si());
create policy escalations_insert on public.escalations for insert to authenticated
  with check (
    requested_by = auth.uid()
    and status = 'open'
    and response is null
    and (brief_id is null or exists (select 1 from public.briefs b where b.id = brief_id and b.user_id = auth.uid()))
  );
create policy escalations_update on public.escalations for update to authenticated
  using (public.is_si()) with check (public.is_si());

create policy audit_log_read on public.audit_log for select to authenticated using (public.is_si());
-- No write policies: rows arrive through log_audit() and security-definer triggers only.

-- ---------------------------------------------------------------------------
-- Privileges
-- ---------------------------------------------------------------------------

revoke all on all tables in schema public from anon;
revoke all on all sequences in schema public from anon;
revoke execute on all functions in schema public from public, anon;

grant usage on schema public to authenticated;
grant select on public.teams, public.profiles to authenticated;
grant select, insert, update on public.studies, public.findings to authenticated;
grant usage on sequence public.study_code_seq to authenticated;
grant select, insert on public.access_requests to authenticated;
grant select on public.study_grants to authenticated;
grant select, insert on public.briefs to authenticated;
grant select, insert, update on public.escalations to authenticated;
grant select on public.audit_log to authenticated;

grant execute on function
  public.current_team_id(),
  public.current_app_role(),
  public.is_si(),
  public.can_read(uuid),
  public.can_decide_access(uuid),
  public.log_audit(text, text, text, jsonb),
  public.decide_access_request(uuid, boolean, text, timestamptz),
  public.or_tsquery(text),
  public.match_findings(extensions.vector, text, int, float, int),
  public.restricted_study_matches(extensions.vector, int, float),
  public.requested_study_catalogue()
to authenticated;
