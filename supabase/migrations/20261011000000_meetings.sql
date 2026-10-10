-- Meeting records written by the meeting runtime.
-- RLS is on with no policies: only the service-role key (server side) can read/write.
create table if not exists public.meetings (
  id text primary key,
  title text not null check (char_length(title) between 1 and 200),
  starts_at timestamptz not null,
  status text not null check (status in ('scheduled', 'active', 'completed', 'cancelled')),
  created_at timestamptz not null
);

create table if not exists public.meeting_participants (
  meeting_id text not null references public.meetings(id) on delete cascade,
  employee_id text not null,
  primary key (meeting_id, employee_id)
);

create table if not exists public.meeting_events (
  id text primary key,
  meeting_id text not null references public.meetings(id) on delete cascade,
  employee_id text not null,
  event_type text not null check (event_type in ('join', 'leave', 'note', 'decision', 'action')),
  content text not null check (char_length(content) between 1 and 4000),
  created_at timestamptz not null
);
create index if not exists idx_meeting_events_meeting on public.meeting_events (meeting_id, created_at);

alter table public.meetings enable row level security;
alter table public.meeting_participants enable row level security;
alter table public.meeting_events enable row level security;
