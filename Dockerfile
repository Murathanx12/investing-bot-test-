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
CMD ["sh", "-c", "python -m scripts.agent_loop --expiry ${AAT_LOOP_EXPIRY} --live ${AAT_LOOP_BRAINS:+--brains $AAT_LOOP_BRAINS} ${AAT_LOOP_SHADOW:+--shadow $AAT_LOOP_SHADOW}"]
