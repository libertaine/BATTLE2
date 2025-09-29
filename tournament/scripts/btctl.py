#!/usr/bin/env python3
# Python 3.13
import argparse, csv, json, os, subprocess, sys, time
from collections import defaultdict, Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROSTER = ROOT / "roster.json"
OUTROOT = ROOT / "results"

# Defaults (your spec)
DEF = dict(arena=2048, ticks=2000, win_mode="score_fallback", territory_w=1, territory_bucket=32)

def _find_build_sh() -> Path:
    # Priority: env override -> likely repo spots
    env = os.environ.get("BUILD_SH")
    if env:
        p = Path(env)
        if p.exists() and p.is_file():
            return p
    for rel in ("build.sh", "agents_tooling/build.sh", "tools/build.sh"):
        cand = ROOT / rel
        if cand.exists() and cand.is_file():
            return cand
    raise FileNotFoundError(
        "build.sh not found. Set $BUILD_SH to an existing path or place build.sh at one of:\n"
        f" - {ROOT/'build.sh'}\n - {ROOT/'agents_tooling/build.sh'}\n - {ROOT/'tools/build.sh'}"
    )

BUILD_SH = _find_build_sh()

def _battle_cmd():
    # Allow override to a specific launcher/binary if desired
    if os.environ.get("BATTLE_BIN"):
        return os.environ["BATTLE_BIN"].split()
    if (ROOT / "main.py").exists():
        return [sys.executable, str(ROOT / "main.py")]
    return [sys.executable, "-m", "BATTLE"]

def load_roster():
    with open(ROSTER) as f:
        r = json.load(f)
    builtins = list(r.get("builtins", []))
    customs = r.get("custom", [])
    return builtins, customs

def build_customs(customs, outdir=None):
    outdir = Path(outdir or ROOT / "agents_build")
    outdir.mkdir(parents=True, exist_ok=True)
    built = []
    for c in customs:
        name = c["name"]
        asm_path = ROOT / c["asm"]
        header = int(c.get("header", 0))
        entry = int(c.get("entry", header))
        blob = outdir / f"{name}.blob"

        cmd = [str(BUILD_SH), str(asm_path), str(blob), "--entry", str(entry)]
        if header:
            cmd += ["--header", str(header)]

        subprocess.run(cmd, cwd=ROOT, check=True)
        built.append({"name": name, "blob": str(blob)})
    return built

def normalize_player(name, built_map):
    if name in built_map:
        return {"name": name, "cli": "runner", "cfg": {"type": "blob", "path": built_map[name]}}
    else:
        return {"name": name, "cli": name, "cfg": {"type": "builtin", "id": name}}

def run_game(a, b, seed, outdir, params=None, swap=False):
    p = dict(DEF)
    if params: p.update(params)
    outdir = Path(outdir); outdir.mkdir(parents=True, exist_ok=True)
    tag = f"{a['name']}__vs__{b['name']}__seed-{seed}__{'BA' if swap else 'AB'}"
    rundir = outdir / tag; rundir.mkdir(exist_ok=True)

    # Engine invocation
    cmd = _battle_cmd() + [
        "--ticks", str(p["ticks"]),
        "--arena", str(p["arena"]),
        "--win-mode", str(p["win_mode"]),
        "--territory-w", str(p["territory_w"]),
        "--territory-bucket", str(p["territory_bucket"]),
        "--seed", str(seed),
        "--a-type", a["cli"],
        "--b-type", b["cli"],
        "--replay", str(rundir / "replay.jsonl"),
        "--config", str(rundir / "config.json"),
    ]

    # Supply blob config via env hook (engine must honor this)
    agents_json = {"A": a["cfg"], "B": b["cfg"]}
    (rundir / "agents.json").write_text(json.dumps(agents_json, indent=2))
    env = os.environ.copy()
    env["BATTLE_AGENTS_JSON"] = str(rundir / "agents.json")

    subprocess.run(cmd, cwd=ROOT, env=env, check=True)

    # summary.json must be produced by engine into rundir (or copy if global)
    sfile = rundir / "summary.json"
    if not sfile.exists():
        # try to pull a stray summary.json if engine dropped it at CWD
        stray = ROOT / "summary.json"
        if stray.exists():
            stray.replace(sfile)
    return rundir

