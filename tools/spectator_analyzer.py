import json
import sys

def circular_dist(a, b, arena_size):
    d = abs(a - b)
    return min(d, arena_size - d)

def main(replay_path):
    arena_size = 8192
    
    # Track the current owner of every address (assuming initially None)
    owner_map = {}
    
    # State tracking
    # (viewer_entrant_id, target_entrant_id) -> bool
    visible_pairs = set() 
    
    active_processes = set()
    disrupted_processes = set()
    
    with open(replay_path, 'r') as f:
        for line in f:
            record = json.loads(line)
            record_type = record.get('record_type')
            
            if record_type == 'header':
                arena_size = record.get('config', {}).get('arena_size', 8192)
                # Initialize owners to None
                for i in range(arena_size):
                    owner_map[i] = None
                    
            elif record_type == 'tick':
                tick = record['tick']
                events_this_tick = []
                
                # Check for disruption (Process ID presence)
                processes = record.get('processes', [])
                current_processes = {p['process_id']: p for p in processes}
                
                # Disruption is deterministically tracked
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
                    length = diff.get('length', 1)
                    owner = diff['owner']
                    
                    if owner is not None:
                        for offset in range(length):
                            curr_addr = (addr + offset) % arena_size
                            prev_owner = owner_map[curr_addr]
                            if prev_owner is not None and prev_owner != owner:
                                events_this_tick.append({
                                    'kind': 'HOSTILE_WRITE',
                                    'actors': [owner, prev_owner],
                                    'address': curr_addr
                                })
                            owner_map[curr_addr] = owner
                
                # Check visibility (Entrant-level detection)
                current_visible = set()
                # Aggregate process anchors by entrant
                anchors_by_entrant = {}
                reach_by_entrant = {}
                for p in processes:
                    e_id = p['entrant_id']
                    if e_id not in anchors_by_entrant:
                        anchors_by_entrant[e_id] = []
                        reach_by_entrant[e_id] = []
                    # Disrupted sensors cannot see!
                    if not p['disrupted']:
                        anchors_by_entrant[e_id].append(p['anchor'])
                        reach_by_entrant[e_id].append(p['reach'])
                        
                for e_a, anchors_a in anchors_by_entrant.items():
                    for e_b, anchors_b in anchors_by_entrant.items():
                        if e_a != e_b:
                            # A can see B if any of A's sensors is close to any of B's anchors
                            can_see = False
                            for idx, a_anchor in enumerate(anchors_a):
                                a_reach = reach_by_entrant[e_a][idx]
                                for b_anchor in anchors_b:
                                    if circular_dist(a_anchor, b_anchor, arena_size) <= a_reach:
                                        can_see = True
                                        break
                                if can_see: break
                            if can_see:
                                current_visible.add((e_a, e_b))
                
                newly_visible = current_visible - visible_pairs
                newly_hidden = visible_pairs - current_visible
                
                for v in newly_visible:
                    events_this_tick.append({'kind': 'DETECTION_GAINED', 'viewer': v[0], 'target': v[1]})
                for v in newly_hidden:
                    events_this_tick.append({'kind': 'DETECTION_LOST', 'viewer': v[0], 'target': v[1]})
                    
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
