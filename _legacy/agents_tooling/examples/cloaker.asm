# cloaker: reads at P, if zero then writes back rotated value (toy)
  MOVP ptr_start
loop:
  LOADI
  ADD 1
  STOREI
  JMP loop