def parse_summary(path: Path):
    try:
        data = json.loads(Path(path).read_text())
    except Exception:
        return {}
    return {
        "winner": data.get("winner", ""),
        "ticks": data.get("ticks", 0),
        "A_score": data.get("A_score", 0),
        "B_score": data.get("B_score", 0),
        "A_alive_ticks": data.get("A_alive_ticks", data.get("A_alive", 0)),
        "B_alive_ticks": data.get("B_alive_ticks", data.get("B_alive", 0)),
        "A_terr": data.get("A_territory", 0),
        "B_terr": data.get("B_territory", 0),
        "seed": data.get("seed", None)
    }

def write_match_csv(runs, csv_path):
    header = ["seed","side","winner","ticks","A_score","B_score","A_alive_ticks","B_alive_ticks","A_terr","B_terr"]
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f); w.writerow(header)
        for r in runs:
            s = parse_summary(r / "summary.json")
            if not s: continue
            side = "B" if r.name.endswith("BA") else "A"
            seed = s.get("seed")
            w.writerow([f"seed-{seed}", side, s["winner"], s["ticks"], s["A_score"], s["B_score"],
                        s["A_alive_ticks"], s["B_alive_ticks"], s["A_terr"], s["B_terr"]])

def aggregate_leaderboard(results_root, out_csv, out_md=None):
    results = list(Path(results_root).rglob("summary.json"))
    if not results:
        print("No summary.json found", file=sys.stderr); return
    stats = defaultdict(lambda: {"wins":0,"losses":0,"ties":0,"games":0,"score_diff":0,"terr_diff":0,"survive_ticks":0})
    for sfile in results:
        data = parse_summary(sfile)
        tag = sfile.parent.name  # A__vs__B__seed-X__AB
        a_name = tag.split("__vs__")[0]
        b_name = tag.split("__vs__")[1].split("__seed-")[0]
        A_score, B_score = data["A_score"], data["B_score"]
        A_terr, B_terr = data["A_terr"], data["B_terr"]
        A_alive, B_alive = data["A_alive_ticks"], data["B_alive_ticks"]
        winner = data["winner"]

        for name in (a_name,b_name): stats[name]["games"] += 1
        if winner == "A":
            stats[a_name]["wins"] += 1; stats[b_name]["losses"] += 1
        elif winner == "B":
            stats[b_name]["wins"] += 1; stats[a_name]["losses"] += 1
        else:
            stats[a_name]["ties"] += 1; stats[b_name]["ties"] += 1
        stats[a_name]["score_diff"] += (A_score - B_score)
        stats[b_name]["score_diff"] += (B_score - A_score)
        stats[a_name]["terr_diff"]  += (A_terr - B_terr)
        stats[b_name]["terr_diff"]  += (B_terr - A_terr)
        stats[a_name]["survive_ticks"] += A_alive
        stats[b_name]["survive_ticks"] += B_alive

    rows = []
    for name, s in stats.items():
        gp = max(1, s["games"])
        rows.append({
            "agent": name, "gp": s["games"],
            "w": s["wins"], "l": s["losses"], "t": s["ties"],
            "winrate": (s["wins"] + 0.5*s["ties"]) / gp,
            "avg_score_diff": s["score_diff"]/gp,
            "avg_terr_diff": s["terr_diff"]/gp,
            "avg_survive_ticks": s["survive_ticks"]/gp
        })
    rows.sort(key=lambda r: (r["winrate"], r["avg_score_diff"], r["avg_survive_ticks"]), reverse=True)

    with open(out_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["agent","gp","w","l","t","winrate","avg_score_diff","avg_terr_diff","avg_survive_ticks"])
        for r in rows:
            w.writerow([r["agent"], r["gp"], r["w"], r["l"], r["t"], f"{r['winrate']:.3f}",
                        f"{r['avg_score_diff']:.2f}", f"{r['avg_terr_diff']:.2f}", f"{r['avg_survive_ticks']:.1f}"])
    if out_md:
        with open(out_md,"w") as f:
            f.write("| agent | gp | w | l | t | winrate | Δscore | Δterr | survive |\n")
            f.write("|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n")
            for r in rows:
                f.write(f"| {r['agent']} | {r['gp']} | {r['w']} | {r['l']} | {r['t']} | {r['winrate']:.3f} | {r['avg_score_diff']:.2f} | {r['avg_terr_diff']:.2f} | {r['avg_survive_ticks']:.1f} |\n")

