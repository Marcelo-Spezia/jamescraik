-- Remitentes (SDRs) + hilo de conversación por lead. Correr una vez en el SQL Editor.

-- Perfiles de remitente: cada SDR con su voz/estilo para clonar el tono en las respuestas.
create table if not exists public.senders (
  slug        text primary key,
  name        text        not null default '',
  role        text        not null default '',
  credibility text        not null default '',   -- base de credibilidad (clientes, sector)
  voice       text        not null default '',   -- cómo escribe esta persona
  examples    jsonb       not null default '[]'::jsonb,  -- 2-3 mensajes de ejemplo (few-shot)
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
alter table public.senders enable row level security;

-- Hilo de conversación por lead (respuesta del lead + respuesta generada + veredicto de fit).
alter table public.leads add column if not exists thread jsonb;
