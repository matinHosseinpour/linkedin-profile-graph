import hashlib
import json

import pytest

from linkedin_graph.analyze import analysis_findings, analyze, build_graph, observed_activity_graph
from linkedin_graph.cli import extract_manifest, main
from linkedin_graph.common import dump_json, profile_url
from linkedin_graph.demo import write_demo
from linkedin_graph.extract import extract_profile, sanitize_html
from linkedin_graph.session import import_session

URL = "https://www.linkedin.com/in/alex-fixture"


@pytest.fixture
def demo_profiles(tmp_path):
    return extract_manifest(write_demo(tmp_path), tmp_path)[0]


def person(slug, skills):
    data = extract_profile(f"<h1>{slug}</h1>", f"https://www.linkedin.com/in/{slug}")
    data["skills"] = [{"name": s} for s in skills]
    return data


def test_ten_html_inputs_have_all_requested_sections(demo_profiles):
    assert len(demo_profiles) == 10
    assert all(p["provenance"]["is_synthetic"] is True for p in demo_profiles)
    for profile in demo_profiles:
        assert profile["basic"]["full_name"]
        for section in ("experience", "education", "skills", "interests", "activity"):
            assert profile[section]
            assert profile["coverage"][section]["status"] == "observed_partial"
        assert profile["experience"][0]["is_current"] is True
        assert profile["experience"][1]["is_current"] is False
        assert len(profile["activity"]) == 2


def test_missing_sections_stay_unknown():
    html = "<h1>Alex Fixture</h1>"
    profile = extract_profile(html, URL)
    assert profile["basic"]["location"] is None
    assert profile["basic"]["headline"] is None
    assert profile["experience"] == []
    assert profile["coverage"]["skills"] == {"status": "unavailable", "items": 0}
    assert profile["provenance"]["html_sha256"] == hashlib.sha256(html.encode()).hexdigest()
    assert profile["provenance"]["timestamp_basis"] == "import_time"


@pytest.mark.parametrize(
    "html",
    [
        "<title>LinkedIn Login</title><h1>Sign in</h1>",
        '<form action="/uas/login"><input name="session_password"></form>',
        "<html>Service unavailable</html>",
        "<h1>LinkedIn Member</h1>",
    ],
)
def test_access_walls_and_missing_identities_are_not_profiles(html):
    with pytest.raises(ValueError):
        extract_profile(html, URL)


def test_jsonld_subject_is_matched_and_unknown_dates_not_invented():
    objects = [
        {"@type": "Person", "url": "https://www.linkedin.com/in/other", "name": "Unrelated Person"},
        {
            "@type": "Person",
            "url": URL,
            "name": "Alex Fixture",
            "jobTitle": "Engineer",
            "worksFor": {"name": "Example Co"},
            "alumniOf": [{"name": "Example University"}],
            "knowsAbout": ["Python", "python", "SQL"],
        },
    ]
    html = '<script type="application/ld+json">' + json.dumps({"@graph": objects}) + "</script>"
    p = extract_profile(html, URL)
    assert p["basic"]["full_name"] == "Alex Fixture"
    assert p["experience"][0]["company"] == "Example Co"
    assert p["experience"][0]["is_current"] is True
    assert p["experience"][0]["start_date"] is None
    assert len(p["skills"]) == 2
    assert p["education"][0]["degree"] is None


def test_unrelated_jsonld_person_is_ignored():
    html = (
        '<script type="application/ld+json">'
        + json.dumps(
            {"@type": "Person", "url": "https://www.linkedin.com/in/other", "name": "Other"}
        )
        + "</script>"
    )
    with pytest.raises(ValueError, match="no_profile_identity"):
        extract_profile(html, URL)


