import json
import math

from bs4 import BeautifulSoup

from linkedin_graph.analyze import build_graph
from linkedin_graph.extract import extract_profile, sanitize_html
from linkedin_graph.interactive import explorer_data, render_explorer


def person(slug, target="other", post_url="https://www.linkedin.com/feed/update/test"):
    html = f"""<h1>{slug}</h1><section id="activity"><ul class="activity__list"><li>
    <p class="activity-action">{slug} reposted this</p>
    <p class="activity-text">{'Captured professional post. ' * 20}</p>
    <a class="activity-target" href="https://www.linkedin.com/in/{target}">Author</a>
    <a href="{post_url}">Post</a></li></ul></section>"""
    return extract_profile(html, f"https://www.linkedin.com/in/{slug}")


def artifacts(profiles, selected_ids=None):
    graph, _, metadata = build_graph(profiles)
    selected_ids = selected_ids if selected_ids is not None else list(graph)
    return (
        {"metadata": metadata, "nodes": [{"id": node} for node in selected_ids], "edges": []},
        {"metadata": metadata, "nodes": [], "edges": []},
    )


def test_sanitization_keeps_captured_post_body_and_removes_executable_content():
    text = "A professional post with details. " * 30
    html = f"""<h1>Subject</h1><section id="activity"><li class="activity-item">
    <p class="activity-text" onclick="PRIVATE_SENTINEL">{text}</p>
    <script>PRIVATE_SENTINEL</script></li></section>"""
    sanitized = sanitize_html(html)
    profile = extract_profile(sanitized, "https://www.linkedin.com/in/subject")
    activity = profile["activity"][0]
    assert activity["captured_text"] == text.strip()
    assert len(activity["text"]) <= 90
    assert activity["text_truncated"] is True
    assert activity["captured_text_truncated"] is False
    assert "PRIVATE_SENTINEL" not in sanitized


def test_previously_abbreviated_source_remains_marked_in_details():
    html = """<h1>Subject</h1><section id="activity"><li class="activity-item">
    <p class="activity-text" data-text-truncated="true">Only an excerpt.</p>
    </li></section>"""
    p = extract_profile(sanitize_html(html), "https://www.linkedin.com/in/subject")
    assert p["activity"][0]["captured_text_truncated"] is True
    assert p["activity"][0]["text_truncated"] is True


def test_explorer_scopes_people_and_targets_and_keeps_all_observations():
    profiles = [person("first"), person("other"), person("excluded")]
    affinity, activity = artifacts(profiles, ["first", "other"])
    data = explorer_data(profiles, affinity, activity)
    assert {p["id"] for p in data["profiles"]} == {"first", "other"}
    assert len(data["actions"]) == 2
    assert data["actions"][0]["actor_id"] == "first"
    assert data["actions"][0]["target_id"] == "other"
    assert len(data["posts"]) == 1
    assert len(data["posts"][0]["action_ids"]) == 2
    assert data["actions"][0]["published_at"] is None
    for layout in data["layouts"].values():
        assert "excluded" not in layout
        assert all(math.isfinite(value) for xy in layout.values() for value in xy)


def test_external_target_does_not_create_an_observed_member():
    profiles = [person("first", target="outside")]
    data = explorer_data(profiles, *artifacts(profiles))
    assert data["actions"][0]["target_id"] is None
    assert data["actions"][0]["target_profile_url"].endswith("/outside")
    assert set(data["layouts"]["people"]) == {"first"}


def test_missing_post_urls_do_not_merge_unrelated_people():
    profiles = [person("first"), person("second")]
    for profile in profiles:
        profile["activity"][0].update(id="same-excerpt-hash", url=None)
    data = explorer_data(profiles, *artifacts(profiles))
    assert len(data["posts"]) == 2


def test_portable_html_round_trips_untrusted_text_without_script_breakout(tmp_path):
    profiles = [person("first")]
    attack = '</script><script>alert("sentinel")</script><img src=x onerror=alert(1)>'
    profiles[0]["basic"]["about"] = attack
    destination = tmp_path / "interactive.html"
    render_explorer(profiles, *artifacts(profiles), destination)
    html = destination.read_text()
    soup = BeautifulSoup(html, "html.parser")
    assert len(soup.select("script")) == 2
    assert not soup.select("script[src],link[href],img,iframe")
    assert attack not in html
    embedded = json.loads(soup.select_one("#explorer-data").string)
    assert embedded["profiles"][0]["basic"]["about"] == attack
    assert "EXPLORER_DATA" not in html
    assert "EXPLORER_SCRIPT" not in html


def test_empty_dataset_renders_a_complete_explorer(tmp_path):
    destination = tmp_path / "empty.html"
    data = render_explorer([], *artifacts([]), destination)
    assert data["actions"] == []
    assert data["layouts"] == {"people": {}, "skills": {}, "posts": {}}
    assert destination.stat().st_size > 10_000
