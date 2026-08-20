create table if not exists public.bot_state_store (
  state_key text primary key,
  state_value jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

create index if not exists bot_state_store_updated_at_idx
  on public.bot_state_store (updated_at);

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

drop trigger if exists bot_state_store_updated_at on public.bot_state_store;
create trigger bot_state_store_updated_at
before update on public.bot_state_store
for each row
execute function public.set_bot_state_store_updated_at();

alter table public.bot_state_store enable row level security;

-- The Supabase service-role key bypasses RLS.  Do not add a broad `public`
-- policy here: anonymous and authenticated browser clients must not read the
-- bot's runtime state.
