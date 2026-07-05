# Design: Pixel Club Base Home

## Architecture

```
web/src/pages/HomePage.tsx
  ├── loads /me and /squad
  ├── renders React HUD and BuildingPanel
  └── renders ClubTownGame

web/src/game/club/
  ├── ClubTownGame.tsx       # React lifecycle wrapper for Phaser.Game
  ├── ClubTownScene.ts       # Phaser scene: map, buildings, agents, input
  └── types.ts               # Shared scene data contracts
```

## React / Phaser Boundary

React owns:

- API requests and user/squad data
- Navigation via `react-router`
- Building panel state
- Lightweight HUD content
- Existing global `StatusHeader` and `TabBar`

Phaser owns:

- Pixel map rendering
- Programmatic building and decoration drawing
- Agent sprites, nameplates, and movement
- Camera drag
- Building hit areas and click event dispatch

Phaser does not own route changes or app UI. It calls `onBuildingClick(buildingId)` and `onAgentClick(cardId)`, and React decides what to show or navigate to.

## Map Generation

The first version generates visual assets in `ClubTownScene`:

- Grass tile texture with slight variation
- Pale road tiles and plaza paths
- A football pitch with lines and goals
- Pixel block buildings with football facility identity
- Trees, flags, signs, benches, cones, and small equipment
- Generic 16x20 player sprites in several kit colors

The map is organized in tile-aligned coordinates to keep a later Tiled JSON migration straightforward. World size is fixed at `960x640`.

## Buildings

Buildings are mocked client-side:

| ID | Name | Action |
|----|------|--------|
| stadium | 主球场 | `/match` |
| training | 训练中心 | `/squad` |
| academy | 青训营 | `/lottery` |
| scout | 球探中心 | `/search` |
| commerce | 商业中心 | `/transfer` |
| medical | 医疗中心 | `/challenge` |
| clubhouse | 俱乐部大厅 | `/bag` |

Each building has a rectangular hit area, level, status, production copy, and action label. These values remain mock data in this change.

## Agents

Agents come from the current starting XI:

- Source: `squad.cards`
- Empty slots are skipped
- Each agent receives a generic sprite color
- Nameplates show visible player names, truncated for readability
- Agents follow deterministic route loops by role/slot
- Agent click navigates to `/cards/{cardId}`

## Camera

The canvas fills the HomePage content area. The Phaser camera:

- Starts centered on the club base
- Is draggable with pointer/touch
- Is clamped to the 960x640 world bounds
- Does not support zoom in this version

## Building Panel

The React panel is a bottom drawer inside HomePage:

- Opens after a building click
- Shows facility name, level, status, production, and active players nearby
- Provides a primary action button to enter the existing feature page
- Closes via close button or map background click

## Migration Path

Future work can replace programmatic map generation with Tiled assets without changing the React boundary:

```
generated map -> Tiled JSON + tileset
mock buildings -> GET /api/club/buildings
mock production -> collect/upgrade endpoints
generic sprites -> richer sprite sheets
deterministic routes -> behavior model
```
