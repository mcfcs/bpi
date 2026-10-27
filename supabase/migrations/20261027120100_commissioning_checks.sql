-- "Before you commission" coverage checks.
--
-- Each check stores a structured result:
--   {"objectives": [{"text", "coverage": "covered"|"partial"|"gap", "finding_ids"}],
--    "recommended_new_scope": "..."}
-- and how it was handed to S&I's commissioning process (see backend/app/commissioning.py).

create table public.commissioning_checks (
  id           uuid primary key default gen_random_uuid(),
  created_by   uuid not null default auth.uid() references public.profiles (id),
  title        text not null,
  objectives   text[] not null,
  result       jsonb not null,
  adapter      text,
  submission   jsonb,
  submitted_at timestamptz,
  created_at   timestamptz not null default now()
);

alter table public.commissioning_checks enable row level security;

create policy commissioning_checks_read on public.commissioning_checks for select to authenticated
  using (created_by = auth.uid() or public.is_si());
create policy commissioning_checks_insert on public.commissioning_checks for insert to authenticated
  with check (created_by = auth.uid());
create policy commissioning_checks_update on public.commissioning_checks for update to authenticated
  using (created_by = auth.uid() or public.is_si())
  with check (created_by = auth.uid() or public.is_si());

revoke all on public.commissioning_checks from anon;
grant select, insert, update on public.commissioning_checks to authenticated;
