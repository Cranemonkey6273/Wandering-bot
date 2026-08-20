-- Lock down the legacy tables created before RLS was introduced to the
-- Wandering Bot schema.  The Railway bot has been verified to use the
-- Supabase service-role key, which bypasses RLS; anonymous and authenticated
-- browser clients receive no policy and therefore no access.

alter table if exists public.delivery_queue enable row level security;
alter table if exists public.kills enable row level security;
alter table if exists public.online_players enable row level security;
alter table if exists public.player_data enable row level security;
alter table if exists public.players enable row level security;
alter table if exists public.purchase_orders enable row level security;
alter table if exists public.radar_nodes enable row level security;
alter table if exists public.radar_zones enable row level security;
alter table if exists public.server_registry enable row level security;
alter table if exists public.swear_words enable row level security;

-- Earlier migrations used a public policy with an auth.role() expression.
-- Service-role requests already bypass RLS, so removing those redundant
-- policies both avoids the advisor warning and denies non-service clients.
drop policy if exists "service role full access" on public.bot_state_store;
drop policy if exists "service role full access" on public.adm_ingest_sources;
drop policy if exists "service role full access" on public.adm_ingest_routes;
drop policy if exists "service role full access" on public.adm_ingest_events;
drop policy if exists "service role full access" on public.adm_online_snapshots;
drop policy if exists "service role full access" on public.discord_feed_outbox;

-- Pin trigger-function lookup to the built-in schema path so an untrusted
-- public schema object cannot affect trigger execution.
create or replace function public.set_bot_state_store_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

create or replace function public.touch_adm_event_pipeline_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;
