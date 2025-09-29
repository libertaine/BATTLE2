# replicator: read from source region and write to other region (toy)
start:
  MOVP src_ptr
  LOADI
  MOVP dst_ptr
  STOREI
  ADDP 1
  JMP start

