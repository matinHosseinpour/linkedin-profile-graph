"""Ten explicitly fictional HTML fixtures. This module never makes network requests."""

from html import escape
from pathlib import Path

from .common import dump_json

PEOPLE = [
    ("Ava Example", "Data Scientist", ["Python", "SQL", "Machine Learning", "Statistics"]),
    ("Ben Example", "ML Engineer", ["Python", "Machine Learning", "PyTorch", "Docker"]),
    ("Cara Example", "Data Engineer", ["Python", "SQL", "Docker", "Kafka"]),
    ("Dara Example", "Backend Engineer", ["Python", "SQL", "Docker", "API"]),
    ("Eli Example", "Backend Engineer", ["Go", "API", "Docker", "PostgreSQL"]),
    ("Faye Example", "Platform Engineer", ["Docker", "Kubernetes", "Go", "Linux"]),
    ("Gia Example", "Product Manager", ["Product", "Strategy", "Analytics", "SQL"]),
    ("Hugo Example", "Product Analyst", ["SQL", "Analytics", "Statistics", "Product"]),
    ("Iris Example", "UX Researcher", ["Figma", "User Research", "Product", "Strategy"]),
    ("Jules Example", "Technical Lead", ["Python", "Docker", "Product", "Strategy"]),
]


def write_demo(directory):
    directory = Path(directory)
    (directory / "sources").mkdir(parents=True, exist_ok=True)
    manifest = []
    for index, (name, role, skills) in enumerate(PEOPLE, 1):
        slug = f"fictional-fixture-{index:02d}"
        url = f"https://www.linkedin.com/in/{slug}"
        target_index = index % len(PEOPLE) + 1
        target_name = PEOPLE[target_index - 1][0]
        target_url = f"https://www.linkedin.com/in/fictional-fixture-{target_index:02d}"
        skill_html = "".join(
            f'<li class="skill-item"><h3 class="skill-name">{escape(s)}</h3></li>' for s in skills
        )
        action = "commented on a post by" if index % 2 else "reposted a post by"
        html = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{name} | SYNTHETIC FIXTURE</title></head>
<body><main>
<p>FICTIONAL TEST DATA. NOT A REAL LINKEDIN PROFILE. DO NOT FETCH THIS URL.</p>
<h1 class="top-card-layout__title">{name}</h1>
<p class="top-card-layout__headline">{role} at Example Analytics (fictional)</p>
<p class="top-card__subline-item">Example City</p>
<section class="about"><h2>About</h2>
<p>Fictional {role.lower()} for an offline graph demonstration.</p></section>
<section class="experience"><h2>Experience</h2><ul class="experience__list">
<li class="experience-item"><h3 class="experience-item__title">{role}</h3>
<h4 class="experience-item__subtitle">Example Analytics</h4>
<a href="https://www.linkedin.com/company/fictional-example-analytics/">Example Analytics</a>
<p class="experience-item__duration"><time datetime="2022-01">Jan 2022</time> - Present</p>
<p class="experience-item__location">Example City</p>
<p class="experience-item__description">
Works on a fictional team using {escape(skills[0])}.</p></li>
<li class="experience-item"><h3 class="experience-item__title">Junior {role}</h3>
<h4 class="experience-item__subtitle">Example Previous Company</h4>
<p class="experience-item__duration"><time datetime="2020-01">Jan 2020</time> -
<time datetime="2021-12">Dec 2021</time></p></li></ul></section>
<section class="education"><h2>Education</h2><ul class="education__list">
<li class="education__item">
<h3 class="education__item--school">Example University {index % 3 + 1}</h3>
<p class="education__item--degree-info">BSc</p><p class="field-of-study">Computer Science</p>
<p class="education__item--duration"><time datetime="2016">2016</time> -
<time datetime="2020">2020</time></p></li></ul></section>
<section class="skills"><h2>Skills</h2><ul class="skills__list">{skill_html}</ul></section>
<section class="interests"><h2>Interests</h2><ul class="interests__list">
<li class="interest-item"><a href="https://www.linkedin.com/company/fictional-open-data/">
<h3 class="interest-name">Example Open Data Community</h3></a></li></ul></section>
<section class="activity"><h2>Activity</h2><ul class="activity__list">
<li class="activity-item"><p class="activity-action">{name} posted</p>
<p class="activity-text">A fictional update about {escape(skills[0])} and team learning.</p>
<a href="https://www.linkedin.com/posts/fictional-{index:02d}-post">View fictional post</a>
<time datetime="2026-10-20">20 Oct 2026 (fictional date)</time></li>
<li class="activity-item"><p class="activity-action">{name} {action} {target_name}</p>
<a class="activity-target" href="{target_url}">{target_name}</a>
<p class="activity-text">A fictional interaction for testing directed evidence edges.</p>
<a href="https://www.linkedin.com/posts/fictional-{index:02d}-interaction">
View fictional activity</a>
<time datetime="2026-10-21">21 Oct 2026 (fictional date)</time></li></ul></section>
</main></body></html>'''
        path = f"sources/{slug}.html"
        (directory / path).write_text(html, encoding="utf-8")
        manifest.append(
            {"path": path, "url": url, "is_synthetic": True, "source_kind": "synthetic_html"}
        )
    dump_json(directory / "manifest.json", manifest)
    return directory / "manifest.json"