def balanced_pair(a, b, seeds, outdir, built_map, params=None):
    aN = normalize_player(a, built_map)
    bN = normalize_player(b, built_map)
    runs = []
    for s in seeds:
        runs.append(run_game(aN, bN, s, outdir, params=params, swap=False))
        runs.append(run_game(bN, aN, s, outdir, params=params, swap=True))
    return runs

def round_robin(players, seeds, outdir, built_map, params=None):
    runs = []
    for i in range(len(players)):
        for j in range(i+1, len(players)):
            a, b = players[i], players[j]
            runs += balanced_pair(a, b, seeds, outdir, built_map, params=params)
    return runs

def single_elim(players, seeds, outdir, built_map, params=None, best_of=3):
    bracket = list(players)
    runs = []
    rnd = 1
    while len(bracket) > 1:
        nxt = []
        for i in range(0, len(bracket), 2):
            if i+1 >= len(bracket):
                nxt.append(bracket[i]); continue
            A, B = bracket[i], bracket[i+1]
            series_dir = Path(outdir) / f"elim_r{rnd}_{A}_vs_{B}"
            series_dir.mkdir(parents=True, exist_ok=True)

            wins = Counter(); score_acc = {A:0, B:0}
            for k in range(best_of):
                s = seeds[k % len(seeds)]
                pair_runs = balanced_pair(A, B, [s], series_dir, built_map, params=params)
                runs += pair_runs

            # tally from produced summaries
            for sfile in series_dir.rglob("summary.json"):
                d = parse_summary(sfile)
                tag = sfile.parent.name
                a_name = tag.split("__vs__")[0]
                b_name = tag.split("__vs__")[1].split("__seed-")[0]
                if a_name == A and b_name == B:
                    if d["winner"] == "A": wins[A]+=1
                    elif d["winner"] == "B": wins[B]+=1
                    score_acc[A] += d["A_score"]; score_acc[B] += d["B_score"]
                elif a_name == B and b_name == A:
                    if d["winner"] == "A": wins[B]+=1
                    elif d["winner"] == "B": wins[A]+=1
                    score_acc[A] += d["B_score"]; score_acc[B] += d["A_score"]
            series_winner = max([A,B], key=lambda x: (wins[x], score_acc[x]))
            nxt.append(series_winner)
        bracket = nxt
        rnd += 1
    return runs

def _parse_players(s): return [x.strip() for x in s.split(",") if x.strip()]
def _parse_seeds(s):
    if ".." in s:
        lo, hi = s.split(".."); return list(range(int(lo), int(hi)+1))
    return [int(x) for x in s.split(",") if x]

