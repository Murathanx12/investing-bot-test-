"""External, non-trading data sources. Each adapter is MEASURED before it is
trusted: `probe()` on every module returns (ok, latency_s, detail) from a real
request, and `docs/SOURCES.md` records the measurement. A source that was not
probed today is not a source."""
