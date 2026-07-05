# Change: Add pixel club base home

## Why

The current web home page is a menu/dashboard surface. It is functional, but it does not express PSL as a living football club. The planned club facility gameplay needs a home surface where facilities are visible, characters move through the base, and buildings can become both navigation and long-term progression entry points.

## What Changes

- **NEW** Phaser-powered pixel club base scene on `/home`
- **NEW** Programmatically generated bright pixel-art club facility map, without external tilesets for the first version
- **NEW** Eleven starting-player agents walking through the base with visible names
- **NEW** Mock building data for stadium, training center, academy, scout center, commerce center, medical center, and clubhouse
- **NEW** React bottom drawer building panel opened by Phaser building clicks
- **MODIFIED** `HomePage.tsx` becomes a React shell around the Phaser scene and lightweight HUD

## Impact

- Affected specs: `web-home`
- Affected code: `web/src/pages/HomePage.tsx`, `web/src/game/club/*`, `web/package.json`
- No backend schema or club-building persistence is added in this change

## Design Decisions

1. **Phaser 3 for the world** — Phaser renders the map, buildings, agents, camera, and input hit areas.
2. **React for app UI** — React keeps API loading, routing, HUD, and building panel.
3. **Programmatic assets first** — generate pixel map, buildings, and sprites in code so visual direction can be validated before sourcing tilesets.
4. **Orthogonal pixel map** — use a Stanford Town style orthogonal map, not isometric.
5. **960x640 world** — render a larger world than the mobile viewport and allow camera drag; no zoom in the first version.
6. **Starting XI agents** — render the current starting squad as eleven generic pixel characters with visible names.
7. **Mock buildings** — building level/status/production are local mock data in this version.
8. **Bottom drawer panel** — building clicks open a React bottom drawer with facility info and an action button.
9. **Preserve global shell** — keep existing `StatusHeader` and `TabBar`.
