# Builder Buddy — Project Context

## What this is

Builder Buddy is a modular woodworking and shop management platform built by Nick Gunderson (Bald Beard Builds). Backend is Python/WSGI (`app_server.py`), frontend is React/JSX (`builder-buddy-site.jsx`), integrated with the Claude API.

## Architecture

Python/WSGI backend — do not assume FastAPI unless explicitly told otherwise. Match WSGI patterns from existing codebase.

## Modules

| Module | Purpose | Active File(s) |
|---|---|---|
| Blueprint | Build planning | `builder-buddy-site.jsx`, `website_builder_buddy.py` |
| Toolbox | Inventory management | `website_toolbox.py` |
| Silhouette | Presentation layer / Blueprint sidecar | `website_silhouette.py` |
| Social Structure | Points, leaderboard, marketplace | In development |

**Test baseline:** 118+ passing (Toolbox 54, Blueprint 42, Silhouette 22, baseline 4)

## Purgatory — Active Bugs

Resolve in dependency order. Do not mark resolved without explicit confirmation.

- **F1** — `datetime.utcnow()` deprecated throughout. Replace with `datetime.now(timezone.utc)`. Fix F1 before F2 where they touch the same files.
- **F2** — `user_id` keyword argument collision crash in `update_build()` and `update_tool()`. Needs param rename or signature fix.

## Tool / Workshop OS Rules

- Tool List, Upgrades, Hardware, Material are parallel interconnected lists
- Owned vs Wishlist separation is mandatory
- Duplicate detection requires clarification — never silent merge
- "Add to toolbox" = item is owned
- Wishlist tools ranked 1–5 stars
- Smart-routing: new items auto-placed into correct list type

## Engineering Rules

- Accuracy > speed
- Buildability > aesthetics
- Systems > shortcuts
- When unsure on dimensions, safety, or irreversible steps — ask, don't guess
- Don't revise completed/working steps unless necessary
- Finalized/sellable plans are locked

## Brand Voice (Ron G)

Stoic, calm, direct, dry humor, safety-first, no condescension toward beginners. Core philosophy: everyone starts somewhere, fundamentals matter forever, the shop is supposed to be fun. Tone scales with timing/consequence — never dramatic.

## Working Style

- Concise and direct — no restating context back
- Act on corrections immediately
- Builder Buddy core is untouchable without explicit instruction + full confirmation
- Destructive ops (migrations, schema changes) require double confirmation
- Don't invent standards, dimensions, tool capabilities, or API behavior — verify or ask
