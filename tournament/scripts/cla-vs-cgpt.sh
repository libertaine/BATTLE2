#!/usr/bin/env bash
# cgpt_vs_claude.sh — Position-balanced ChatGPT-Hunter vs Claude-Hunter
# Bash 4.2+. Python 3 required for summarization.

set -euo pipefail

# ---------- Config (override via env) ----------
ARENA="${ARENA:-4096}"
TICKS="${TICKS:-4000}"
WIN_MODE="${WIN_MODE:-score_fallback}"
TERR_W="${TERR_W:-1}"
TERR_BUCKET="${TERR_BUCKET:-32}"
SEEDS="${SEEDS:-1 2 3 4 5 6 7 8 9 10}"
PARALLEL_JOBS="${PARALLEL_JOBS:-1}"

# Source ASM files
CGPT_ASM="${CGPT_ASM:-agents_tooling/chatgpt_hunter.asm}"
CLAUDE_ASM="${CLAUDE_ASM:-agents_tooling/claude_agent.asm}"

# Spawn positions (symmetric pair)
POS_A="${POS_A:-256}"
POS_B="${POS_B:-1536}"
CLAUDE_HDR="${CLAUDE_HDR:-16}"   # header size for Claude blob

PYGAME_FLAG="${PYGAME_FLAG:---pygame}"   # set to "" to disable GUI

STAMP="$(date +%Y%m%d-%H%M%S)"
OUT_ROOT="results/cgpt-vs-claude-${STAMP}"
mkdir -p "${OUT_ROOT}"

# ---------- Preflight ----------
for f in "${CGPT_ASM}" "${CLAUDE_ASM}"; do
  [[ -f "$f" ]] || { echo "Missing ASM source: $f" >&2; exit 1; }
done
command -v python3 >/dev/null || { echo "python3 required" >&2; exit 1; }
[[ -x agents_tooling/build.sh ]] || { echo "agents_tooling/build.sh not executable" >&2; exit 1; }

