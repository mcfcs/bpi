-- Study documents: the report PDF behind each study card, and where in it each finding sits.
--
-- The client's point at the consultation: reports carry citations, but nobody outside the owning
-- team can open the report as a whole. Each study can now hold its source document, and each
-- finding records the page it came from, so a brief can cite "SI-2026-014 · p.12" and open the
-- report at that page.
--
-- Read rule: a document is readable exactly when its study is (can_read(), or S&I). Restricted
-- studies' reports are never downloadable by teams without access; the catalogue function below
-- returns metadata only, never document bytes or finding text.
--
-- Provenance labels every study as synthetic demo data, a public third-party source, or internal
-- research uploaded by S&I. Public sources are shown to readers as "Public source" with their
-- publisher; they are not BPI research.

alter table public.studies
  add column provenance text not null default 'internal'
             check (provenance in ('synthetic', 'public', 'internal')),
  add column publisher  text;   -- for public sources, e.g. 'Bangko Sentral ng Pilipinas'

alter table public.findings
  add column page           int check (page is null or page > 0),  -- 1-based page in the study document
  add column source_excerpt text;                                   -- short passage the finding was taken from

create table public.study_documents (
  id          uuid primary key default gen_random_uuid(),
  study_id    uuid not null references public.studies (id) on delete cascade,
  filename    text not null check (length(btrim(filename)) > 0),
  media_type  text not null default 'application/pdf' check (media_type in ('application/pdf')),
  content     bytea not null,
  byte_size   int generated always as (octet_length(content)) stored,
  page_count  int check (page_count is null or page_count > 0),
  sha256      text not null check (sha256 ~ '^[0-9a-f]{64}$'),
  source_url  text,
  source_kind text not null check (source_kind in ('synthetic', 'public', 'uploaded')),
  license     text,
  uploaded_by uuid references public.profiles (id),
  created_at  timestamptz not null default now(),
  constraint study_documents_one_copy unique (study_id, sha256)
);

create index study_documents_study_idx on public.study_documents (study_id);

alter table public.study_documents enable row level security;

create policy study_documents_read on public.study_documents for select to authenticated
  using (public.can_read(study_id) or public.is_si());
create policy study_documents_insert on public.study_documents for insert to authenticated
  with check (public.is_si() and (uploaded_by is null or uploaded_by = auth.uid()));
-- No update or delete policies: a stored report is immutable; a new version is a new row.

revoke all on public.study_documents from anon;
grant select, insert on public.study_documents to authenticated;

-- The study catalogue: every approved study, with metadata only for those the caller cannot read.
-- SECURITY DEFINER so restricted studies can be listed for "Request access"; it never returns
-- summaries, populations, findings or document bytes for unreadable studies.
create or replace function public.study_catalogue()
returns table (
  study_id      uuid,
  code          text,
  title         text,
  owner_team    text,
  access_level  text,
  method_type   text,
  fieldwork_year int,
  provenance    text,
  publisher     text,
  has_document  boolean,
  can_read      boolean
)
language sql stable security definer
set search_path = public, pg_temp
as $$
  select s.id, s.code, s.title, t.name, s.access_level, s.method_type,
         extract(year from s.fieldwork_end)::int, s.provenance, s.publisher,
         exists (select 1 from public.study_documents d where d.study_id = s.id),
         public.can_read(s.id)
  from public.studies s
  join public.teams t on t.id = s.owner_team_id
  where auth.uid() is not null
    and s.review_status = 'approved'
$$;

revoke execute on function public.study_catalogue() from public, anon;
grant execute on function public.study_catalogue() to authenticated;

-- ---------------------------------------------------------------------------
-- Access requests only for approved studies
-- ---------------------------------------------------------------------------
--
-- Found in review: a BU user could file an access request for a study still in the S&I review
-- queue (or rejected), see its code and title through requested_study_catalogue(), and an approver
-- could grant it. Studies that S&I has not approved are not in the catalogue and cannot be
-- requested, decided or listed by anyone outside S&I. The request path answers "not found"
-- (errcode P0002, HTTP 404) so it does not confirm that an unapproved study exists.

create or replace function public.is_approved_study(p_study_id uuid)
returns boolean
language sql stable security definer
set search_path = public, pg_temp
as $$
  select exists (select 1 from public.studies s where s.id = p_study_id and s.review_status = 'approved')
$$;

create or replace function public.access_requests_require_approved_study()
returns trigger
language plpgsql security definer
set search_path = public, pg_temp
as $$
begin
  if not public.is_approved_study(new.study_id) then
    raise exception 'study not found' using errcode = 'P0002';
  end if;
  return new;
end $$;

create trigger access_requests_require_approved_study before insert on public.access_requests
  for each row execute function public.access_requests_require_approved_study();

-- Defence in depth: the insert policy states the same rule.
drop policy access_requests_insert on public.access_requests;
create policy access_requests_insert on public.access_requests for insert to authenticated
  with check (
    requester_id = auth.uid()
    and requester_team_id = public.current_team_id()
    and status = 'pending'
    and decided_by is null
    and public.is_approved_study(study_id)
  );

-- Same as the baseline definition, plus: the study must still be approved when the decision is made.
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
  if not public.is_approved_study(r.study_id) then
    raise exception 'the study is not approved, so access cannot be decided' using errcode = '55000';
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

-- Catalogue metadata for requested studies: never for studies S&I has not approved, except to S&I.
create or replace function public.requested_study_catalogue()
returns table (study_id uuid, code text, title text, owner_team text)
language sql stable security definer
set search_path = public, pg_temp
as $$
  select s.id, s.code, s.title, t.name
  from public.studies s
  join public.teams t on t.id = s.owner_team_id
  where auth.uid() is not null
    and (s.review_status = 'approved' or public.is_si())
    and (s.id in (select r.study_id from public.access_requests r where r.requester_id = auth.uid())
         or public.can_decide_access(s.id))
$$;

revoke execute on function public.is_approved_study(uuid), public.access_requests_require_approved_study()
  from public, anon;
grant execute on function public.is_approved_study(uuid) to authenticated;
