# Change: Upgrade space model — dynamic position value, pass-to-space, zone-based marking

## Why

Current engine has correct structure (reward-driven, 3-phase tick) but produces unrealistic gameplay:
- No penetrating runs (forwards stand still)
- No width exploitation (all cluster around ball)
- Passes only to feet (no through-balls or space exploitation)
- Defenders all chase ball instead of marking zones
- Goals too few because attack can't break through organized defense

Root cause: position_value is static, doesn't account for dynamic space creation or teammate coordination. All behavior must emerge from an upgraded spatial model.

## What Changes

- **MODIFIED** `position_value.py` — Add space_creation_bonus + receive_reachability factors
- **MODIFIED** `player.py` — Upgrade off-ball attack (dynamic candidate scoring), add pass_to_space action, fix defend mark/block to use zones, IQ noise on all evaluations
- **MODIFIED** `match.py` — Handle pass_to_space execution (ball to space, first-to-arrive gets it)
- **MODIFIED** `config.py` — New parameters for space model

## Design (all from space model, no if-else)

1. **position_value upgrade**: value = base_space × space_creation × receive_reachability
2. **Off-ball attack runs**: candidate positions scored by upgraded PV → front-runs, wide-runs, drop-deep all emerge naturally
3. **pass_to_space**: new on-ball candidate — pass toward high-value space where teammate can arrive first
4. **Zone-based marking**: defenders mark attackers in THEIR zone, not chase ball
5. **IQ as perception noise**: all evaluations get noise scaled by (100-IQ)/100

## Impact
- Affected: position_value.py, player.py, match.py, config.py
- No frontend changes
- No API changes
