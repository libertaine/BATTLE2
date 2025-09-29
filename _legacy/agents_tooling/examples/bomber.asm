# bomber: pointer-based spray
  MOV 0x99
  MOVP ptr_start
loop:
  STOREI
  ADDP stride
  JMP loop

