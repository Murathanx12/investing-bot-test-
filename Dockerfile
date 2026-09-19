# The unattended loop, containerised. One service per ACCOUNT ROLE.
#
#   railway up                                   (from this directory, project linked)
#   railway variables set AAT_ACCOUNT_ROLE=dev AAT_DEV_KEY_ID=... AAT_DEV_SECRET_KEY=... \
#       AAT_DEEPSEEK_API_KEY=... AAT_FINNHUB_API_KEY=... AAT_FRED_API_KEY=... AAT_LOOP_EXPIRY=2026-08-28
#
# The ledgers live in /app/state; mount a Railway volume there or the chain
# restarts from genesis on every deploy (the parent project lost `options_pit`
# exactly this way -- a store whose count never grows is RESET, not quiet).
# NEVER run the same role from two hosts at once: two writers, one book.
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PYTHONUNBUFFERED=1
# --brains/--shadow come from AAT_LOOP_BRAINS / AAT_LOOP_SHADOW so dev and exp1
# differ by variables only, not by image.
# Genesis records (and the whole-market universe) are committed under docs/seed/ (a birth certificate that
# only exists on one laptop is not evidence) and SEEDED into the volume on
# start, never overwritten: the volume is the ledger, the repo is the seed.
COPY docs/seed/ /app/seed/
# AAT_LOOP_ARGS carries the flags the runbook prescribes for the role, e.g.
#   --profile conservative --brains post_event_drift --shadow "" --window-universe
# 2026-09-20: the loop runs only inside the market window (Mon-Fri 13:00-22:10Z
# by default, AAT_WINDOW_OPEN_UTC / AAT_WINDOW_CLOSE_UTC) and this container
# sleeps as a few-megabyte shell outside it -- Railway bills memory per second
# and an idle loop held 1.16 GB all night. The loop command inside the wrapper
# is the old CMD verbatim. See scripts/market_window.sh.
CMD ["sh", "/app/scripts/market_window.sh"]
