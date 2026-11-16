-- The embedding of each brief's question, kept from the search that answered it (no extra call).
-- The research-gap map uses it to place questions no readable study answered next to the topic
-- they are closest to (backend/app/gaps.py), so unanswered demand shows up in the grid.
-- Follow-up briefs record the brief they continue.

alter table public.briefs add column question_embedding extensions.vector(512);
alter table public.briefs add column follow_up_of uuid references public.briefs (id) on delete set null;