def test_grouped_rendered_jobs_keep_the_company():
    html = """<h1>Alex Fixture</h1><section><div id="experience"></div><ul class="pvs-list">
    <li><span class="t-bold"><span aria-hidden="true">Example Co</span></span>
    <ul class="pvs-list"><li><span class="t-bold"><span aria-hidden="true">Senior Engineer</span>
    </span><span class="date-range">2023 - Present</span></li>
    <li><span class="t-bold"><span aria-hidden="true">Engineer</span></span>
    <span class="date-range"><time datetime="2020">2020</time> -
    <time datetime="2022">2022</time></span></li></ul></li></ul></section>"""
    p = extract_profile(html, URL)
    assert [(e["title"], e["company"]) for e in p["experience"]] == [
        ("Senior Engineer", "Example Co"),
        ("Engineer", "Example Co"),
    ]
    assert p["experience"][0]["is_current"] is True


def test_sanitization_excludes_session_and_viewer_context():
    html = """<div>PRIVATE SIDEBAR</div><section aria-label="Primary content">
    <div componentkey="public-subject-Topcard"><h2>Alex Fixture</h2></div>
    <p>Followed by Viewer Friend and 2 others you know</p>
    <input value="SESSION_SENTINEL"><script>SESSION_SENTINEL</script>
    <a href="https://www.linkedin.com/company/example?token=SESSION_SENTINEL"
    onclick="SESSION_SENTINEL" data-tracking="SESSION_SENTINEL">Example Co</a></section>"""
    result = sanitize_html(html)
    assert "SESSION_SENTINEL" not in result
    assert "PRIVATE SIDEBAR" not in result
    assert "Viewer Friend" not in result
    assert "public-subject-Topcard" in result
    assert 'href="https://www.linkedin.com/company/example"' in result


def test_sdui_grouped_employment_preserves_each_role():
    html = """<h1>Alex Fixture</h1><section><h2>Experience</h2>
    <div componentkey="entity-collection-item-company"><p>Example Co</p><p>5 yrs</p>
    <div componentkey="entity-collection-item-senior"><p>Senior Engineer</p>
    <p>Jan 2023 - Present</p><p>Remote</p></div>
    <div componentkey="entity-collection-item-junior"><p>Engineer</p>
    <p>Jan 2020 - Dec 2022</p><p>Example City</p></div></div></section>"""
    p = extract_profile(html, URL)
    assert [(j["title"], j["company"], j["is_current"]) for j in p["experience"]] == [
        ("Senior Engineer", "Example Co", True),
        ("Engineer", "Example Co", False),
    ]


def test_sdui_grouped_list_does_not_confuse_duration_with_company():
    html = """<h1>Alex Fixture</h1><section><h2>Experience</h2>
    <div componentkey="entity-collection-item-company"><p>Example Co</p>
    <p>Full-time · 5 yrs</p><ul><li><a href="/company/example"><p>Lead Engineer</p>
    <p>Jan 2023 - Present</p></a><p>Present</p>
    <p><span data-testid="expandable-text-box">Builds software.</span></p></li>
    <li><a href="/company/example"><p>Engineer</p><p>Jan 2020 - Dec 2022</p>
    <p>Remote</p></a></li></ul></div></section>"""
    p = extract_profile(html, URL)
    assert len(p["experience"]) == 2
    assert p["experience"][0]["title"] == "Lead Engineer"
    assert p["experience"][0]["company"] == "Example Co"
    assert p["experience"][0]["location"] is None
    assert p["experience"][1]["location"] == "Remote"


