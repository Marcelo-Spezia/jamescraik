-- Enrichment web de Exa (company + persona) por lead. Correr una vez en el SQL Editor.
-- Guarda run_id + status (fire→poll async) + los facts con su fuente.
alter table public.leads add column if not exists exa jsonb;
