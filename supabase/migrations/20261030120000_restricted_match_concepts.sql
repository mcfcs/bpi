-- Restricted-study hints that share the question's concept, not just its product.
--
-- restricted_study_matches ranked restricted studies by embedding similarity alone, so "Test appetite
-- for a pet insurance add-on among young cardholders" hinted at the card-rewards study (both are
-- about cards). The app cannot check what such a study is about: the function returns catalogue
-- metadata only, by design. So the check runs here: when the caller passes the question's concept
-- words (app/topicality.py concept_words), a study qualifies only if one of its findings contains
-- one of them (full text), or its similarity reaches bypass_similarity (for paraphrases a lexical
-- check misses). The return columns are unchanged: still no finding text, values or counts.
--
-- Callers that pass no concept words get the previous behaviour.

drop function if exists public.restricted_study_matches(extensions.vector, int, float);

create function public.restricted_study_matches(
  query_embedding   extensions.vector,
  match_count       int   default 5,
  min_similarity    float default 0.2,
  concept_text      text  default null,
  bypass_similarity float default 2.0
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
     and (nullif(btrim(coalesce(concept_text, '')), '') is null
          or max(1 - (f.embedding <=> query_embedding)) >= bypass_similarity
          or bool_or(f.tsv @@ public.or_tsquery(concept_text)))
  order by similarity desc
  limit match_count
$$;

revoke execute on function public.restricted_study_matches(extensions.vector, int, float, text, float) from public, anon;
grant execute on function public.restricted_study_matches(extensions.vector, int, float, text, float) to authenticated;
