#!/usr/bin/env bash
# round_robin.sh — multi-agent round-robin (with optional top-4 bracket)
# Works with:
#  - Built-ins: runner|writer|bomber|flooder|spiral|seeker
#  - ASM sources (.asm): rebuilt per-position with --entry
#  - Prebuilt blobs (.bin): used as-is (WARNING: only position safe if truly position-independent)
#
# Roster CSV format (no header):
# id,kind,source,byte,stride,header
#  - kind: builtin|asm|blob
#  - source: builtin name (for builtin), path/to/agent.asm (for asm), path/to/agent.bin (for blob)
#  - byte: hex or dec for asm build (ignored for builtin/blob unless you rebuild blobs yourself)
#  - stride: asm build param (ignored for builtin/blob)
#  - header: integer header size in bytes (0 for none). For asm builds, header typically 0; for Claude set 16.
#
# Example roster.csv:
# cgpt,asm,agents_tooling/chatgpt_hunter.asm,0xC6,7,0
# claude,asm,agents_tooling/claude_agent.asm,0xC1,7,16
# runner,builtin,runner,0,0,0
# bomber,builtin,bomber,0,0,0
#
# Usage (from repo root):
#   chmod +x round_robin.sh
#   ./round_robin.sh roster.csv
#
# Outputs:
#   results/rr-YYYYmmdd-HHMMSS/...
#   - Per-match folders with cmd.txt, stdout.log, summary.json (if produced)
#   - standings.csv (round robin), leaderboard.txt
#   - If BRACKET=1: bracket_semis.csv, bracket_final.csv, bracket_winner.txt

set -euo pipefail

ROSTER="${1:-}"
[[ -n "${ROSTER}" && -f "${ROSTER}" ]] || { echo "Usage: $0 roster.csv" >&2; exit 1; }

# ---------- Global knobs (override with env) ----------
ARENA="${ARENA:-2048}"
TICKS="${TICKS:-2000}"
WIN_MODE="${WIN_MODE:-score_fallback}"
TERR_W="${TERR_W:-1}"
TERR_BUCKET="${TERR_BUCKET:-32}"
SEEDS="${SEEDS:-1 2 3 4 5}"
PYGAME_FLAG="${PYGAME_FLAG:---pygame}"      # set "" for headless
PARALLEL_JOBS="${PARALLEL_JOBS:-1}"
# Two symmetric positions (rebuild asm for each)
POS_A="${POS_A:-256}"
POS_B="${POS_B:-1536}"
# Enable top-4 single elimination after round robin
BRACKET="${BRACKET:-0}"

STAMP="$(date +%Y%m%d-%H%M%S)"
OUT_ROOT="results/rr-${STAMP}"
mkdir -p "${OUT_ROOT}"

# ---------- Preflight ----------
command -v python3 >/dev/null || { echo "python3 required" >&2; exit 1; }
[[ -x agents_tooling/build.sh ]] || { echo "agents_tooling/build.sh not executable" >&2; exit 1; }

# Disable pygame if parallel
if [[ "${PARALLEL_JOBS}" -gt 1 && -n "${PYGAME_FLAG}" ]]; then
  echo "PARALLEL_JOBS>1: disabling pygame"
  PYGAME_FLAG=""
fi