def test_sdui_sections_and_explicit_activity_identity():
    html = """<section aria-label="Primary content">
    <div componentkey="com.linkedin.sdui.profile.card.refFixtureTopcard">
    <h2>Alex Fixture</h2><p>· 3rd</p><p>Engineer</p><p>Example Co · Example School</p>
    <div><p>Example City</p><p>·</p><p><a href="/in/alex-fixture/overlay/contact-info/">
    Contact info</a></p></div></div>
    <section><h2>Experience</h2><div componentkey="entity-collection-item-1">
    <p>Engineer</p><p>Example Co</p><p>Jan 2020 - Present · 6 yrs</p><p>Remote</p>
    <span data-testid="expandable-text-box">Builds software.</span></div></section>
    <section><h2>Skills (2)</h2><div componentkey="entity-collection-item-2">
    <p>Python</p><p>10 endorsements</p></div></section>
    <section><h2>Activity</h2><div componentkey="update-card-focus-1">
    <p>Alex Fixture reposted this</p><a href="/in/alex-fixture/">Alex Fixture</a>
    <a href="/in/other-fixture/">Other Fixture</a><p>2w</p>
    <a href="/feed/update/urn:li:activity:123/"><span data-testid="expandable-text-box">
    A short fictional post.</span></a></div>
    <div componentkey="update-card-focus-2"><p>Other Fixture liked this</p>
    <a href="/in/other-fixture/">Other Fixture</a>
    <span data-testid="expandable-text-box">Different person's action.</span></div>
    </section></section>"""
    p = extract_profile(html, URL)
    assert p["basic"]["location"] == "Example City"
    assert p["basic"]["headline"] == "Engineer"
    assert p["experience"][0]["company"] == "Example Co"
    assert p["experience"][0]["location"] == "Remote"
    assert [s["name"] for s in p["skills"]] == ["Python"]
    assert p["activity"][0]["kind"] == "repost"
    assert p["activity"][0]["target_profile_url"] == "https://www.linkedin.com/in/other-fixture"
    assert p["activity"][0]["date_text"] == "2w"
    assert p["activity"][0]["published_at"] is None
    assert p["activity"][1]["kind"] == "unknown"
    assert p["activity"][1]["target_profile_url"] is None


def test_centrality_matches_a_three_person_path():
    profiles = [
        person("left", ["Python"]),
        person("bridge", ["Python", "SQL"]),
        person("right", ["SQL"]),
    ]
    graph, _, _ = build_graph(profiles, threshold=0.5)
    assert graph.number_of_edges() == 2
    assert graph.nodes["bridge"]["betweenness_centrality"] == pytest.approx(1.0)
    assert graph.nodes["left"]["betweenness_centrality"] == 0
    assert graph.nodes["bridge"]["degree_centrality"] == 1
    assert graph["left"]["bridge"]["weight"] == 0.5


def test_observed_directed_centrality_uses_actual_counterparties():
    base, _, _ = build_graph([person("left", []), person("bridge", []), person("right", [])])
    interactions = [{"source": "left", "target": "bridge"}, {"source": "bridge", "target": "right"}]
    graph, _ = observed_activity_graph(base, interactions)
    assert graph.nodes["bridge"]["in_degree_centrality"] == 0.5
    assert graph.nodes["bridge"]["out_degree_centrality"] == 0.5
    assert graph.nodes["bridge"]["betweenness_centrality"] == 0.5
    assert graph.nodes["left"]["in_degree_centrality"] == 0.0


def test_findings_count_counterparties_instead_of_repeated_action_totals():
    base, _, _ = build_graph([person("left", []), person("bridge", []), person("right", [])])
    interactions = [
        {"source": "left", "target": "bridge"},
        {"source": "right", "target": "bridge"},
        *[{"source": "bridge", "target": "right"}] * 5,
    ]
    observed, _ = observed_activity_graph(base, interactions)
    findings = "\n".join(analysis_findings(base, observed))
    expected = "Highest observed incoming reach: **bridge**, with **2** distinct counterparties"
    assert expected in findings


def test_empty_missing_skills_and_singleton_are_supported(tmp_path):
    graph, _, meta = build_graph([person("alone", [])])
    assert graph.nodes["alone"]["degree_centrality"] == 0
    assert meta["missing_skills_profiles"] == 1
    artifact = analyze([], tmp_path)
    assert artifact["metadata"]["dataset_kind"] == "empty"
    assert (tmp_path / "graph.png").stat().st_size > 1000


