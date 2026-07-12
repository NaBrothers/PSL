use crate::physics::distance;

#[derive(Debug, Clone)]
pub struct DefenderActionInput {
    pub index: usize,
    pub pos: (f64, f64),
    pub new_pos: (f64, f64),
    pub action: String,
    pub speed: f64,
    pub defence: f64,
    pub is_goalkeeper: bool,
}

#[derive(Debug, Clone)]
pub struct DetectionResult {
    pub defender_index: Option<usize>,
    pub distance: f64,
}

#[derive(Debug, Clone)]
pub struct DuelDetectionInput<'a> {
    pub holder_pos: (f64, f64),
    pub holder_action: &'a str,
    pub carry_target: (f64, f64),
    pub defenders: &'a [DefenderActionInput],
    pub tackle_range: f64,
}

#[derive(Debug, Clone)]
pub struct WastedTackleInput<'a> {
    pub holder_pos: (f64, f64),
    pub holder_action: &'a str,
    pub defenders: &'a [DefenderActionInput],
    pub tackle_range: f64,
}

#[derive(Debug, Clone)]
pub struct InterceptionDetectionInput<'a> {
    pub pass_origin: (f64, f64),
    pub pass_target: (f64, f64),
    pub defenders: &'a [DefenderActionInput],
    pub interception_reach: f64,
}

#[derive(Debug, Clone)]
pub struct DuelResolveInput {
    pub attacker_dribbling: f64,
    pub defender_tackling: f64,
    pub attacker_uniform: f64,
    pub defender_uniform: f64,
}

#[derive(Debug, Clone)]
pub struct InterceptionResolveInput {
    pub defender_defence: f64,
    pub passer_ability: f64,
    pub distance: f64,
    pub interception_reach: f64,
    pub random_value: f64,
}

#[derive(Debug, Clone)]
pub struct DefensivePressureInput<'a> {
    pub holder_pos: (f64, f64),
    pub holder_action: &'a str,
    pub defenders: &'a [DefenderActionInput],
    pub press_radius: f64,
    pub duel_detected: bool,
    pub interception_detected: bool,
}

#[derive(Debug, Clone)]
pub struct DefensivePressureOutput {
    pub defender_index: usize,
    pub successful: bool,
}

pub fn resolve_duel(input: &DuelResolveInput) -> &'static str {
    let atk_roll = input.attacker_dribbling + input.attacker_uniform;
    let def_roll = input.defender_tackling + input.defender_uniform;
    let diff = def_roll - atk_roll;
    if diff > 8.0 {
        "defender_wins"
    } else if diff < -8.0 {
        "attacker_wins"
    } else {
        "loose_ball"
    }
}

pub fn interception_chance(input: &InterceptionResolveInput) -> f64 {
    let base_chance = input.defender_defence / 200.0;
    let proximity_factor = (1.0 - input.distance / input.interception_reach).max(0.3);
    let pass_quality = input.passer_ability / 150.0;
    (base_chance * proximity_factor * (1.0 - pass_quality * 0.4)).clamp(0.05, 0.60)
}

pub fn resolve_interception(input: &InterceptionResolveInput) -> bool {
    input.random_value < interception_chance(input)
}