# Utility: absolute path
abspath() { [[ "$1" = /* ]] && echo "$1" || echo "$(pwd)/$1"; }

# ---------- Load roster ----------
# Arrays keyed by numeric index i
ids=(); kinds=(); sources=(); bytes=(); strides=(); headers=()
while IFS=, read -r id kind src byte stride hdr; do
  [[ -z "$id" || "${id:0:1}" = "#" ]] && continue
  ids+=("$id"); kinds+=("$kind"); sources+=("$src"); bytes+=("${byte:-0}"); strides+=("${stride:-0}"); headers+=("${hdr:-0}")
done < "${ROSTER}"
N="${#ids[@]}"
(( N >= 2 )) || { echo "Need at least 2 agents in roster" >&2; exit 1; }

echo "Loaded $N agents:"
for ((i=0;i<N;i++)); do echo "  - ${ids[i]} (${kinds[i]}): ${sources[i]} hdr=${headers[i]}"; done

# ---------- Build ASM per position ----------
TEMP_DIR="$(mktemp -d)"
WORKLIST="$(mktemp)"
trap 'rm -f "${WORKLIST:-}"; rm -rf "${TEMP_DIR:-}"' EXIT

build_for_entry () {
  # $1=asm path, $2=out bin, $3=entry, $4=name, $5=byte, $6=stride
  local src="$1" out="$2" entry="$3" name="$4" byte="$5" stride="$6"
  local src_dir; src_dir="$(dirname "$(abspath "$src")")"
  local src_file; src_file="$(basename "$src")"
  local out_abs;  out_abs="$(abspath "$out")"
  mkdir -p "$(dirname "$out_abs")"
  ( cd "$src_dir" && ./build.sh "$src_file" "$out_abs" --entry "$entry" --name "$name" --byte "$byte" --stride "$stride" )
}

# For each ASM agent, build a bin for POS_A and POS_B
declare -A BIN_AT_POSA BIN_AT_POSB HDR_BY_ID KIND_BY_ID
for ((i=0;i<N;i++)); do
  id="${ids[i]}"; kind="${kinds[i]}"; src="${sources[i]}"; b="${bytes[i]}"; st="${strides[i]}"; hdr="${headers[i]}"
  KIND_BY_ID["$id"]="$kind"
  if [[ "$kind" == "asm" ]]; then
    outA="${TEMP_DIR}/${id}_${POS_A}.bin"
    outB="${TEMP_DIR}/${id}_${POS_B}.bin"
    build_for_entry "$src" "$outA" "$POS_A" "${id}@${POS_A}" "$b" "$st"
    build_for_entry "$src" "$outB" "$POS_B" "${id}@${POS_B}" "$b" "$st"
    BIN_AT_POSA["$id"]="$outA"
    BIN_AT_POSB["$id"]="$outB"
    HDR_BY_ID["$id"]="${hdr:-0}"
  elif [[ "$kind" == "blob" ]]; then
    # Prebuilt blob; we assume relocation-safe only if its code is position-independent.
    BIN_AT_POSA["$id"]="$(abspath "$src")"
    BIN_AT_POSB["$id"]="$(abspath "$src")"
    HDR_BY_ID["$id"]="${hdr:-0}"
  elif [[ "$kind" == "builtin" ]]; then
    HDR_BY_ID["$id"]="0"
  else
    echo "Unknown kind for $id: $kind" >&2; exit 1;
  fi
done

# ---------- Run one match ----------
run_match() {
  # $1=seed  $2=side(A|B)  $3=idA  $4=idB
  local seed="$1" side="$2" A="$3" B="$4"
  local dir="${OUT_ROOT}/seed-${seed}/${A}_vs_${B}/${side}"
  mkdir -p "$dir"

  # Side A => idA at POS_A, idB at POS_B ; Side B => idA at POS_B, idB at POS_A
  local a_start a_ptr a_args b_start b_ptr b_args
  if [[ "$side" == "A" ]]; then
    # A -> POS_A
    if [[ "${KIND_BY_ID[$A]}" == "builtin" ]]; then
      a_args=( --a-type "${sources[ $(printf '%s\n' "${!ids[@]}" | awk -v id="$A" '{if (ARGV[1]==id && $1==id) print}')]}" --a-start "${POS_A}" )
      a_ptr="${POS_A}"
    else
      a_args=( --a-blob "${BIN_AT_POSA[$A]}" --a-start "${POS_A}" )
      a_ptr=$((POS_A + ${HDR_BY_ID[$A]}))
    fi
    # B -> POS_B
    if [[ "${KIND_BY_ID[$B]}" == "builtin" ]]; then
      # find its source (builtin name)
      btype=""
      for ((i=0;i<N;i++)); do if [[ "${ids[i]}" == "$B" ]]; then btype="${sources[i]}"; fi; done
      b_args=( --b-type "${btype}" --b-start "${POS_B}" )
      b_ptr="${POS_B}"
    else
      b_args=( --b-blob "${BIN_AT_POSB[$B]}" --b-start "${POS_B}" )
      b_ptr=$((POS_B + ${HDR_BY_ID[$B]}))
    fi
  else
    # side B => swap positions
    if [[ "${KIND_BY_ID[$A]}" == "builtin" ]]; then
      atype=""
      for ((i=0;i<N;i++)); do if [[ "${ids[i]}" == "$A" ]]; then atype="${sources[i]}"; fi; done
      a_args=( --a-type "${atype}" --a-start "${POS_B}" )
      a_ptr="${POS_B}"
    else
      a_args=( --a-blob "${BIN_AT_POSB[$A]}" --a-start "${POS_B}" )
      a_ptr=$((POS_B + ${HDR_BY_ID[$A]}))
    fi
    if [[ "${KIND_BY_ID[$B]}" == "builtin" ]]; then
      btype=""
      for ((i=0;i<N;i++)); do if [[ "${ids[i]}" == "$B" ]]; then btype="${sources[i]}"; fi; done
      b_args=( --b-type "${btype}" --b-start "${POS_A}" )
      b_ptr="${POS_A}"
    else
      b_args=( --b-blob "${BIN_AT_POSA[$B]}" --b-start "${POS_A}" )
      b_ptr=$((POS_A + ${HDR_BY_ID[$B]}))
    fi
  fi

  local cmd=( python3 "$(pwd)/main.py"
    --arena "${ARENA}" --ticks "${TICKS}" ${PYGAME_FLAG}
    --win-mode "${WIN_MODE}" --territory-w "${TERR_W}" --territory-bucket "${TERR_BUCKET}"
    --seed "${seed}"
    --ptr "${a_ptr}" "${a_args[@]}"
    --ptr "${b_ptr}" "${b_args[@]}"
  )

  (
    cd "${dir}"
    printf "%s\n" "${cmd[@]}" > cmd.txt
    if ! "${cmd[@]}" > stdout.log 2>&1; then
      echo "RUN FAILED: seed=${seed} ${A} vs ${B} side=${side}" | tee -a stdout.log
    fi
    if [[ ! -f summary.json ]]; then
      echo "WARN: no summary.json (seed=${seed} ${A} vs ${B} side=${side})" | tee -a stdout.log
    fi
  )
}

export -f run_match
export OUT_ROOT ARENA TICKS PYGAME_FLAG WIN_MODE TERR_W TERR_BUCKET POS_A POS_B
export N
# Export bash arrays/maps for subshells launched via xargs (encode as env strings)
# We’ll run sequentially by default to avoid env export issues; parallel works for many shells but not all.
if [[ "${PARALLEL_JOBS}" -gt 1 ]]; then
  echo "Note: PARALLEL_JOBS>1 relies on environment export—if you see missing summaries, rerun with PARALLEL_JOBS=1."
fi

# ---------- Create worklist: all pairings (round robin), both sides, all seeds ----------
pairs=()
for ((i=0;i<N;i++)); do
  for ((j=i+1;j<N;j++)); do
    pairs+=("${ids[i]}|${ids[j]}")
  done
done

for seed in ${SEEDS}; do
  for p in "${pairs[@]}"; do
    IFS='|' read -r A B <<< "$p"
    echo "${seed}|A|${A}|${B}" >> "${WORKLIST}"
    echo "${seed}|B|${A}|${B}" >> "${WORKLIST}"
  done
done

# ---------- Execute ----------
echo "Output dir: ${OUT_ROOT}"
if [[ "${PARALLEL_JOBS}" -gt 1 ]]; then
  < "${WORKLIST}" xargs -I{} -P "${PARALLEL_JOBS}" bash -c '
    IFS="|" read -r seed side A B <<< "{}"
    run_match "$seed" "$side" "$A" "$B"
  '
else
  while IFS="|" read -r seed side A B; do
    run_match "$seed" "$side" "$A" "$B"
  done < "${WORKLIST}"
fi

# ---------- Summarize Round Robin ----------
CSV="${OUT_ROOT}/standings.csv"
echo "pair,seed,side,winner,ticks,A_id,B_id,A_score,B_score,A_alive,B_alive,A_terr,B_terr" > "${CSV}"

python3 - "$OUT_ROOT" "${ROSTER}" >> "${CSV}" <<'PY'
import os, json, sys, csv
root = sys.argv[1]
pairs = []
for seed in sorted(os.listdir(root)):
    sd = os.path.join(root, seed)
    if not os.path.isdir(sd): continue
    for pair_dir in sorted(os.listdir(sd)):
        pd = os.path.join(sd, pair_dir)
        if not os.path.isdir(pd): continue
        A_id, _, B_id = pair_dir.partition("_vs_")
        for side in ("A","B"):
            rd = os.path.join(pd, side)
            js = os.path.join(rd, "summary.json")
            if not os.path.isfile(js):
                print(f"{pair_dir},{seed},{side},NO_SUMMARY,NA,{A_id},{B_id},NA,NA,NA,NA,NA,NA")
                continue
            try:
                j = json.load(open(js))
            except:
                print(f"{pair_dir},{seed},{side},BAD_JSON,NA,{A_id},{B_id},NA,NA,NA,NA,NA,NA")
                continue
            score = j.get("score", j.get("scores", {}))
            As = score.get("A", score.get("a","NA"))
            Bs = score.get("B", score.get("b","NA"))
            Aa = At = Ba = Bt = "NA"
            for a in j.get("agents", []):
                if a.get("id") in ("A","a"):
                    Aa=a.get("alive_ticks","NA"); At=a.get("territory_max", a.get("territory_last","NA"))
                if a.get("id") in ("B","b"):
                    Ba=a.get("alive_ticks","NA"); Bt=a.get("territory_max", a.get("territory_last","NA"))
            print(f"{pair_dir},{seed},{side},{j.get('winner','NA')},{j.get('ticks','NA')},{A_id},{B_id},{As},{Bs},{Aa},{Ba},{At},{Bt}")
PY

# Leaderboard aggregation
awk -F, 'NR>1 && $4!="NO_SUMMARY" && $4!="BAD_JSON" {
  # winner is literal A or B (engine roles), map to agent ids per side
  A_id=$6; B_id=$7; winner=$4; side=$3
  if (winner=="A") w=A_id; else if (winner=="B") w=B_id; else w="NA"
  wins[w]++
} END {
  printf "=== Round Robin Wins ===\n" > "'"${OUT_ROOT}"'/leaderboard.txt"
  for (id in wins) printf "%s,%d\n", id, wins[id] | "sort -t, -k2,2nr >> "'"${OUT_ROOT}"'/leaderboard.txt'"
  close("sort -t, -k2,2nr >> "'"${OUT_ROOT}"'/leaderboard.txt'")
}' "${CSV}"

echo "Round robin standings -> ${CSV}"
echo "Leaderboard -> ${OUT_ROOT}/leaderboard.txt"

# ---------- Optional: Top-4 single-elimination ----------
if [[ "${BRACKET}" -eq 1 ]]; then
  echo "Running top-4 bracket…"
  mapfile -t TOP4 < <(cut -d, -f1 "${OUT_ROOT}/leaderboard.txt" | head -n 4)
  if (( ${#TOP4[@]} < 4 )); then
    echo "Not enough agents with wins for bracket." >&2
    exit 0
  fi
  SEMI1_A="${TOP4[0]}"; SEMI1_B="${TOP4[3]}"
  SEMI2_A="${TOP4[1]}"; SEMI2_B="${TOP4[2]}"
  SEMIS_CSV="${OUT_ROOT}/bracket_semis.csv"
  echo "match,seed,side,winner,ticks,A_id,B_id,A_score,B_score" > "${SEMIS_CSV}"

  run_pair () {
    local name="$1" A="$2" B="$3"
    for seed in ${SEEDS}; do
      # A as side A, B as side B; then swap
      for side in A B; do
        run_match "$seed" "$side" "$A" "$B"
        # append summary row
        local pd="${OUT_ROOT}/seed-${seed}/${A}_vs_${B}/${side}/summary.json"
        if [[ -f "$pd" ]]; then
          python3 - "$name" "$seed" "$side" "$A" "$B" "$pd" >> "${SEMIS_CSV}" <<'PY'
import sys, json
name, seed, side, A, B, path = sys.argv[1:]
j=json.load(open(path))
s=j.get("score", j.get("scores", {})); As=s.get("A", s.get("a","NA")); Bs=s.get("B", s.get("b","NA"))
print(f"{name},{seed},{side},{j.get('winner','NA')},{j.get('ticks','NA')},{A},{B},{As},{Bs}")
PY
        else
          echo "${name},${seed},${side},NO_SUMMARY,NA,${A},${B},NA,NA" >> "${SEMIS_CSV}"
        fi
      done
    done
  }

  run_pair "semi1" "${SEMI1_A}" "${SEMI1_B}"
  run_pair "semi2" "${SEMI2_A}" "${SEMI2_B}"

  # Decide finalists by majority of wins across all seeds/sides
  get_series_winner () {
    local match="$1"
    awk -F, -v m="$match" 'NR>1 && $1==m && $4!="NO_SUMMARY" {
      A=$6; B=$7; w=$4; if (w=="A") win[A]++; else if (w=="B") win[B]++
    } END { mw=""; mv=-1; for (k in win) if (win[k]>mv){mw=k; mv=win[k]} print mw }' "${SEMIS_CSV}"
  }
  F1="$(get_series_winner semi1)"; F2="$(get_series_winner semi2)"
  echo "Finalists: ${F1} vs ${F2}"

  FINAL_CSV="${OUT_ROOT}/bracket_final.csv"
  echo "match,seed,side,winner,ticks,A_id,B_id,A_score,B_score" > "${FINAL_CSV}"
  run_pair "final" "${F1}" "${F2}"

  CHAMP="$(awk -F, 'NR>1 && $1=="final" && $4!="NO_SUMMARY" {A=$6;B=$7;w=$4;if(w=="A")win[A]++;else if(w=="B")win[B]++} END{mw="";mv=-1;for(k in win) if(win[k]>mv){mw=k;mv=win[k]} print mw}' "${FINAL_CSV}")"
  echo "${CHAMP}" > "${OUT_ROOT}/bracket_winner.txt"
  echo "Bracket semis -> ${SEMIS_CSV}"
  echo "Bracket final -> ${FINAL_CSV}"
  echo "Champion -> ${OUT_ROOT}/bracket_winner.txt"
fi

echo "Done."

