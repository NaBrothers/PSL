## 1. Dependencies
- [x] 1.1 Add Phaser to the web package dependencies

## 2. Phaser Scene
- [x] 2.1 Create shared club scene types
- [x] 2.2 Create `ClubTownScene` with 960x640 world bounds
- [x] 2.3 Generate programmatic pixel textures for grass, roads, buildings, pitch, decorations, and agents
- [x] 2.4 Render seven mock club facilities with hit areas
- [x] 2.5 Render starting XI agents with visible names and route-loop movement
- [x] 2.6 Add camera drag clamped to world bounds
- [x] 2.7 Emit building and agent click callbacks to React

## 3. React Integration
- [x] 3.1 Create `ClubTownGame` React wrapper that mounts and destroys Phaser
- [x] 3.2 Replace `HomePage` dashboard content with Phaser scene shell and lightweight HUD
- [x] 3.3 Add React bottom drawer building panel with mock building data and action navigation
- [x] 3.4 Preserve existing global `StatusHeader` and `TabBar`

## 4. Validation
- [x] 4.1 Run `npm run build`
- [x] 4.2 Run `openspec validate add-pixel-club-base-home`
