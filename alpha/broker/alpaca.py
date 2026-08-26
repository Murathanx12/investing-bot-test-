"""The only path to Alpaca. Paper-only, idempotent, and it records the quote.

WHY THIS EXISTS RATHER THAN CALLING `alpaca-py` DIRECTLY
========================================================
Three things have to be true of every order this agent sends, and none of them
is true of a bare SDK call:

1. **It cannot reach a live account.** Enforced in `alpha.config` at the host
   level, re-asserted here, and additionally checked against the account object
   itself -- a paper key against a paper host still gets verified once at
   startup, because two independent checks that agree are worth more than one
   check you trust.

2. **It cannot be sent twice.** A tournament agent restarts. Railway redeploys,
   a websocket drops, a loop retries. Every order carries a deterministic
   `client_order_id` derived from the decision it implements, so a replay after
   a crash collides with the original instead of doubling the position. Alpaca
   rejects the duplicate; that rejection is the guard working, not an error.

3. **The quote at decision time is stored with it.** The competition runs in a
   paper environment that, by Alpaca's own documentation, does not model market
   impact, latency, queue position, or order size against displayed NBBO
   quantity. That means a large order in a thin option can be filled at a price
   nobody could have got. We are not going to find out how good that exploit is:
   every order records the bid, the ask and the size we saw, so the fill can be
   audited against a quote that actually existed. The evidence has to survive
   the competition and be worth importing back into the research project, and
   evidence from a gamed simulator is worth nothing.
"""

from __future__ import annotations

import hashlib
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from alpha import config

logger = logging.getLogger(__name__)


class BrokerRefusal(RuntimeError):
    """An order or account state that this agent will not act on."""


