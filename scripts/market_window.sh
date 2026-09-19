#!/bin/sh
# THE MARKET-WINDOW SUPERVISOR (2026-09-20).
#
# Railway bills memory per second, and an idle `scripts.agent_loop` holds about
# 1.16 GB (pandas, numpy, the venue client) for the fifteen hours a day and the
# two days a week when nothing can be decided. Measured 2026-09-20 with
# `railway metrics --service aat-loop-hack3`: 1.16 GB resident, <0.01 vCPU
# average. Six of those plus the authority and the website backend were the
# ~$50/month Murat asked to cut ("it doesn't have to run all the time, only
# decisions or while market open in intervals").
#
# So the loop runs only INSIDE THE WINDOW and this shell sleeps outside it.
# A sleeping `sh` is a few megabytes; the saving is the whole idle memory.
#
# THE WINDOW, in UTC because the container's clock is UTC and the venue's
# session is what matters:
#   Mon-Fri 13:00 -> 22:10 by default (AAT_WINDOW_OPEN_UTC / AAT_WINDOW_CLOSE_UTC
#   as HHMM). 13:00Z is 09:00 ET in summer and 08:00 ET in winter; 22:10Z is
#   18:10 ET in summer and 17:10 ET in winter. Both sides of the DST change are
#   covered by one pair of numbers, including the 15:30 ET next-session entry
#   and the after-close exit checks the loop runs. Holidays are NOT decided
#   here: inside the window the loop asks the venue clock itself and idles
#   cheaply when it says CLOSED, exactly as before.
#
# WHAT DOES NOT CHANGE: the loop's own code, cadence and flags. The command
# below is the Dockerfile's old CMD, verbatim, under `timeout`.
#
# WHAT CHANGES FOR LIVENESS: at the window's close the loop is stopped with
# SIGTERM and its heartbeat is RETIRED (`alpha.liveness.retire`), because a
# loop stopped on purpose at a declared time is not a dead loop, and a stale
# receipt left behind would make the next `liveness.report()` say DEAD -- the
# false alarm that module exists to prevent. The retirement is logged with the
# window that caused it, so the record says why the beat is absent.
#
# `set -u` is deliberate: an unset AAT_LOOP_EXPIRY is a misconfigured service
# and must fail loudly at the first cycle, not run with an empty flag.
set -u

mkdir -p /app/state && cp -rn /app/seed/. /app/state/ 2>/dev/null

OPEN="${AAT_WINDOW_OPEN_UTC:-1300}"
CLOSE="${AAT_WINDOW_CLOSE_UTC:-2210}"
ROLE="${AAT_ACCOUNT_ROLE:-unset}"

echo "MARKET WINDOW supervisor: role=${ROLE} window=${OPEN}-${CLOSE}Z Mon-Fri; outside it this process sleeps"

while true; do
  dow=$(date -u +%u)          # 1 = Monday ... 7 = Sunday
  hm=$(date -u +%H%M)
  # AAT_WINDOW_WEEKENDS=1 is for a REHEARSAL on a weekend (the loop then asks
  # the venue clock and idles); never set it on a deployed service.
  weekday_ok=0
  if [ "$dow" -le 5 ] || [ "${AAT_WINDOW_WEEKENDS:-0}" = "1" ]; then weekday_ok=1; fi
  if [ "$weekday_ok" -eq 1 ] && [ "$hm" -ge "$OPEN" ] && [ "$hm" -lt "$CLOSE" ]; then
    now_s=$(date -u +%s)
    close_s=$(date -u -d "today ${CLOSE%??}:${CLOSE#??}" +%s)
    budget=$((close_s - now_s))
    if [ "$budget" -le 0 ]; then budget=60; fi
    echo "MARKET WINDOW open at $(date -u +%FT%TZ): running the loop for ${budget}s (until ${CLOSE}Z)"
    # The sealed-book poller (scripts/prediction_book_sync.py, a no-op without
    # AAT_PREDICTION_BOOK_BASE_URL) -- formerly started by a dashboard-only
    # start command on three services -- runs beside the loop, inside the
    # window only, and is stopped with it.
    python -m scripts.prediction_book_sync &
    poller_pid=$!
    # shellcheck disable=SC2086  -- AAT_LOOP_ARGS is a flag list by contract.
    timeout -s TERM "$budget" python -m scripts.agent_loop --expiry "${AAT_LOOP_EXPIRY}" --live \
      ${AAT_LOOP_BRAINS:+--brains "$AAT_LOOP_BRAINS"} ${AAT_LOOP_SHADOW:+--shadow "$AAT_LOOP_SHADOW"} \
      ${AAT_LOOP_ARGS:-}
    rc=$?
    kill "$poller_pid" 2>/dev/null; wait "$poller_pid" 2>/dev/null
    echo "MARKET WINDOW loop exited rc=${rc} at $(date -u +%FT%TZ) (124 = stopped at the window's close)"
    python -c "from alpha import liveness; print('MARKET WINDOW retired heartbeat:', liveness.retire('${ROLE}'))" || true
    # A loop that died INSIDE the window (rc != 124) is restarted by the outer
    # loop after a short pause -- the same restart-on-crash Railway's policy
    # gave the old always-on process, now with a pause so a crash-loop is
    # readable in the log rather than a blur.
    if [ "$rc" -ne 124 ]; then sleep 60; fi
  else
    sleep 300
  fi
done
