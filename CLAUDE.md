# Builder Buddy — Project Context

## What this is

Builder Buddy is a modular woodworking and shop management platform built by Nick Gunderson (Bald Beard Builds). Backend is Python/WSGI (`app_server.py`), frontend is React/JSX (`builder-buddy-site.jsx`), integrated with the Claude API.

## Architecture

Python/WSGI backend — do not assume FastAPI unless explicitly told otherwise. Match WSGI patterns from existing codebase.

**Module independence:** Toolbox, Blueprint, and Social Structure are independent modules — each adds to the platform on its own. Toolbox connects to the user's external tool app (connected app integration). Silhouette is the only shared layer: it bridges modules by providing a unified presentation surface. Nothing outside Silhouette should depend on another module directly.

## Modules

| Module | Purpose | Active File(s) |
|---|---|---|
| Blueprint | Build planning | `website_builder_buddy.py` |
| Toolbox | Inventory management — links to external tool app | `website_toolbox.py` |
| Silhouette | Shared presentation bridge (overview, steps, materials, snapshots) | `website_silhouette.py` |
| Social Structure | Points, leaderboard, marketplace | `website_social_structure.py` |
| Tips | Verified Tips knowledge base (CRUD, search, categories) | `website_tips.py` |
| Ron G | AI Q&A via Claude API — build-context-aware, Ron G brand voice | `website_ron_g.py` |

**Test baseline:** 262 passing (Toolbox 54, Blueprint 52, Silhouette 32, Social 37, Tips 34, Ron G 19, Baseline 4)

## Purgatory — Active Bugs

F1 and F2 were avoided in the fresh build — `datetime.now(timezone.utc)` is used throughout, and no `user_id` param collisions exist. Purgatory is clear. Mark new bugs here if they arise.

## Ron G — Mascot / AI Character

Ron G is a consistent brand character — same voice, same identity across all users. Personalization comes from **context injection** (current build, skill level, past session log), not from mutating the character itself. This keeps the voice coherent and the brand memorable while still feeling like Ron G knows you and your project.

If per-user profile personalization is added later (name, preferences, build history), inject it as context — same mechanism, more data.

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

## Context Compaction Rule

When conversations are compacted, **consolidate context — do not lose it**. Every architectural decision, active bug, module state, test count, and working rule must survive compaction. The summary must be dense enough that the next session can pick up without re-deriving anything already settled.