@dataclass
class AlpacaPaper:
    """A paper trading client scoped to ONE declared account role."""

    role: str | None = None
    timeout: float = 15.0
    _creds: config.Credentials = field(init=False, repr=False)
    _verified: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        self._creds = config.credentials(self.role)

    # ---------------------------------------------------------------- transport
    def _request(self, method: str, path: str, *, base: str | None = None, body: Any = None,
                 params: dict[str, Any] | None = None, timeout: float | None = None) -> Any:
        root = base or config.base_url()
        url = f"{root}{path}"
        if params:
            clean = {k: v for k, v in params.items() if v is not None}
            url = f"{url}?{urllib.parse.urlencode(clean)}"

        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        for k, v in self._creds.headers.items():
            req.add_header(k, v)
        req.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:500]
            raise BrokerRefusal(f"{method} {path} -> HTTP {exc.code}: {detail}") from exc

    # ------------------------------------------------------------------ account
    def account(self) -> dict[str, Any]:
        acct = self._request("GET", "/v2/account")
        if not self._verified:
            self._verify_paper(acct)
        return acct

    def _verify_paper(self, acct: dict[str, Any]) -> None:
        """Third check: the account object must say it is paper.

        `config` already allowlisted the host and the credential namespace is
        segregated. This asks the SERVER, because the two local checks share a
        failure mode -- a developer who exports the wrong thing exports it
        everywhere -- and the server does not.
        """
        number = str(acct.get("account_number", ""))
        # Alpaca paper account numbers are prefixed `PA`. A live account is not.
        if not number.startswith("PA"):
            raise BrokerRefusal(
                f"Account {number!r} does not look like a paper account (expected a "
                "'PA' prefix). Refusing every subsequent call. If this is genuinely "
                "a paper account whose numbering changed, verify by hand -- do not "
                "relax this check to make a run start."
            )
        if acct.get("status") != "ACTIVE":
            logger.warning("account status is %s, not ACTIVE", acct.get("status"))
        self._verified = True
        logger.info("verified paper account %s (role=%s)", number, self._creds.role)

    def positions(self) -> list[dict[str, Any]]:
        return self._request("GET", "/v2/positions") or []

    def orders(self, status: str = "open", limit: int = 200) -> list[dict[str, Any]]:
        return self._request("GET", "/v2/orders", params={"status": status, "limit": limit}) or []

    def clock(self) -> dict[str, Any]:
        return self._request("GET", "/v2/clock")

    def assets(self, *, status: str = "active", asset_class: str = "us_equity") -> list[dict[str, Any]]:
        """Every asset the venue lists -- the raw material of a universe that is
        not "the names with good option chains"."""
        return self._request("GET", "/v2/assets", params={"status": status, "asset_class": asset_class}) or []

    def stock_bars_multi(self, symbols: list[str], *, start: str, timeframe: str = "1Day",
                         adjustment: str = "all", end: str | None = None,
                         page_limit: int = 10000, feed: str = "sip",
                         batch_size: int = 100) -> dict[str, list[dict[str, Any]]]:
        """Daily bars for MANY symbols, following `next_page_token` to the end.
        Symbols are sent in batches so the URL stays inside the venue's limit.

        DEFAULT FEED IS SIP, deliberately. Measured 2026-08-26: the free plan
        serves HISTORICAL bars from the consolidated tape, and the IEX feed's
        volume is IEX's own (~2-4% of consolidated: NTLA $2.0M vs $48.8M a day).
        A dollar-volume screen on IEX bars is a screen on a different market."""
        import time

        out: dict[str, list[dict[str, Any]]] = {}
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i + batch_size]
            token = None
            while True:
                data = None
                for attempt in range(4):
                    try:
                        data = self._request(
                            "GET", "/v2/stocks/bars", base=config.data_url(), timeout=90.0,
                            params={"symbols": ",".join(batch), "start": start, "end": end, "timeframe": timeframe,
                                    "adjustment": adjustment, "limit": page_limit, "feed": feed,
                                    "page_token": token})
                        break
                    except (TimeoutError, OSError, BrokerRefusal) as exc:
                        # A multi-year page for 100 names can exceed the venue's patience; a
                        # transient failure here must not restart a 3,000-name scan from zero.
                        if attempt == 3:
                            raise
                        logger.warning("bars page retry %d for %d symbols: %s", attempt + 1, len(batch), str(exc)[:80])
                        time.sleep(2.0 * (attempt + 1))
                for sym, bars in (data.get("bars") or {}).items():
                    out.setdefault(sym, []).extend(bars)
                token = data.get("next_page_token")
                if not token:
                    break
        return out

    def asset(self, symbol: str) -> dict[str, Any]:
        """The venue's own record of an asset: `tradable`, `shortable`, `easy_to_borrow`.

        Asked before a short share structure is BUILT, so a name the venue will
        not lend is never enumerated rather than rejected at the order."""
        return self._request("GET", f"/v2/assets/{urllib.parse.quote(symbol)}") or {}

    # ------------------------------------------------------------- market data
    def option_chain(self, underlying: str, *, expiration_gte: str | None = None,
                     expiration_lte: str | None = None, feed: str | None = None,
                     strike_gte: float | None = None, strike_lte: float | None = None,
                     limit: int = 1000) -> dict[str, Any]:
        """Chain snapshot: quotes, greeks and implied vol per contract.

        The feed is DECLARED by configuration rather than hardcoded. Asking for
        `opra` without the Algo Trader Plus subscription returns 403 with the
        message "OPRA agreement is not signed", which reads like a paperwork
        problem and is actually a billing one -- so the refusal below says what
        it really means rather than passing the venue's wording through.
        """
        try:
            return self._request(
                "GET", f"/v1beta1/options/snapshots/{underlying}",
                base=config.data_url(),
                params={
                    "feed": feed or config.options_feed(),
                    "expiration_date_gte": expiration_gte,
                    "expiration_date_lte": expiration_lte,
                    "strike_price_gte": strike_gte,
                    "strike_price_lte": strike_lte,
                    "limit": limit,
                },
            )
        except BrokerRefusal as exc:
            if "OPRA agreement" in str(exc):
                raise BrokerRefusal(
                    "Real-time OPRA option data was requested but this account is on "
                    "the free plan. Alpaca reports this as \"OPRA agreement is not "
                    "signed\"; it means the Algo Trader Plus subscription ($99/mo) is "
                    "absent, and no agreement can be signed to avoid it. Set "
                    "AAT_OPTIONS_FEED=indicative to use the delayed feed."
                ) from exc
            raise

    def option_quotes(self, symbols: list[str]) -> dict[str, Any]:
        """Latest quotes for specific OCC contracts.

        The chain endpoint answers "what is available around this strike"; this
        answers "what is THIS contract worth now", which is the question a
        counterfactual asks about a leg it never bought. Batched in hundreds
        because the URL is the limit, not the plan.
        """
        out: dict[str, Any] = {}
        for i in range(0, len(symbols), 100):
            batch = symbols[i:i + 100]
            page = self._request(
                "GET", "/v1beta1/options/quotes/latest",
                base=config.data_url(),
                params={"symbols": ",".join(batch), "feed": config.options_feed()},
            )
            out.update(page.get("quotes") or {})
        return out

    def stock_quote(self, symbols: list[str]) -> dict[str, Any]:
        return self._request(
            "GET", "/v2/stocks/quotes/latest",
            base=config.data_url(),
            params={"symbols": ",".join(symbols), "feed": config.stock_feed()},
        )

    def latest_trade(self, symbols: list[str]) -> dict[str, Any]:
        """Last trade print. The PRIMARY source for a live underlying price.

        Preferred over the quote because on the free IEX feed a quote is often
        one-sided -- measured on this account, AVGO came back with a bid and an
        ask of exactly zero while SPY was clean. A trade has no sides.
        """
        return self._request(
            "GET", "/v2/stocks/trades/latest",
            base=config.data_url(),
            params={"symbols": ",".join(symbols), "feed": config.stock_feed()},
        )

    def stock_bars(self, symbol: str, *, start: str, timeframe: str = "1Day",
                   adjustment: str = "all", limit: int = 1000) -> dict[str, Any]:
        """Historical bars. `adjustment="all"` is not optional -- see vol_gap."""
        return self._request(
            "GET", "/v2/stocks/bars",
            base=config.data_url(),
            params={"symbols": symbol, "start": start, "timeframe": timeframe,
                    "adjustment": adjustment, "limit": limit, "feed": config.stock_feed()},
        )

    def crypto_quote(self, symbols: list[str]) -> dict[str, Any]:
        """Crypto is real-time and free, and it is the ONLY market open on the
        weekend of 29-30 August -- two of the competition's eight days."""
        return self._request(
            "GET", "/v1beta3/crypto/us/latest/quotes",
            base=config.data_url(), params={"symbols": ",".join(symbols)},
        )

    # ----------------------------------------------------------------- ordering
    def submit(self, order: dict[str, Any], *, decision_id: str,
               quote_snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
        """Send one order, keyed to the decision that produced it.

        `decision_id` makes the submission idempotent. Two calls carrying the
        same decision produce the same `client_order_id`, and the second is
        rejected by Alpaca rather than filled -- which is the correct outcome
        after a crash-restart and is why the id is derived, not generated.
        """
        if quote_snapshot is None:
            raise BrokerRefusal(
                "submit() requires the quote seen at decision time. An order whose "
                "fill cannot be audited against a quote that existed is not evidence, "
                "and this account's record is the deliverable."
            )
        payload = dict(order)
        payload["client_order_id"] = client_order_id(decision_id)
        if payload.get("extended_hours"):
            # Alpaca rejects extended-hours option orders; catching it here gives a
            # readable refusal instead of an opaque 422 mid-session.
            if _is_option(payload.get("symbol", "")) or payload.get("legs"):
                raise BrokerRefusal("options cannot be routed extended-hours.")
        logger.info("submitting %s (decision=%s)", payload.get("symbol") or "multileg", decision_id)
        return self._request("POST", "/v2/orders", body=payload)

    def close_position(self, symbol: str, *, percentage: str | None = None) -> dict[str, Any]:
        return self._request(
            "DELETE", f"/v2/positions/{urllib.parse.quote(symbol)}",
            params={"percentage": percentage},
        )


def client_order_id(decision_id: str) -> str:
    """Deterministic, <=48 chars, collides on replay by design."""
    digest = hashlib.sha256(decision_id.encode()).hexdigest()[:32]
    return f"aat-{digest}"


def _is_option(symbol: str) -> bool:
    """OCC symbols are 15+ chars ending in an 8-digit strike; equities are not."""
    return len(symbol) >= 15 and symbol[-8:].isdigit()