pub fn detect_duel(input: &DuelDetectionInput<'_>) -> DetectionResult {
    if input.holder_action != "carry" && input.holder_action != "dribble" {
        return DetectionResult {
            defender_index: None,
            distance: 0.0,
        };
    }
    let path_dx = input.carry_target.0 - input.holder_pos.0;
    let path_dy = input.carry_target.1 - input.holder_pos.1;
    let path_len2 = path_dx * path_dx + path_dy * path_dy;

    for defender in input.defenders {
        let d_now = distance(input.holder_pos, defender.pos);
        let d_next = distance(input.holder_pos, defender.new_pos);
        let mut d_path = d_next;
        if path_len2 > 0.01 {
            let rel_x = defender.new_pos.0 - input.holder_pos.0;
            let rel_y = defender.new_pos.1 - input.holder_pos.1;
            let proj = ((rel_x * path_dx + rel_y * path_dy) / path_len2).clamp(0.0, 1.0);
            let closest = (
                input.holder_pos.0 + path_dx * proj,
                input.holder_pos.1 + path_dy * proj,
            );
            d_path = distance(defender.new_pos, closest);
        }
        let intent_factor = match defender.action.as_str() {
            "tackle" => 1.0,
            "approach" => 0.62,
            "block_lane" | "mark_runner" => 0.36,
            _ => 0.16,
        };
        let speed_factor = 0.82 + 0.36 * (defender.speed / 100.0);
        let defence_factor = 0.82 + 0.30 * (defender.defence / 100.0);
        let control_range = input.tackle_range * intent_factor * speed_factor * defence_factor;
        let d = d_now.min(d_next).min(d_path);
        if d < control_range {
            return DetectionResult {
                defender_index: Some(defender.index),
                distance: d,
            };
        }
    }
    DetectionResult {
        defender_index: None,
        distance: 0.0,
    }
}

pub fn track_defensive_pressures(
    input: &DefensivePressureInput<'_>,
) -> Vec<DefensivePressureOutput> {
    let successful_action = matches!(input.holder_action, "pass" | "shoot" | "clear");
    let pressure_range = input.press_radius * 0.55;
    let mut outputs = Vec::new();
    for defender in input.defenders {
        if defender.is_goalkeeper {
            continue;
        }
        let d_now = distance(defender.pos, input.holder_pos);
        let d_next = distance(defender.new_pos, input.holder_pos);
        let min_dist = d_now.min(d_next);
        let is_pressure = (matches!(defender.action.as_str(), "approach" | "tackle")
            && min_dist < pressure_range)
            || (matches!(defender.action.as_str(), "block_lane" | "mark_runner")
                && min_dist < pressure_range * 0.72);
        if !is_pressure {
            continue;
        }
        outputs.push(DefensivePressureOutput {
            defender_index: defender.index,
            successful: input.duel_detected
                || input.interception_detected
                || defender.action == "tackle"
                || successful_action,
        });
    }
    outputs
}

pub fn detect_wasted_tackle(input: &WastedTackleInput<'_>) -> Vec<DetectionResult> {
    if input.holder_action == "carry" || input.holder_action == "dribble" {
        return Vec::new();
    }
    let mut results = Vec::new();
    for defender in input.defenders {
        if defender.action != "tackle" {
            continue;
        }
        let d = distance(input.holder_pos, defender.pos);
        if d < input.tackle_range * 1.5 {
            results.push(DetectionResult {
                defender_index: Some(defender.index),
                distance: d,
            });
        }
    }
    results
}

pub fn detect_interception(input: &InterceptionDetectionInput<'_>) -> DetectionResult {
    let dx = input.pass_target.0 - input.pass_origin.0;
    let dy = input.pass_target.1 - input.pass_origin.1;
    let pass_length = (dx * dx + dy * dy).sqrt();
    if pass_length < 1.0 {
        return DetectionResult {
            defender_index: None,
            distance: 0.0,
        };
    }
    let nx = dx / pass_length;
    let ny = dy / pass_length;

    for defender in input.defenders {
        let px = defender.new_pos.0 - input.pass_origin.0;
        let py = defender.new_pos.1 - input.pass_origin.1;
        let proj = px * nx + py * ny;
        if proj < 2.0 || proj > pass_length - 2.0 {
            continue;
        }
        let perp = (px * ny - py * nx).abs();
        if perp < input.interception_reach {
            return DetectionResult {
                defender_index: Some(defender.index),
                distance: perp,
            };
        }
    }
    DetectionResult {
        defender_index: None,
        distance: 0.0,
    }
}
