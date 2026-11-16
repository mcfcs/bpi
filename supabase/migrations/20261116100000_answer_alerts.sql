-- "A new study answers your question": one alert per earlier brief that no readable study answered,
-- raised when a study the asker can read is approved (or when the asker is granted access to one).
--
-- The match is made under the asker's own row-level security (backend/app/alerts.py), so an alert
-- never points at a study the asker cannot read. Rows are written by the service role after that
-- check; the asker reads and dismisses their own, and S&I reads all of them for the usage summary.

create table public.answer_alerts (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references public.profiles (id),
  brief_id   uuid not null references public.briefs (id) on delete cascade,
  study_id   uuid not null references public.studies (id) on delete cascade,
  question   text not null,
  created_at timestamptz not null default now(),
  read_at    timestamptz,
  unique (brief_id)
);

create index answer_alerts_user_idx on public.answer_alerts (user_id, created_at desc);

alter table public.answer_alerts enable row level security;

create policy answer_alerts_read on public.answer_alerts for select to authenticated
  using (user_id = auth.uid() or public.is_si());
create policy answer_alerts_update on public.answer_alerts for update to authenticated
  using (user_id = auth.uid()) with check (user_id = auth.uid());

revoke all on public.answer_alerts from anon;
grant select on public.answer_alerts to authenticated;
grant update (read_at) on public.answer_alerts to authenticated;
