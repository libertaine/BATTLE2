# writer: write a fixed address (entry + 128)
  MOV 0x41
  STORE entry+128   # assembler will not evaluate expressions; use build-time ptr instead
  JMP 0

