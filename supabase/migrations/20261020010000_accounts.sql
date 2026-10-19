-- Sign-in (Supabase Auth, Google) keeps a workspace across devices; one-click sending from the user's own Gmail.
alter table workspaces add column user_id uuid unique, add column email text;
alter table drafts drop constraint drafts_status_check;
alter table drafts add constraint drafts_status_check check (status in ('draft','edited','approved','exported','sent'));
alter table drafts add column sent_at timestamptz, add column gmail_message_id text;