def test_current_employer_filter_does_not_accept_unknown_or_former_jobs():
    profiles = [person("current", []), person("former", []), person("unknown", [])]
    for profile, status in zip(profiles, [True, False, None], strict=True):
        profile["experience"] = [{"company": " Example   Co ", "is_current": status}]
    graph, _, _ = build_graph(profiles, organization="EXAMPLE CO")
    assert list(graph) == ["current"]


def test_activity_edges_are_separate_from_skill_affinity(demo_profiles):
    for p in demo_profiles:
        p["skills"] = []
    graph, interactions, meta = build_graph(demo_profiles)
    assert graph.number_of_edges() == 0
    assert len(interactions) == 10
    assert meta["is_linkedin_connection_graph"] is False


@pytest.mark.parametrize(
    "url",
    [
        "http://www.linkedin.com/in/person",
        "https://example.com/in/person",
        "https://www.linkedin.com.evil.test/in/person",
        "https://token@www.linkedin.com/in/person",
        "https://www.linkedin.com/in/person/details/skills",
        "https://www.linkedin.com/in/escaped%2Fpath",
    ],
)
def test_profile_url_validation(url):
    with pytest.raises(ValueError):
        profile_url(url)


def test_manifest_path_traversal_is_rejected(tmp_path):
    dump_json(tmp_path / "manifest.json", [{"url": URL, "path": "../outside.html"}])
    with pytest.raises(ValueError, match="inside"):
        extract_manifest(tmp_path / "manifest.json", tmp_path)


def test_source_hash_matches_file_bytes_with_carriage_returns(tmp_path):
    source = b"<h1>Alex\rFixture</h1>"
    (tmp_path / "profile.html").write_bytes(source)
    dump_json(tmp_path / "manifest.json", [{"url": URL, "path": "profile.html"}])
    profiles, _ = extract_manifest(tmp_path / "manifest.json", tmp_path)
    assert profiles[0]["basic"]["full_name"] == "Alex Fixture"
    assert profiles[0]["provenance"]["html_sha256"] == hashlib.sha256(source).hexdigest()


def test_failed_import_is_not_silently_complete(tmp_path):
    dump_json(
        tmp_path / "session.json",
        {
            "requested": 2,
            "captures": [
                {"url": URL, "status": "saved", "html": "<h1>Alex Fixture</h1>"},
                {
                    "url": "https://www.linkedin.com/in/failed",
                    "status": "failed",
                    "error": "login_wall",
                },
            ],
        },
    )
    profiles, receipt = import_session(tmp_path / "session.json", tmp_path / "out")
    assert len(profiles) == 1
    assert receipt["acquisition_complete"] is False
    assert receipt["requested"] == 2
    assert receipt["saved"] == 1


def test_cli_demo_writes_reviewable_outputs(tmp_path):
    assert main(["demo", "--out", str(tmp_path), "--organization", "Example Analytics"]) == 0
    for filename in (
        "profiles.json",
        "graph.json",
        "graph.png",
        "interactions.json",
        "report.md",
        "interactive.html",
    ):
        assert (tmp_path / filename).is_file()
    graph = json.loads((tmp_path / "graph.json").read_text())
    assert graph["metadata"]["dataset_kind"] == "synthetic"
    assert graph["metadata"]["selected_profiles"] == 10
    assert graph["metadata"]["affinity_edges"] == 16


def test_cli_partial_acquisition_has_nonzero_exit(tmp_path):
    dump_json(tmp_path / "manifest.json", [{"url": URL, "path": "missing.html"}])
    assert (
        main(
            [
                "extract",
                "--manifest",
                str(tmp_path / "manifest.json"),
                "--out",
                str(tmp_path / "out"),
            ]
        )
        == 2
    )


def test_duplicates_rejected_instead_of_double_counted():
    p = person("duplicate", [])
    with pytest.raises(ValueError, match="Duplicate"):
        build_graph([p, p])