# Utility: compute absolute path (works on Linux; avoids readlink -f portability issues)
abspath() { [[ "$1" = /* ]] && echo "$1" || echo "$(pwd)/$1"; }

# ---------- Rebuild agents for both positions ----------
TEMP_DIR="$(mktemp -d)"
# Create WORKLIST early so trap never references an unset var
WORKLIST="$(mktemp)"
trap 'rm -f "${WORKLIST:-}"; rm -rf "${TEMP_DIR:-}"' EXIT

echo "Rebuilding agents for position-independent testing..."
echo "Temp directory: ${TEMP_DIR}"

build_for_entry () {
  # build_for_entry SRC_ASM OUT_BIN ENTRY NAME [BYTE] [STRIDE]
  local src="$1" out="$2" entry="$3" name="$4" byte="${5:-0xC6}" stride="${6:-7}"
  local src_dir; src_dir="$(dirname "$(abspath "$src")")"
  local src_file; src_file="$(basename "$src")"
  local out_abs;  out_abs="$(abspath "$out")"
  mkdir -p "$(dirname "$out_abs")"
  # Run build.sh from inside agents_tooling so it can find asm_assembler.py
  ( cd "$src_dir" && ./build.sh "$src_file" "$out_abs" --entry "$entry" --name "$name" --byte "$byte" --stride "$stride" )
}

# Build ChatGPT agent for both positions (no header)
build_for_entry "${CGPT_ASM}"   "${TEMP_DIR}/cgpt_${POS_A}.bin"   "${POS_A}" "ChatGPT-${POS_A}" 0xC6
build_for_entry "${CGPT_ASM}"   "${TEMP_DIR}/cgpt_${POS_B}.bin"   "${POS_B}" "ChatGPT-${POS_B}" 0xC6

# Build Claude agent for both positions (has header CLAUDE_HDR)
build_for_entry "${CLAUDE_ASM}" "${TEMP_DIR}/claude_${POS_A}.bin" "${POS_A}" "Claude-${POS_A}" 0xC1
build_for_entry "${CLAUDE_ASM}" "${TEMP_DIR}/claude_${POS_B}.bin" "${POS_B}" "Claude-${POS_B}" 0xC1

echo "Agent builds complete."

# ---------- One match ----------
run_one () {
  local seed="$1"
  local side="$2"   # "A": CGPT at POS_A vs Claude at POS_B
                    # "B": Claude at POS_A vs CGPT at POS_B

  local dir="${OUT_ROOT}/seed-${seed}/${side}"
  mkdir -p "${dir}"

  local a_blob a_start a_ptr
  local b_blob b_start b_ptr

  if [[ "${side}" == "A" ]]; then
    a_blob="${TEMP_DIR}/cgpt_${POS_A}.bin";   a_start=${POS_A}; a_ptr=${POS_A}
    b_blob="${TEMP_DIR}/claude_${POS_B}.bin"; b_start=${POS_B}; b_ptr=$((POS_B + CLAUDE_HDR))
  else
    a_blob="${TEMP_DIR}/claude_${POS_A}.bin"; a_start=${POS_A}; a_ptr=$((POS_A + CLAUDE_HDR))
    b_blob="${TEMP_DIR}/cgpt_${POS_B}.bin";   b_start=${POS_B}; b_ptr=${POS_B}
  fi

  local cmd=( python3 "$(pwd)/main.py"
    --arena "${ARENA}"
    --ticks "${TICKS}"
    ${PYGAME_FLAG}
    --win-mode "${WIN_MODE}"
    --territory-w "${TERR_W}"
    --territory-bucket "${TERR_BUCKET}"
    --seed "${seed}"
    --ptr "${a_ptr}" --a-blob "${a_blob}" --a-start "${a_start}"
    --ptr "${b_ptr}" --b-blob "${b_blob}" --b-start "${b_start}"
  )

  (
    cd "${dir}"
    printf "%s\n" "${cmd[@]}" > cmd.txt
    if ! "${cmd[@]}" > stdout.log 2>&1; then
      echo "RUN FAILED: seed ${seed} side ${side}" | tee -a stdout.log
    fi
    if [[ ! -f summary.json ]]; then
      echo "WARN: no summary.json (seed=${seed}, side=${side})" | tee -a stdout.log
    fi
  )
}

# ---------- Execute ----------
echo "Output dir: ${OUT_ROOT}"
echo "Running ${PARALLEL_JOBS} parallel job(s)..."
if [[ "${PARALLEL_JOBS}" -gt 1 && -n "${PYGAME_FLAG}" ]]; then
  echo "PARALLEL_JOBS>1: disabling pygame for stability"
  PYGAME_FLAG=""
fi

for s in ${SEEDS}; do
  echo "${s}|A" >> "${WORKLIST}"
  echo "${s}|B" >> "${WORKLIST}"
done

if [[ "${PARALLEL_JOBS}" -gt 1 ]]; then
  export -f run_one
  export OUT_ROOT ARENA TICKS PYGAME_FLAG WIN_MODE TERR_W TERR_BUCKET TEMP_DIR POS_A POS_B CLAUDE_HDR
  < "${WORKLIST}" xargs -I{} -P "${PARALLEL_JOBS}" bash -c '
    IFS="|" read -r seed side <<< "{}"
    run_one "${seed}" "${side}"
  '
else
  while IFS="|" read -r seed side; do
    run_one "${seed}" "${side}"
  done < "${WORKLIST}"
fi

# ---------- Summarize ----------
CSV="${OUT_ROOT}/summary.csv"
echo "seed,side,winner,ticks,A_score,B_score,A_alive_ticks,B_alive_ticks,A_terr,B_terr" > "${CSV}"

python3 - "$OUT_ROOT" >> "${CSV}" <<'PY'
import os,json,sys
root=sys.argv[1]
for seed in sorted(os.listdir(root)):
    sd=os.path.join(root,seed)
    if not os.path.isdir(sd): continue
    for side in ("A","B"):
        rd=os.path.join(sd,side)
        summ=os.path.join(rd,"summary.json")
        if not os.path.isfile(summ):
            print(f"{seed},{side},NO_SUMMARY,NA,NA,NA,NA,NA,NA,NA")
            continue
        try:
            with open(summ) as f: j=json.load(f)
        except:
            print(f"{seed},{side},BAD_JSON,NA,NA,NA,NA,NA,NA,NA")
            continue
        score=j.get("score", j.get("scores", {}))
        A_score=score.get("A", score.get("a", "NA"))
        B_score=score.get("B", score.get("b", "NA"))
        agents=j.get("agents", [])
        A_alive=A_terr="NA"; B_alive=B_terr="NA"
        for a in agents:
            if a.get("id") in ("A","a"):
                A_alive=a.get("alive_ticks","NA")
                A_terr=a.get("territory_max", a.get("territory_last","NA"))
            if a.get("id") in ("B","b"):
                B_alive=a.get("alive_ticks","NA")
                B_terr=a.get("territory_max", a.get("territory_last","NA"))
        print(f"{seed},{side},{j.get('winner','NA')},{j.get('ticks','NA')},{A_score},{B_score},{A_alive},{B_alive},{A_terr},{B_terr}")
PY

# ---------- Leaderboard ----------
awk -F, 'NR>1 && $3!="NO_SUMMARY" && $3!="BAD_JSON" {
  if ($2=="A" && $3=="A") cgpt++;
  if ($2=="A" && $3=="B") claude++;
  if ($2=="B" && $3=="A") claude++;
  if ($2=="B" && $3=="B") cgpt++;
} END {
  printf "ChatGPT-Hunter total wins: %d\nClaude-Hunter total wins: %d\n", cgpt+0, claude+0
}' "${CSV}" > "${OUT_ROOT}/leaderboard.txt"

cat "${OUT_ROOT}/leaderboard.txt"
echo ""
echo "Wrote ${CSV}"
echo "Wrote ${OUT_ROOT}/leaderboard.txt"
echo "Done."

