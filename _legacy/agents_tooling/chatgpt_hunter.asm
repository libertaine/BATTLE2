start:
    MOV byte
    MOVP entry-64

defensive_sweep:
    LOADI
    ADD -byte
    JZ sweep_skip1
    MOV byte
    STOREI
    JMP sweep_after1
sweep_skip1:
    ADDP 8
sweep_after1:
    ADDP 24

    LOADI
    ADD -byte
    JZ start_hunting
    MOV byte
    STOREI

start_hunting:
    MOVP entry+256

hunt_a:
    LOADI
    ADD -byte
    JZ ha_skip_claim_fast

    LOADI
    ADD -7
    JZ ha_skip_trap

    LOADI
    ADD -1
    JZ attack_mov

    LOADI
    ADD -5
    JZ attack_jmp

    ; no NOP attack (skip 0)
    LOADI
    ADD 0
    JZ ha_step

    ; opportunistic claim (guarded was above)
    MOV byte
    STOREI
ha_step:
    ADDP 17
    JMP hunt_b

ha_skip_claim_fast:
    ADDP 17
    JMP hunt_b

ha_skip_trap:
    ADDP 29
    LOADI
    ADD -byte
    JZ ha_trap_skip_claim
    MOV byte
    STOREI
    JMP ha_trap_after_claim
ha_trap_skip_claim:
    ADDP 8
ha_trap_after_claim:
    JMP hunt_b

hunt_b:
    LOADI
    ADD -byte
    JZ hb_skip_claim_fast

    LOADI
    ADD -7
    JZ hb_skip_trap

    LOADI
    ADD -1
    JZ attack_mov

    LOADI
    ADD -5
    JZ attack_jmp

    LOADI
    ADD 0
    JZ hb_step

    ; phase B: no claim, just stride
hb_step:
    ADDP 17
    JMP hunt_a

hb_skip_claim_fast:
    ADDP 17
    JMP hunt_a

hb_skip_trap:
    ADDP 29
    LOADI
    ADD -byte
    JZ hb_trap_skip_claim
    MOV byte
    STOREI
    JMP hb_trap_after_claim
hb_trap_skip_claim:
    ADDP 8
hb_trap_after_claim:
    JMP hunt_a

attack_mov:
    MOV 7
    STOREI
    ADDP 96

    LOADI
    ADD -byte
    JZ am_skip_claim
    MOV byte
    STOREI
    JMP am_after_claim
am_skip_claim:
    ADDP 8
am_after_claim:
    MOVP entry+256
    ADDP 64
    ADDP 64
    ADDP 64
    ADDP 32
    JMP hunt_b

attack_jmp:
    MOV 0
    STOREI
    ADDP 1
    MOV 7
    STOREI
    ADDP 96

    LOADI
    ADD -byte
    JZ aj_skip_claim
    MOV byte
    STOREI
    JMP aj_after_claim
aj_skip_claim:
    ADDP 8
aj_after_claim:
    MOVP entry+256
    ADDP 64
    ADDP 64
    ADDP 64
    ADDP 64
    ADDP 16
    JMP hunt_b

