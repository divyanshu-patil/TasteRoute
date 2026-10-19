# F01. Brand intake

## Purpose

Turn a website URL or a short description into a confirmed **brand profile** and a list of **1–5 products**, and stop early if the business is not a fit for TasteRoute.

## User story

As a brand founder, I paste my website and get a profile of what I sell that I can correct in under a minute, so the ranking is based on the right products.

## Inputs

- `website_url` (optional) or `description` (optional); at least one is required.
- Category pack (defaults to Food and drink).

## How it works

1. **Validate the URL.** Only `http` and `https`. Resolve the host and **reject private, loopback, link-local and metadata IP ranges** (SSRF protection). Maximum 3 redirects, each re-checked.
2. **Read pages.** Fetch the homepage and at most 2 more same-domain pages whose link text matches about/shop/products/menu. Timeout `WEBSITE_FETCH_TIMEOUT_SECONDS` each. Respect `robots.txt` for the paths fetched. Maximum 1.5 MB per page. Extract main text with `trafilatura` (fallback: strip tags). Keep at most 12,000 characters total.
3. **Propose a profile.** The agent calls the LLM with the `brand_profile.md` prompt. Output (validated with Pydantic):
   ```json
   {
     "brand_name": "string",
     "one_liner": "string <= 140 chars",
     "category": "food_drink | fashion | unsupported",
     "prospects_are_consumer_facing": true,
     "price_tier": "budget | mid | premium | unknown",
     "style_words": ["string", "... up to 6"],
     "products": [{"name": "string", "kind": "string", "notes": "string"}],
     "unsupported_reason": "string | null"
   }
   ```
4. **Unsupported check.** If `category` is `unsupported` or `prospects_are_consumer_facing` is false, show Flow D (explanation, no run). The user can override once with a confirmation ("My prospects are cafés/shops"), which is logged.
5. **User confirms.** The user edits any field and confirms. The confirmed profile is saved; the raw extracted text is stored for 30 days for debugging, then deleted.
6. **No website.** If the user types a description, step 3 runs on the description alone.

## Outputs and storage

- `brands` row (profile JSON, source URL, confirmed_at).
- `products` rows (1–5).
- `external_calls` rows for each page fetch (URL, status, bytes, duration).

## Failure handling

| Failure | Behaviour |
|---|---|
| URL blocked by SSRF guard | 422 `url_not_allowed` with a plain message |
| Site unreachable, timeout, non-HTML | Ask for a description instead |
| LLM unavailable | Show an empty profile form for the user to fill manually |
| LLM output invalid twice | Same as unavailable, with a notice |
| More than 5 products proposed | Keep the first 5; the user can swap |

## UI

Step 1 of the intake wizard: URL field, "or describe your brand" link, Continue. Step 2: editable profile card with product rows, an "unsupported" banner if relevant.

## Tests

| What | How |
|---|---|
| SSRF guard blocks `127.0.0.1`, `10.0.0.0/8`, `169.254.169.254`, `[::1]`, redirects to private IPs | Unit tests on the URL validator with mocked DNS |
| Page selection picks about/shop pages and stops at 3 | Unit test with stored HTML fixtures |
| Text extraction caps length | Unit test |
| Profile parsing, repair retry, and manual fallback | Unit tests with `FakeProvider` |
| Unsupported detection for "accounting software for law firms" | Fake provider fixture plus API test |
| Full intake through the API | API test with respx-mocked website and fake LLM |

Acceptance: INT-01 to INT-05.
