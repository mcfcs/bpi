-- Local stand-in for what a Supabase project already provides: the auth schema, auth.uid() and
-- auth.jwt(), the anon/authenticated/service_role roles and the extensions schema.
--
-- Apply this only to a plain Postgres used for local development and tests. Never apply it to a
-- Supabase project; the migrations in ../migrations run there as-is.

create schema if not exists extensions;
create schema if not exists auth;

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then
    create role anon nologin noinherit;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then
    create role authenticated nologin noinherit;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'service_role') then
    create role service_role nologin noinherit bypassrls;
  end if;
end $$;

create table if not exists auth.users (
  id         uuid primary key,
  email      text unique,
  created_at timestamptz not null default now()
);

-- Same definitions Supabase uses: identity comes from the request's JWT claims.
create or replace function auth.uid()
returns uuid
language sql stable
as $$
  select coalesce(
    nullif(current_setting('request.jwt.claim.sub', true), ''),
    (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub')
  )::uuid
$$;

create or replace function auth.jwt()
returns jsonb
language sql stable
as $$
  select coalesce(nullif(current_setting('request.jwt.claims', true), '')::jsonb, '{}'::jsonb)
$$;

grant usage on schema auth, extensions, public to anon, authenticated, service_role;
grant execute on function auth.uid(), auth.jwt() to anon, authenticated, service_role;

-- Lets the API connection switch to the request's role, as the postgres role can on Supabase.
grant anon, authenticated, service_role to current_user;
