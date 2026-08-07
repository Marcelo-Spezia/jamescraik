-- Persistencia durable de campañas y contexto (reemplaza los archivos efímeros del disco
-- de Streamlit Cloud). Correr una vez en el SQL Editor de Supabase.
-- La app usa la service_role key → bypassa RLS; no hay acceso anónimo a estas tablas.

-- Campañas (la definición del "ICP": filtros Sales Nav + rúbrica + propuesta de valor + señales).
create table if not exists public.campaigns (
  slug               text primary key,
  name               text        not null default '',
  sales_nav_filters  jsonb       not null default '[]'::jsonb,
  rubric             text        not null default '',
  value_prop         text        not null default '',
  enrichment_signals jsonb       not null default '[]'::jsonb,
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now()
);
alter table public.campaigns enable row level security;

-- Contexto de Making Sense (una sola fila, key = 'making_sense').
create table if not exists public.app_context (
  key        text primary key,
  content    text        not null default '',
  updated_at timestamptz not null default now()
);
alter table public.app_context enable row level security;
