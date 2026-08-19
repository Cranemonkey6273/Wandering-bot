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

do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename = 'bot_state_store'
      and policyname = 'service role full access'
  ) then
    create policy "service role full access"
      on public.bot_state_store
      for all
      to public
      using (auth.role() = 'service_role')
      with check (auth.role() = 'service_role');
  end if;
end
$$;
