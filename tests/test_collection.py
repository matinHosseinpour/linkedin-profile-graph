from types import SimpleNamespace
from urllib.robotparser import RobotFileParser

import pytest
import requests

from linkedin_graph.collect import CollectionError, PublicClient, collect_profiles

URL = "https://www.linkedin.com/in/alex-fixture"


class Response:
    def __init__(self, body="", status=200, headers=None):
        self.body = body.encode()
        self.status_code = status
        self.headers = headers or {"Content-Type": "text/html"}
        self.encoding = "utf-8"
        self.closed = False

    def iter_content(self, size):
        yield self.body

    def close(self):
        self.closed = True


class Session:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.headers = {}
        self.cookies = SimpleNamespace(clear=lambda: None)
        self.calls = []

    def get(self, url, **options):
        self.calls.append((url, options))
        value = next(self.responses)
        if isinstance(value, Exception):
            raise value
        return value


@pytest.mark.parametrize("status", [401, 403, 429, 999])
def test_access_denial_stops_batch_without_retry(status, tmp_path):
    session = Session(
        [
            Response("User-agent: *\nAllow: /", headers={"Content-Type": "text/plain"}),
            Response(status=status, headers={"Retry-After": "120"}),
        ]
    )
    client = PublicClient(session=session, sleep=lambda _: None)
    profiles, receipt = collect_profiles([URL, URL + "-2"], tmp_path, client=client)
    assert profiles == []
    assert len(session.calls) == 2  # Robots and one profile, no second profile request.
    assert receipt["saved"] == 0
    assert receipt["not_attempted"] == 1
    assert receipt["retry_after"] == "120"
    assert receipt["acquisition_complete"] is False


def test_robots_denial_makes_no_profile_request(tmp_path):
    session = Session([Response("User-agent: *\nDisallow: /")])
    client = PublicClient(session=session)
    profiles, receipt = collect_profiles([URL], tmp_path, client=client)
    assert profiles == []
    assert len(session.calls) == 1
    assert receipt["results"][0]["reason"] == "robots_disallowed"


def test_robots_failure_is_fail_closed(tmp_path):
    session = Session([Response(status=503)])
    profiles, receipt = collect_profiles([URL], tmp_path, client=PublicClient(session=session))
    assert profiles == []
    assert receipt["run_error"] == "robots_unavailable"
    assert len(session.calls) == 1


def test_rate_limiter_and_timeouts_cover_each_request():
    session = Session([Response("first"), Response("second")])
    waits = []
    client = PublicClient(interval=7, session=session, sleep=waits.append, clock=lambda: 0)
    client.get(URL)
    client.get(URL + "-2")
    assert waits == [7]
    assert session.calls[0][1]["timeout"] == (10, 25)
    assert session.calls[0][1]["allow_redirects"] is False
    assert session.calls[0][1]["stream"] is True


@pytest.mark.parametrize(
    "destination", ["https://evil.test/in/person", "/authwall", "http://www.linkedin.com/in/person"]
)
def test_redirect_cannot_escape_host_or_access_gate(destination):
    session = Session([Response(status=302, headers={"Location": destination})])
    with pytest.raises(CollectionError):
        PublicClient(session=session).get(URL)
    assert len(session.calls) == 1


def test_network_exception_is_safely_recorded(tmp_path):
    session = Session([Response("User-agent: *\nAllow: /"), requests.Timeout("detail")])
    _, receipt = collect_profiles(
        [URL], tmp_path, client=PublicClient(session=session, sleep=lambda _: None)
    )
    assert receipt["results"][0]["reason"] == "network_error"


def test_success_persists_only_sanitized_sources(tmp_path):
    html = "<h1>Alex Fixture</h1><script>SESSION_SENTINEL</script>"
    session = Session([Response("User-agent: *\nAllow: /"), Response(html)])
    profiles, receipt = collect_profiles(
        [URL], tmp_path, client=PublicClient(session=session, sleep=lambda _: None)
    )
    assert len(profiles) == 1
    assert receipt["acquisition_complete"] is True
    assert receipt["profile_completeness_established"] is False
    assert "SESSION_SENTINEL" not in (tmp_path / "sources/alex-fixture.html").read_text()


def test_missing_robots_is_allowed_and_delay_is_honored():
    client = PublicClient(session=Session([Response(status=404)]))
    assert isinstance(client.robots(), RobotFileParser)
    client = PublicClient(session=Session([Response("User-agent: *\nCrawl-delay: 12\nAllow: /")]))
    client.robots()
    assert client.interval == 12
