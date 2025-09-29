# runner: simple survival loop
start:
  NOP
  ADD 1
  JZ start
  JMP start+1

