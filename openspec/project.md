# PSL - Premier Star League

A football (soccer) simulation game with bot and web interfaces.

## Repository Structure

- `psl_core/` — Core shared library (abilities, formations, constants)
- `bot/` — QQ bot client
- `server/` — FastAPI web server
- `web/` — React frontend
- `engine/` (under bot) — Current match engine (v1)
- `scripts/` — Utility scripts (migration, simulation)

## Conventions

- Language: Python 3.10+ for backend, TypeScript/React for frontend
- Package management: pip / npm
- Testing: pytest for Python
- Configuration: Admin web panel + database-backed config
