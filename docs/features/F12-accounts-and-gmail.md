# F12. Accounts and sending from Gmail

## Purpose

Let a user keep their work across devices, and send an approved pitch from their own Gmail in one click.

## Sign-in

1. "Log in to save progress" in the nav signs in with Google through Supabase Auth (PKCE). The same sign-in asks for Gmail's `gmail.send` permission, which can send but never read mail.
2. Back on the page, the browser sends the Supabase access token to `POST /v1/workspaces/login`. The API checks it once with Supabase (`GET /auth/v1/user`) and ties a workspace to the account: this browser's workspace if the account has none, or the account's existing one. Work done before signing in moves into it.
3. "All runs" then lists every run from any device the user logged in on. On your own database, `uv run python scripts/claim_runs.py <email>` (after logging in once) moves every run made without signing in into the account; never on a shared database, where it would take other people's runs.
4. After that the API uses the same signed workspace token as before; it never sees a password. "Log out" clears the browser's tokens and starts a new anonymous workspace.
5. Without `NEXT_PUBLIC_SUPABASE_ANON_KEY` (web) and `SUPABASE_ANON_KEY` (API), sign-in is hidden and everything else works as before.

## Sending

1. A signed-in user sees "Send with Gmail" on each draft. One click saves any edits and sends that one email from their Gmail. Clicking send is the approval.
2. The API rebuilds the email from the stored draft (to the contact's address, the subject and body, with the opt-out line), checks the do-not-contact list, claims the draft so a double click cannot send twice, and calls Gmail's `users.messages.send`.
3. Google's token lasts about an hour. It stays in the browser, goes to the API with each send, and is never stored or logged. When Gmail refuses it, the button asks to connect Gmail again.
4. A sent draft is final: status `sent`, `sent_at`, Gmail's message id. It can't be edited or regenerated, and re-running outreach leaves it alone.
5. Nothing is sent in bulk or on a schedule. The "Open in mail app" link, "Copy email" and the CSV still work for users who don't sign in.

## Outputs and storage

`workspaces.user_id` and `email`; `drafts.status = 'sent'`, `sent_at`, `gmail_message_id`.

## Tests

`tests/api/test_accounts.py` (sign-in keeps and merges work; a forged token fails; send once, never twice; Gmail refusal asks to reconnect; suppression blocks), `lib/account.test.ts` (Google token expiry), `test_static.py` (no mail service; Gmail only from the send route).
