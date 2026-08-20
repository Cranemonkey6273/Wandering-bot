-- Central ADM event-pipeline foundation.
--
-- The collector stores only a non-reversible token fingerprint here. Keep the
-- actual Nitrado/FTP credentials in the collector's encrypted configuration
-- or deployment secrets; never place them in these tables or event payloads.

create table if not exists public.adm_ingest_sources (
  source_key text primary key,
  service_id text not null,
  token_fingerprint text not null,
  source_kind text not null default 'nitrado_api'
    check (source_kind in ('nitrado_api', 'ftps')),
  enabled boolean not null default true,
  poll_interval_seconds integer not null default 60
    check (poll_interval_seconds between 15 and 1800),
  next_poll_at timestamptz not null default now(),
  lease_owner text,
  lease_expires_at timestamptz,
  last_source_path text,
  last_source_modified_at timestamptz,
  last_success_at timestamptz,
  last_http_status integer,
  consecutive_failures integer not null default 0
    check (consecutive_failures >= 0),
  rate_limited_until timestamptz,
  last_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- A source can serve more than one Discord runtime profile without downloading
-- the same ADM file twice.
create table if not exists public.adm_ingest_routes (
  runtime_id text primary key,
  discord_guild_id text not null,
  server_profile_id text not null default '',
  source_key text not null references public.adm_ingest_sources(source_key)
    on delete cascade,
  enabled boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- Immutable, idempotent record of each parsed source line. `source_generation`
-- is normally the source ADM path plus its generation timestamp; it ensures a
-- new DayZ log can legitimately contain an identical line hash.
create table if not exists public.adm_ingest_events (
  id bigint generated always as identity primary key,
  source_key text not null references public.adm_ingest_sources(source_key)
    on delete cascade,
  source_generation text not null,
  line_hash text not null,
  event_type text not null,
  occurred_at timestamptz,
  observed_at timestamptz not null default now(),
  payload jsonb not null default '{}'::jsonb,
  unique (source_key, source_generation, line_hash)
);

-- Current roster only: it is overwritten on each successful parse so Discord
-- and the dashboard never need to fetch Nitrado just to show online players.
create table if not exists public.adm_online_snapshots (
  runtime_id text primary key references public.adm_ingest_routes(runtime_id)
    on delete cascade,
  source_key text not null references public.adm_ingest_sources(source_key)
    on delete cascade,
  players jsonb not null default '[]'::jsonb,
  player_count integer not null default 0 check (player_count >= 0),
  observed_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- Durable delivery outbox. A Discord worker claims pending rows, sends the
-- feed, and marks them delivered. The uniqueness key makes retry/redeploy safe.
create table if not exists public.discord_feed_outbox (
  id bigint generated always as identity primary key,
  runtime_id text not null references public.adm_ingest_routes(runtime_id)
    on delete cascade,
  event_id bigint references public.adm_ingest_events(id) on delete cascade,
  feed_key text not null,
  dedupe_key text not null,
  payload jsonb not null default '{}'::jsonb,
  status text not null default 'pending'
    check (status in ('pending', 'claimed', 'delivered', 'failed', 'dead_letter')),
  available_at timestamptz not null default now(),
  claimed_by text,
  claimed_at timestamptz,
  delivered_at timestamptz,
  attempts integer not null default 0 check (attempts >= 0),
  last_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (runtime_id, feed_key, dedupe_key)
);

create index if not exists adm_ingest_sources_due_idx
  on public.adm_ingest_sources (next_poll_at)
  where enabled = true;

create index if not exists adm_ingest_sources_lease_idx
  on public.adm_ingest_sources (lease_expires_at)
  where lease_expires_at is not null;

create index if not exists adm_ingest_routes_source_idx
  on public.adm_ingest_routes (source_key)
  where enabled = true;

create index if not exists adm_ingest_events_source_observed_idx
  on public.adm_ingest_events (source_key, observed_at desc);

create index if not exists adm_ingest_events_type_observed_idx
  on public.adm_ingest_events (event_type, observed_at desc);

create index if not exists discord_feed_outbox_ready_idx
  on public.discord_feed_outbox (available_at, id)
  where status = 'pending';

create index if not exists discord_feed_outbox_claimed_idx
  on public.discord_feed_outbox (claimed_at)
  where status = 'claimed';

create or replace function public.touch_adm_event_pipeline_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

drop trigger if exists adm_ingest_sources_updated_at on public.adm_ingest_sources;
create trigger adm_ingest_sources_updated_at
before update on public.adm_ingest_sources
for each row execute function public.touch_adm_event_pipeline_updated_at();

drop trigger if exists adm_ingest_routes_updated_at on public.adm_ingest_routes;
create trigger adm_ingest_routes_updated_at
before update on public.adm_ingest_routes
for each row execute function public.touch_adm_event_pipeline_updated_at();

drop trigger if exists adm_online_snapshots_updated_at on public.adm_online_snapshots;
create trigger adm_online_snapshots_updated_at
before update on public.adm_online_snapshots
for each row execute function public.touch_adm_event_pipeline_updated_at();

drop trigger if exists discord_feed_outbox_updated_at on public.discord_feed_outbox;
create trigger discord_feed_outbox_updated_at
before update on public.discord_feed_outbox
for each row execute function public.touch_adm_event_pipeline_updated_at();

alter table public.adm_ingest_sources enable row level security;
alter table public.adm_ingest_routes enable row level security;
alter table public.adm_ingest_events enable row level security;
alter table public.adm_online_snapshots enable row level security;
alter table public.discord_feed_outbox enable row level security;

do $$
declare
  table_name text;
begin
  foreach table_name in array array[
    'adm_ingest_sources',
    'adm_ingest_routes',
    'adm_ingest_events',
    'adm_online_snapshots',
    'discord_feed_outbox'
  ]
  loop
    if not exists (
      select 1 from pg_policies
      where schemaname = 'public'
        and tablename = table_name
        and policyname = 'service role full access'
    ) then
      execute format(
        'create policy %I on public.%I for all to public using (auth.role() = ''service_role'') with check (auth.role() = ''service_role'')',
        'service role full access',
        table_name
      );
    end if;
  end loop;
end
$$;

comment on table public.adm_ingest_sources is
  'One controlled Nitrado/FTPS polling source. Credentials are intentionally stored outside this table.';
comment on table public.adm_ingest_routes is
  'Maps one ADM source to one or more Discord runtime profiles.';
comment on table public.adm_ingest_events is
  'Idempotent parsed ADM events; payload must not contain credentials.';
comment on table public.adm_online_snapshots is
  'Latest online-player snapshot for a Discord runtime profile.';
comment on table public.discord_feed_outbox is
  'Durable, idempotent Discord delivery jobs emitted by the ADM collector.';
