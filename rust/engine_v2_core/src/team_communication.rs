use crate::tactical_task::{CommunicatedTeammateHint, TacticalTask};

pub const TEAM_COMMUNICATION_PLAYER_COUNT: usize = 11;

const UNKNOWN_OBSERVED_TICK: i32 = i32::MIN / 4;

#[derive(Clone, Copy, Debug)]
struct TeamSharedTask {
    task: Option<TacticalTask>,
    received_tick: i32,
}

#[derive(Clone, Copy, Debug)]
struct TeamSharedPosition {
    pos: (f64, f64),
    observed_tick: i32,
    received: bool,
}

const EMPTY_SHARED_POSITION: TeamSharedPosition = TeamSharedPosition {
    pos: (0.0, 0.0),
    observed_tick: UNKNOWN_OBSERVED_TICK,
    received: false,
};

const EMPTY_SHARED_TASK: TeamSharedTask = TeamSharedTask {
    task: None,
    received_tick: UNKNOWN_OBSERVED_TICK,
};

#[derive(Clone, Copy, Debug)]
pub struct TeamSharedBelief {
    tasks: [TeamSharedTask; TEAM_COMMUNICATION_PLAYER_COUNT],
    positions: [TeamSharedPosition; TEAM_COMMUNICATION_PLAYER_COUNT],
}

impl Default for TeamSharedBelief {
    fn default() -> Self {
        Self {
            tasks: [EMPTY_SHARED_TASK; TEAM_COMMUNICATION_PLAYER_COUNT],
            positions: [EMPTY_SHARED_POSITION; TEAM_COMMUNICATION_PLAYER_COUNT],
        }
    }
}

impl TeamSharedBelief {
    pub fn task(&self, player_index: usize, tick: i32) -> Option<TacticalTask> {
        self.tasks
            .get(player_index)
            .and_then(|shared| shared.task)
            .filter(|task| task.active(tick))
    }

    pub fn teammate_hint(&self, player_index: usize) -> Option<CommunicatedTeammateHint> {
        self.positions.get(player_index).and_then(|shared| {
            shared.received.then_some(CommunicatedTeammateHint {
                index: player_index,
                pos: shared.pos,
                confidence: 0.35,
                observed_tick: shared.observed_tick,
            })
        })
    }

    fn advance_to(&mut self, tick: i32) {
        for shared_task in &mut self.tasks {
            if shared_task.task.is_some_and(|task| !task.active(tick)) {
                shared_task.task = None;
            }
        }
    }

    fn merge_message(&mut self, message: TeamCommunicationMessage, tick: i32) {
        self.positions[message.sender_index] = TeamSharedPosition {
            pos: message.pos,
            observed_tick: message.observed_tick,
            received: true,
        };
        if let Some(task) = message.task.filter(|task| task.active(tick)) {
            self.tasks[message.sender_index] = TeamSharedTask {
                task: Some(task),
                received_tick: tick,
            };
        } else if self
            .tasks
            .get(message.sender_index)
            .is_some_and(|shared| shared.received_tick <= message.observed_tick)
        {
            self.tasks[message.sender_index] = EMPTY_SHARED_TASK;
        }
    }
}

#[derive(Clone, Copy, Debug)]
pub struct TeamCommunicationPublishInput {
    pub sender_index: usize,
    pub task: Option<TacticalTask>,
    pub pos: (f64, f64),
    pub observed_tick: i32,
}

#[derive(Clone, Copy, Debug)]
struct TeamCommunicationMessage {
    pending: bool,
    sender_index: usize,
    task: Option<TacticalTask>,
    pos: (f64, f64),
    observed_tick: i32,
    deliver_tick: i32,
}

const EMPTY_TEAM_COMMUNICATION_MESSAGE: TeamCommunicationMessage = TeamCommunicationMessage {
    pending: false,
    sender_index: 0,
    task: None,
    pos: (0.0, 0.0),
    observed_tick: UNKNOWN_OBSERVED_TICK,
    deliver_tick: UNKNOWN_OBSERVED_TICK,
};

#[derive(Clone, Copy, Debug)]
struct TeamCommunicationState {
    shared: TeamSharedBelief,
    queued: [TeamCommunicationMessage; TEAM_COMMUNICATION_PLAYER_COUNT],
}

impl Default for TeamCommunicationState {
    fn default() -> Self {
        Self {
            shared: TeamSharedBelief::default(),
            queued: [EMPTY_TEAM_COMMUNICATION_MESSAGE; TEAM_COMMUNICATION_PLAYER_COUNT],
        }
    }
}

impl TeamCommunicationState {
    fn deliver(&mut self, tick: i32) {
        self.shared.advance_to(tick);
        for message in &mut self.queued {
            if !message.pending || message.deliver_tick > tick {
                continue;
            }
            self.shared.merge_message(*message, tick);
            *message = EMPTY_TEAM_COMMUNICATION_MESSAGE;
        }
    }

