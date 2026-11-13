"""Small sequential guest HTTP collector; no login, cookies file, proxy rotation or evasion."""

import time
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import requests

from .common import dump_json, profile_url, utc_now
from .extract import access_problem, extract_profile, sanitize_html

USER_AGENT = "LinkedInProfileGraph/1.0 (local research project)"
MAX_BYTES = 5 * 1024 * 1024
STOP_STATUSES = {401, 403, 429, 999}


class CollectionError(Exception):
    def __init__(self, code, *, status=None, retry_after=None):
        super().__init__(code)
        self.code = code
        self.status = status
        self.retry_after = retry_after


class PublicClient:
    def __init__(self, interval=5, session=None, sleep=time.sleep, clock=time.monotonic):
        if interval < 5:
            raise ValueError("The minimum interval is 5 seconds")
        self.interval = interval
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,text/plain;q=0.8",
                "Accept-Language": "en-US,en;q=0.8",
            }
        )
        self.sleep = sleep
        self.clock = clock
        self.last_request = None

    def get(self, url):
        for _redirect in range(4):
            parts = urlsplit(url)
            if (
                parts.scheme != "https"
                or parts.hostname not in {"www.linkedin.com", "linkedin.com"}
                or parts.username
                or parts.password
                or parts.port not in {None, 443}
            ):
                raise CollectionError("unsafe_redirect")
            if any(p in parts.path for p in ("/authwall", "/login", "/checkpoint", "/uas/")):
                raise CollectionError("authentication_or_access_restricted")
            if self.last_request is not None:
                self.sleep(max(0, self.interval - (self.clock() - self.last_request)))
            self.last_request = self.clock()
            try:
                response = self.session.get(
                    url, timeout=(10, 25), allow_redirects=False, stream=True
                )
            except requests.RequestException:
                raise CollectionError("network_error") from None
            try:
                status = response.status_code
                if status in STOP_STATUSES:
                    # Persist the server's delay as a receipt; leave later retries to the caller.
                    retry_after = response.headers.get("Retry-After")
                    if retry_after and len(retry_after) > 100:
                        retry_after = None
                    raise CollectionError(
                        "access_restricted" if status != 429 else "rate_limited",
                        status=status,
                        retry_after=retry_after,
                    )
                if status in {301, 302, 303, 307, 308}:
                    if not response.headers.get("Location"):
                        raise CollectionError("redirect_without_location", status=status)
                    url = urljoin(url, response.headers["Location"])
                    continue
                if status >= 500:
                    raise CollectionError("server_error", status=status)
                if status >= 400:
                    raise CollectionError("http_error", status=status)
                chunks, length = [], 0
                deadline = self.clock() + 60
                for chunk in response.iter_content(65536):
                    length += len(chunk)
                    if length > MAX_BYTES or self.clock() > deadline:
                        raise CollectionError("response_limit_exceeded", status=status)
                    chunks.append(chunk)
                body = b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")
                return body, response.headers.get("Content-Type", ""), url
            finally:
                response.close()
                self.session.cookies.clear()
        raise CollectionError("too_many_redirects")

    def robots(self):
        url = "https://www.linkedin.com/robots.txt"
        try:
            body, _, _ = self.get(url)
        except CollectionError as error:
            if error.status == 404:
                body = ""  # No robots file; ordinary HTTP checks still apply.
            else:
                raise CollectionError(
                    "robots_unavailable", status=error.status, retry_after=error.retry_after
                ) from error
        rules = RobotFileParser(url)
        rules.parse(body.splitlines())
        self.interval = max(self.interval, rules.crawl_delay(USER_AGENT) or 0)
        rate = rules.request_rate(USER_AGENT)
        if rate and rate.requests:
            self.interval = max(self.interval, rate.seconds / rate.requests)
        return rules


def collect_profiles(urls, output_dir, *, interval=5, client=None):
    """Write a receipt even when all URLs fail. Never mix a previous run's data in."""
    urls = list(dict.fromkeys(profile_url(u) for u in urls))
    if not urls:
        raise ValueError("The URL list is empty")
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    profiles, receipts, manifest = [], [], []
    client = client or PublicClient(interval)
    fatal = None
    try:
        rules = client.robots()
    except CollectionError as error:
        rules = None
        fatal = error
    for url in urls:
        if fatal:
            receipts.append({"url": url, "status": "not_attempted", "reason": fatal.code})
            continue
        if not rules.can_fetch(USER_AGENT, url):
            receipts.append({"url": url, "status": "blocked", "reason": "robots_disallowed"})
            continue
        try:
            html, content_type, final_url = client.get(url)
            if "html" not in content_type.casefold():
                raise CollectionError("unexpected_content_type")
            if problem := access_problem(html, final_url):
                raise CollectionError(problem)
            if profile_url(final_url) != url:
                raise CollectionError("profile_identity_redirect")
            snapshot = sanitize_html(html)
            profile = extract_profile(snapshot, url, source_kind="public_http")
            filename = f"sources/{profile['id']}.html"
            destination = out / filename
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(snapshot, encoding="utf-8")
            profiles.append(profile)
            manifest.append(
                {
                    "path": filename,
                    "url": url,
                    "is_synthetic": False,
                    "source_kind": "public_http",
                    "collected_at": profile["provenance"]["collected_at"],
                }
            )
            receipts.append({"url": url, "status": "saved", "path": filename})
        except (CollectionError, ValueError) as error:
            if not isinstance(error, CollectionError):
                error = CollectionError(str(error))
            receipts.append(
                {
                    "url": url,
                    "status": "failed",
                    "reason": error.code,
                    "http_status": error.status,
                    "retry_after": error.retry_after,
                }
            )
            if error.status in STOP_STATUSES or error.code in {
                "authentication_or_access_restricted",
                "unsafe_redirect",
            }:
                fatal = error
    receipt = {
        "collected_at": utc_now(),
        "requested": len(urls),
        "saved": len(profiles),
        "failed_or_blocked": sum(r["status"] in {"failed", "blocked"} for r in receipts),
        "not_attempted": sum(r["status"] == "not_attempted" for r in receipts),
        "acquisition_complete": len(profiles) == len(urls),
        "profile_completeness_established": False,
        "run_error": fatal.code if fatal else None,
        "retry_after": fatal.retry_after if fatal else None,
        "results": receipts,
    }
    dump_json(out / "profiles.json", profiles)
    dump_json(out / "manifest.json", manifest)
    dump_json(out / "collection_status.json", receipt)
    return profiles, receipt
