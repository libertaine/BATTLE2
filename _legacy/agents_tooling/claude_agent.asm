# Claude's Hunter-Defender Agent (Proper Signature Guards)
# Strategy: Smart territorial expansion with signature detection
# Now uses fixed assembler for negative hex literals

start:
    # Phase 1: Territorial sweep with signature protection
    MOV byte                   # Load signature byte  
    MOVP entry-64             # Safe distance from our code
    
defensive_sweep:
    # Guard before each store
    LOADI                     # Check what's here
    ADD -byte                 # Compare with our signature  
    JZ skip_defensive1        # Skip if already ours
    MOV byte                  # Load signature
    STOREI                    # Mark territory
    ADDP 16                   # Move forward
    JMP continue_sweep1
    
skip_defensive1:
    ADDP 16                   # Skip forward without writing
    
continue_sweep1:
    LOADI                     # Check next location
    ADD -byte                 # Compare with signature
    JZ skip_defensive2        # Skip if already ours  
    MOV byte
    STOREI                    # Mark territory
    ADDP 16
    JMP continue_sweep2
    
skip_defensive2:
    ADDP 16
    
continue_sweep2:
    # One more defensive mark then start hunting
    LOADI
    ADD -byte
    JZ start_hunting
    MOV byte  
    STOREI
    
start_hunting:
    # Transition to hunting from safe distance
    MOVP entry+256            # Safe hunt base
    
hunt_loop:
    LOADI
    ADD -byte
    JZ skip_claim_fast        # Already ours - skip quickly

    LOADI
    ADD -7
    JZ skip_trap              # HALT trap - avoid lingering

    LOADI
    ADD 0                     # Check for NOP (0)  
    JZ attack_nop
    
    LOADI                     # Read again
    ADD -1                    # Check for MOV (1)
    JZ attack_mov
    
    LOADI                     # Read again  
    ADD -5                    # Check for JMP (5)
    JZ attack_jmp
    
    # Opportunistic claiming (already guarded above)
    MOV byte                  # Load signature
    STOREI                    # Claim this cell
    ADDP 19                   # Prime stride
    JMP hunt_loop
    
skip_claim_fast:
    ADDP 19                   # Skip ahead without claiming
    JMP hunt_loop

skip_trap:
    ADDP 31                   # Farther hop to break cadence
    JMP hunt_loop

attack_nop:
    MOV 7                     # HALT opcode
    STOREI                    # Plant trap
    ADDP 48                   # Larger stride away from trap
    # Claim territory with guard
    LOADI
    ADD -byte
    JZ reset_after_nop        # Skip claim if already ours
    MOV byte                  
    STOREI                    # Claim territory
    
reset_after_nop:
    MOVP entry+384            # Reset to safe hunt base
    JMP hunt_loop
    
attack_mov:
    MOV 7                     # HALT opcode
    STOREI                    # Overwrite instruction
    ADDP 48                   # Larger stride away
    # Claim with guard
    LOADI
    ADD -byte
    JZ reset_after_mov
    MOV byte                  # Mark with signature  
    STOREI                    # Claim territory
    
reset_after_mov:
    MOVP entry+512            # Reset to safe hunt base
    JMP hunt_loop
    
attack_jmp:
    MOV 0                     # NOP to break control flow
    STOREI
    ADDP 1
    MOV 7                     # HALT trap
    STOREI
    ADDP 48                   # Larger stride away
    # Claim with guard
    LOADI
    ADD -byte
    JZ reset_after_jmp
    MOV byte                  # Load signature
    STOREI                    # Claim territory
    
reset_after_jmp:
    MOVP entry+448            # Reset to safe hunt base  
    JMP hunt_loop