def main():
    ap = argparse.ArgumentParser(prog="btctl", description="BATTLE controller (build.sh only)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ap_build = sub.add_parser("build", help="Build custom agents from roster.json")
    ap_build.add_argument("--out", default=str(ROOT/"agents_build"))

    ap_smoke = sub.add_parser("smoke", help="Quick position-balanced smoke vs built-ins")
    ap_smoke.add_argument("--players", default="chatgpt_hunter,claude_agent")
    ap_smoke.add_argument("--seeds", default="1,2,3")
    ap_smoke.add_argument("--out", default=str(OUTROOT / f"smoke-{int(time.time())}"))

    ap_sweep = sub.add_parser("sweep", help="Seed sweep for a vs b (position-balanced)")
    ap_sweep.add_argument("--a", required=True)
    ap_sweep.add_argument("--b", required=True)
    ap_sweep.add_argument("--seeds", default="1..32")
    ap_sweep.add_argument("--out", default=str(OUTROOT / f"sweep-{int(time.time())}"))

    ap_rr = sub.add_parser("roundrobin", help="Round-robin (position-balanced)")
    ap_rr.add_argument("--players", default="runner,writer,bomber,flooder,spiral,seeker,chatgpt_hunter,claude_agent")
    ap_rr.add_argument("--seeds", default="1..8")
    ap_rr.add_argument("--out", default=str(OUTROOT / f"rr-{int(time.time())}"))

    ap_elim = sub.add_parser("elim", help="Single-elim tournament")
    ap_elim.add_argument("--players", default="runner,writer,bomber,flooder,spiral,seeker,chatgpt_hunter,claude_agent")
    ap_elim.add_argument("--seeds", default="1..4")
    ap_elim.add_argument("--best-of", type=int, default=3)
    ap_elim.add_argument("--out", default=str(OUTROOT / f"elim-{int(time.time())}"))

    ap_report = sub.add_parser("report", help="Aggregate CSV + leaderboard from results tree")
    ap_report.add_argument("--in", dest="indir", required=True)
    ap_report.add_argument("--csv", dest="csv", default="leaderboard.csv")
    ap_report.add_argument("--md", dest="md", default="leaderboard.md")

    for p in (ap_smoke, ap_sweep, ap_rr, ap_elim):
        p.add_argument("--arena", type=int, default=DEF["arena"])
        p.add_argument("--ticks", type=int, default=DEF["ticks"])
        p.add_argument("--win-mode", default=DEF["win_mode"])
        p.add_argument("--territory-w", type=int, default=DEF["territory_w"])
        p.add_argument("--territory-bucket", type=int, default=DEF["territory_bucket"])

    args = ap.parse_args()
    builtins, customs = load_roster()
    built_map = {c["name"]: str((ROOT/"agents_build"/f"{c['name']}.blob")) for c in customs}

    if args.cmd == "build":
        built = build_customs(customs, args.out)
        print(json.dumps(built, indent=2)); return

    # Ensure customs are built
    if customs:
        build_customs(customs, ROOT/"agents_build")

    if args.cmd == "smoke":
        players = _parse_players(args.players)
        seeds = _parse_seeds(args.seeds)
        params = dict(arena=args.arena, ticks=args.ticks, win_mode=args.win_mode,
                      territory_w=args.territory_w, territory_bucket=args.territory_bucket)
        runs = []
        for p in players:
            for q in builtins:
                if p == q: continue
                runs += balanced_pair(p, q, seeds, args.out, built_map, params=params)
        write_match_csv(runs, Path(args.out)/"smoke.csv")
        aggregate_leaderboard(args.out, Path(args.out)/"leaderboard.csv", Path(args.out)/"leaderboard.md")
        return

    if args.cmd == "sweep":
        seeds = _parse_seeds(args.seeds)
        params = dict(arena=args.arena, ticks=args.ticks, win_mode=args.win_mode,
                      territory_w=args.territory_w, territory_bucket=args.territory_bucket)
        runs = balanced_pair(args.a, args.b, seeds, args.out, built_map, params=params)
        write_match_csv(runs, Path(args.out)/f"{args.a}-vs-{args.b}.csv")
        aggregate_leaderboard(args.out, Path(args.out)/"leaderboard.csv", Path(args.out)/"leaderboard.md")
        return

    if args.cmd == "roundrobin":
        players = _parse_players(args.players)
        seeds = _parse_seeds(args.seeds)
        params = dict(arena=args.arena, ticks=args.ticks, win_mode=args.win_mode,
                      territory_w=args.territory_w, territory_bucket=args.territory_bucket)
        runs = round_robin(players, seeds, args.out, built_map, params=params)
        write_match_csv(runs, Path(args.out)/"roundrobin.csv")
        aggregate_leaderboard(args.out, Path(args.out)/"leaderboard.csv", Path(args.out)/"leaderboard.md")
        return

    if args.cmd == "elim":
        players = _parse_players(args.players)
        seeds = _parse_seeds(args.seeds)
        params = dict(arena=args.arena, ticks=args.ticks, win_mode=args.win_mode,
                      territory_w=args.territory_w, territory_bucket=args.territory_bucket)
        runs = single_elim(players, seeds, args.out, built_map, params=params, best_of=args.best_of)
        write_match_csv(runs, Path(args.out)/"elim.csv")
        aggregate_leaderboard(args.out, Path(args.out)/"leaderboard.csv", Path(args.out)/"leaderboard.md")
        return

    if args.cmd == "report":
        aggregate_leaderboard(args.indir, args.csv, args.md)
        return

if __name__ == "__main__":
    main()

