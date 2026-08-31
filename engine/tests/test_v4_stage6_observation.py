"""Bytefray v4 Stage 6 Observation Contract Prototype."""
from __future__ import annotations

from dataclasses import dataclass

from battle_engine.agent_api import ActionKind


@dataclass
class CandidateObservation:
    """A minimal observation contract candidate (C1/C2)."""
    current_tick: int
    last_callback_tick: int
    
    self_process_id: str
    self_anchor: int
    self_reach: int
    own_core_base: int
    
    visible_enemy_anchor_addresses: tuple[int, ...]
    
    previous_action_kind: ActionKind | None
    previous_action_tick: int | None
    previous_action_applied: bool
    
    previous_read_value: int | None
    previous_read_owner: str | None
    
    # Contract C2 addition (for testing information leakage)
    previous_disruption_hit: bool | None = None


def test_stale_target_leakage():
    # If we have W1 (disruption_hit), writing to a stale target leaks movement.
    # We want W0 (no confirmation).
    
    # Tick N+1
    enemy_pos_tick_N1 = 564 # Enemy moved from 500
    
    # Attacker writes to 500
    action_applied = True # It's within reach, so the memory write succeeds
    disruption_hit = (enemy_pos_tick_N1 == 500)
    
    # Under W0: attacker sees action_applied=True. 
    # Attacker cannot deduce if enemy moved or stayed without further READ probing.
    assert action_applied == True
    
    # Under W1: attacker sees disruption_hit=False.
    # Attacker instantly knows the enemy moved. This bypasses detection radius limits if 
    # the attacker swept multiple addresses.
    assert disruption_hit == False

def test_stale_feedback_recovery():
    # Tick N
    current_tick = 5
    last_callback_tick = 3
    prev_action_tick = 3
    
    # The agent can deduce it missed tick 4:
    missed_ticks = current_tick - last_callback_tick - 1
    assert missed_ticks == 1
    
    # The agent knows the read feedback is from tick 3:
    is_fresh = (prev_action_tick == current_tick - 1)
    assert not is_fresh

if __name__ == "__main__":
    test_stale_target_leakage()
    test_stale_feedback_recovery()
