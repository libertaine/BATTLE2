import json
import sys

def circular_dist(a, b, arena_size):
    d = abs(a - b)
    return min(d, arena_size - d)

def main(replay_path):
    arena_size = 8192
    
    agent_cores = {} # agent_id -> (start, end)
    
    # State tracking
    # (viewer_entrant_id, viewer_process_id, target_entrant_id, target_process_id) -> bool
    visible_pairs = set() 
    
    active_processes = set()
    disrupted_processes = set()
    
    with open(replay_path, 'r') as f:
        for line in f:
            record = json.loads(line)
            record_type = record.get('record_type')
            
            if record_type == 'header':
                arena_size = record.get('config', {}).get('arena_size', 8192)
            
            elif record_type == 'tick':
                tick = record['tick']
                events_this_tick = []
                
                # Update core regions on tick 0
                if tick == 0:
                    for ag in record.get('agents', []):
                        agent_cores[ag['id']] = ag['region']
                        
                processes = record.get('processes', [])
                
                # Check for process creation/death
                current_processes = {p['process_id']: p for p in processes}
                for pid in current_processes:
                    if pid not in active_processes:
                        events_this_tick.append({'kind': 'PROCESS_CREATED', 'actors': [current_processes[pid]['entrant_id']], 'process_id': pid})
                        active_processes.add(pid)
                
                dead_processes = active_processes - set(current_processes.keys())
                for pid in dead_processes:
                    events_this_tick.append({'kind': 'PROCESS_DEATH', 'process_id': pid})
                    active_processes.remove(pid)
                    # Cleanup visible pairs
                    visible_pairs = {pair for pair in visible_pairs if pair[1] != pid and pair[3] != pid}
                
                # Check for disruption
                for p in processes:
                    pid = p['process_id']
                    if p['disrupted'] and pid not in disrupted_processes:
                        disrupted_processes.add(pid)
                        events_this_tick.append({'kind': 'CORE_DISRUPTION', 'actors': [p['entrant_id']], 'process_id': pid})
                    elif not p['disrupted'] and pid in disrupted_processes:
                        disrupted_processes.remove(pid)
                
                # Check memory diffs for hostile writes
                diffs = record.get('memory_diffs', [])
                for diff in diffs:
                    addr = diff.get('address', diff.get('addr'))
                    owner = diff['owner']
                    if owner is not None:
                        # Check whose core it is in
                        for ag_id, (start, end) in agent_cores.items():
                            if ag_id != owner:
                                # handle circular region
                                in_core = False
                                if start <= end:
                                    in_core = start <= addr <= end
                                else:
                                    in_core = addr >= start or addr <= end
                                if in_core:
                                    events_this_tick.append({
                                        'kind': 'HOSTILE_WRITE',
                                        'actors': [owner, ag_id],
                                        'address': addr
                                    })
                
                # Check visibility
                # process A can see process B if dist(A.anchor, B.anchor) <= A.reach
                # wait, A.anchor is in processes.
                current_visible = set()
                for p_a in processes:
                    for p_b in processes:
                        if p_a['entrant_id'] != p_b['entrant_id']:
                            dist = circular_dist(p_a['anchor'], p_b['anchor'], arena_size)
                            if dist <= p_a['reach']:
                                current_visible.add((p_a['entrant_id'], p_a['process_id'], p_b['entrant_id'], p_b['process_id']))
                
                newly_visible = current_visible - visible_pairs
                newly_hidden = visible_pairs - current_visible
                
                for v in newly_visible:
                    events_this_tick.append({'kind': 'DETECTION_GAINED', 'viewer': v[0], 'target': v[2], 'viewer_pid': v[1], 'target_pid': v[3]})
                for v in newly_hidden:
                    events_this_tick.append({'kind': 'DETECTION_LOST', 'viewer': v[0], 'target': v[2], 'viewer_pid': v[1], 'target_pid': v[3]})
                    
                visible_pairs = current_visible
                
                # Agent deaths
                for ev in record.get('events', []):
                    if ev['type'] in ('death', 'forfeit'):
                        events_this_tick.append({'kind': 'AGENT_ELIMINATED', 'actors': [ev['victim']]})
                
                if events_this_tick:
                    print(json.dumps({'tick': tick, 'events': events_this_tick}))
                    
            elif record_type == 'result':
                winner = record.get('winner')
                if winner:
                    print(json.dumps({'tick': record.get('ticks', 0), 'events': [{'kind': 'VICTORY', 'actors': [winner]}]}))

if __name__ == '__main__':
    main(sys.argv[1])
