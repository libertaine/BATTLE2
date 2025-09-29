    BATTLE — Hunter Feedback Bundle
    Name: hunter_feedback_bundle
    Created: 2025-09-26 16:02:00
    Source results: /home/rod/Projects/BATTLE/results/hunter-20250926-155338

    Contents:
      - configs/run_notes.txt           # aggregated command lines used
      - results/<opponent>/seed-*/A|B/  # summary.json (+ stdout.log if included)
      - summary/summary.csv             # if present in results root
      - summary/leaderboard.txt         # if present in results root

    Stats:
      Opponents: bomber, flooder, runner, seeker, spiral, writer
      Seeds: seed-1, seed-2, seed-3, seed-4, seed-5
      Runs captured: 60
      Summaries: 1
      Logs included: yes (count=60)

    How to generate more data:
      - Use test_hunter.sh (set PARALLEL_JOBS for speed)
      - Ensure --record is on so summary.json is emitted
      - Re-run this collector to refresh the bundle

    How to share:
      - Send the ZIP (or .tar.gz) of this folder.
