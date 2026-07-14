#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum MatchClockPhase {
    ActivePlay,
    DeadBall,
}

#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct MatchClock {
    match_seconds: f64,
    active_play_seconds: f64,
    dead_ball_seconds: f64,
    active_play_ticks: i32,
    dead_ball_ticks: i32,
}

#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct MatchClockSnapshot {
    pub match_seconds: f64,
    pub active_play_seconds: f64,
    pub dead_ball_seconds: f64,
    pub active_play_ratio: f64,
    pub match_ticks: i32,
    pub active_play_ticks: i32,
    pub dead_ball_ticks: i32,
}

impl MatchClock {
    pub fn advance(&mut self, phase: MatchClockPhase, tick_duration: f64) {
        if !tick_duration.is_finite() || tick_duration <= 0.0 {
            return;
        }

        self.match_seconds += tick_duration;
        match phase {
            MatchClockPhase::ActivePlay => {
                self.active_play_seconds += tick_duration;
                self.active_play_ticks += 1;
            }
            MatchClockPhase::DeadBall => {
                self.dead_ball_seconds += tick_duration;
                self.dead_ball_ticks += 1;
            }
        }
    }

    pub fn snapshot(&self) -> MatchClockSnapshot {
        let active_play_ratio = if self.match_seconds <= 0.0 {
            0.0
        } else {
            self.active_play_seconds / self.match_seconds
        };
        MatchClockSnapshot {
            match_seconds: self.match_seconds,
            active_play_seconds: self.active_play_seconds,
            dead_ball_seconds: self.dead_ball_seconds,
            active_play_ratio,
            match_ticks: self.active_play_ticks + self.dead_ball_ticks,
            active_play_ticks: self.active_play_ticks,
            dead_ball_ticks: self.dead_ball_ticks,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::{MatchClock, MatchClockPhase};

    #[test]
    fn separates_active_and_dead_time_without_losing_match_time() {
        let mut clock = MatchClock::default();
        clock.advance(MatchClockPhase::ActivePlay, 2.0);
        clock.advance(MatchClockPhase::DeadBall, 4.0);
        clock.advance(MatchClockPhase::ActivePlay, 1.5);

        let snapshot = clock.snapshot();
        assert_eq!(snapshot.match_seconds, 7.5);
        assert_eq!(snapshot.active_play_seconds, 3.5);
        assert_eq!(snapshot.dead_ball_seconds, 4.0);
        assert_eq!(snapshot.match_ticks, 3);
        assert_eq!(snapshot.active_play_ticks, 2);
        assert_eq!(snapshot.dead_ball_ticks, 1);
        assert!((snapshot.active_play_ratio - 3.5 / 7.5).abs() < 1e-12);
    }

    #[test]
    fn ignores_invalid_tick_durations() {
        let mut clock = MatchClock::default();
        clock.advance(MatchClockPhase::ActivePlay, 0.0);
        clock.advance(MatchClockPhase::DeadBall, -2.0);
        clock.advance(MatchClockPhase::ActivePlay, f64::NAN);

        assert_eq!(clock.snapshot(), Default::default());
    }
}
