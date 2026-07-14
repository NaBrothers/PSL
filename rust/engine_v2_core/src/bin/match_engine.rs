use std::io::{self, Read, Write};

use psl_engine_v2_core::{run_match_v2, MatchV2RunRequest};

fn main() -> Result<(), String> {
    let mode = std::env::args()
        .nth(1)
        .ok_or_else(|| "missing mode; expected match_v2_run".to_string())?;
    if mode != "match_v2_run" {
        return Err(format!("unknown mode: {mode}; expected match_v2_run"));
    }

    let mut input = String::new();
    io::stdin()
        .read_to_string(&mut input)
        .map_err(|err| err.to_string())?;
    let request: MatchV2RunRequest =
        serde_json::from_str(input.trim()).map_err(|err| err.to_string())?;
    let response = run_match_v2(request);
    let stdout = io::stdout();
    let mut stdout = stdout.lock();
    serde_json::to_writer(&mut stdout, &response).map_err(|err| err.to_string())?;
    stdout.write_all(b"\n").map_err(|err| err.to_string())?;
    Ok(())
}