    fn publish(&mut self, input: TeamCommunicationPublishInput) {
        let Some(message) = self.queued.get_mut(input.sender_index) else {
            return;
        };
        *message = TeamCommunicationMessage {
            pending: true,
            sender_index: input.sender_index,
            task: input.task,
            pos: input.pos,
            observed_tick: input.observed_tick,
            deliver_tick: input.observed_tick.saturating_add(1),
        };
    }
}

#[derive(Clone, Copy, Debug, Default)]
pub struct TeamCommunicationBus {
    home: TeamCommunicationState,
    away: TeamCommunicationState,
}

impl TeamCommunicationBus {
    pub fn reset(&mut self) {
        *self = Self::default();
    }

    pub fn deliver(&mut self, tick: i32) {
        self.home.deliver(tick);
        self.away.deliver(tick);
    }

    pub fn publish(&mut self, team_home: bool, input: TeamCommunicationPublishInput) {
        if team_home {
            self.home.publish(input);
        } else {
            self.away.publish(input);
        }
    }

    pub fn snapshot(&self, team_home: bool) -> TeamSharedBelief {
        if team_home {
            self.home.shared
        } else {
            self.away.shared
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn active_support_task(
        target: (f64, f64),
        accepted_tick: i32,
        expires_tick: i32,
    ) -> TacticalTask {
        let mut task = TacticalTask::inactive(target);
        task.intent = crate::TacticalTaskIntent::Support;
        task.phase = crate::TacticalTaskPhase::Active;
        task.accepted_tick = accepted_tick;
        task.expires_tick = expires_tick;
        task.commitment = 0.8;
        task
    }

    #[test]
    fn declared_task_arrives_on_the_next_tick_only() {
        let mut bus = TeamCommunicationBus::default();
        let task = active_support_task((60.0, 18.0), 8, 14);
        bus.publish(
            false,
            TeamCommunicationPublishInput {
                sender_index: 7,
                task: Some(task),
                pos: (58.0, 22.0),
                observed_tick: 8,
            },
        );

        bus.deliver(8);
        assert!(bus.snapshot(false).task(7, 8).is_none());
        assert!(bus.snapshot(false).teammate_hint(7).is_none());
        bus.deliver(9);
        assert_eq!(
            bus.snapshot(false)
                .task(7, 9)
                .map(|shared| shared.raw_target),
            Some((60.0, 18.0))
        );
        assert_eq!(
            bus.snapshot(false).teammate_hint(7),
            Some(CommunicatedTeammateHint {
                index: 7,
                pos: (58.0, 22.0),
                confidence: 0.35,
                observed_tick: 8,
            })
        );
        assert!(bus.snapshot(true).teammate_hint(7).is_none());
    }

    #[test]
    fn declared_tasks_are_isolated_by_team() {
        let mut bus = TeamCommunicationBus::default();
        bus.publish(
            true,
            TeamCommunicationPublishInput {
                sender_index: 5,
                task: Some(active_support_task((72.0, 40.0), 4, 12)),
                pos: (68.0, 38.0),
                observed_tick: 4,
            },
        );
        bus.deliver(5);

        assert!(bus.snapshot(true).task(5, 5).is_some());
        assert!(
            bus.snapshot(false).task(5, 5).is_none(),
            "the opposing side must never receive the other team's task declaration"
        );
    }

    #[test]
    fn cancellation_and_expiry_release_a_declared_task() {
        let mut bus = TeamCommunicationBus::default();
        bus.publish(
            true,
            TeamCommunicationPublishInput {
                sender_index: 3,
                task: Some(active_support_task((74.0, 24.0), 10, 13)),
                pos: (70.0, 22.0),
                observed_tick: 10,
            },
        );
        bus.deliver(11);
        assert!(bus.snapshot(true).task(3, 11).is_some());

        bus.publish(
            true,
            TeamCommunicationPublishInput {
                sender_index: 3,
                task: None,
                pos: (71.0, 22.0),
                observed_tick: 11,
            },
        );
        bus.deliver(12);
        assert!(
            bus.snapshot(true).task(3, 12).is_none(),
            "a teammate must stop reserving space after the source cancels its task"
        );

        bus.publish(
            true,
            TeamCommunicationPublishInput {
                sender_index: 3,
                task: Some(active_support_task((74.0, 24.0), 12, 13)),
                pos: (72.0, 22.0),
                observed_tick: 12,
            },
        );
        bus.deliver(13);
        assert!(bus.snapshot(true).task(3, 13).is_some());
        bus.deliver(14);
        assert!(bus.snapshot(true).task(3, 14).is_none());
    }
}
