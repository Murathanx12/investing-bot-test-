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
# Genesis records are committed under docs/genesis/ (a birth certificate that
# only exists on one laptop is not evidence) and SEEDED into the volume on
# start, never overwritten: the volume is the ledger, the repo is the seed.
COPY docs/genesis/ /app/seed/
# AAT_LOOP_ARGS carries the flags the runbook prescribes for the role, e.g.
#   --profile conservative --brains post_event_drift --shadow "" --window-universe
CMD ["sh", "-c", "mkdir -p /app/state && cp -n /app/seed/*.json /app/state/ 2>/dev/null; exec python -m scripts.agent_loop --expiry ${AAT_LOOP_EXPIRY} --live ${AAT_LOOP_BRAINS:+--brains $AAT_LOOP_BRAINS} ${AAT_LOOP_SHADOW:+--shadow $AAT_LOOP_SHADOW} ${AAT_LOOP_ARGS}"]
