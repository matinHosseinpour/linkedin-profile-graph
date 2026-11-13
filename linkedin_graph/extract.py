"""Extract observed HTML/JSON-LD only. Selectors are deliberately easy to update."""

import hashlib
import json
import re

from bs4 import BeautifulSoup, Comment

from .common import clean, normalize, profile_url, safe_url, unique, utc_now

SECTIONS = {
    "experience": ("experience", "Experience", "سوابق شغلی"),
    "education": ("education", "Education", "تحصیلات"),
    "skills": ("skills", "Skills", "مهارت‌ها"),
    "interests": ("interests", "Interests", "علاقه‌مندی‌ها"),
    "activity": ("activity", "Activity", "فعالیت‌ها"),
}


def text_at(root, selectors):
    """Use the first populated selector, avoiding duplicate screen-reader text."""
    if root is None:
        return None
    for selector in selectors.split(","):
        node = root.select_one(selector.strip())
        if node and (value := clean(node.get_text(" ", strip=True))):
            return value
    return None


def section_at(soup, key):
    anchor, english, persian = SECTIONS[key]
    for selector in (f"section.{anchor}", f"section#{anchor}", f"[data-section='{anchor}']"):
        if node := soup.select_one(selector):
            return node
    # LinkedIn's rendered page puts the anchor inside its containing section.
    if node := soup.find(id=anchor):
        return node.find_parent("section") or node.parent
    for heading in soup.select("h2"):
        label = re.sub(r"\s*\(\d+\)$", "", heading.get_text(" ", strip=True))
        if normalize(label) in {normalize(english), normalize(persian)}:
            return heading.find_parent("section") or heading.parent
    return None


def person_jsonld(soup, url):
    def walk(value):
        if isinstance(value, list):
            for item in value:
                yield from walk(item)
        elif isinstance(value, dict):
            types = value.get("@type", [])
            if "Person" in (types if isinstance(types, list) else [types]):
                yield value
            for key in ("@graph", "mainEntity"):
                yield from walk(value.get(key))

    people = []
    for script in soup.select("script[type='application/ld+json']"):
        try:
            people.extend(walk(json.loads(script.string or script.get_text())))
        except (ValueError, TypeError, RecursionError):
            continue
    for person in people:
        if safe_url(person.get("url")) == url:
            return person
    # Never take a different person's recommendations/sidebar schema as the subject.
    candidates = [p for p in people if not p.get("url")]
    if len(candidates) == 1 and len(people) == 1:
        return candidates[0]
    return {}


def named(value):
    if isinstance(value, dict):
        return clean(value.get("name"))
    return clean(value) if isinstance(value, str) else None


def as_list(value):
    return value if isinstance(value, list) else [value] if value else []


def entries(section, guest_selector):
    if section is None:
        return []
    nodes = section.select(guest_selector)
    if not nodes:
        nodes = (
            section.select("[componentkey^='entity-collection-item-']")
            or section.select("[componentkey^='update-card-focus']")
            or section.select(".pvs-list > li")
            or section.select("li")
        )
    # Nested roles are handled by jobs(), not emitted twice here.
    return [n for n in nodes if not any(p in nodes for p in n.parents)]


def date_info(node):
    date_range = text_at(
        node,
        ".experience-item__duration, .education__item--duration, .date-range, "
        ".pvs-entity__caption-wrapper, .t-black--light span[aria-hidden='true']",
    )
    if not date_range:
        date_range = next(
            (
                clean(p.get_text(" ", strip=True))
                for p in node.select("p")
                if re.match(
                    r"^(?:[A-Z][a-z]{2} )?\d{4}\s*[-–—]\s*"
                    r"(?:[A-Z][a-z]{2} )?(?:\d{4}|Present)",
                    p.get_text(" ", strip=True),
                )
            ),
            None,
        )
    times = node.select("time")
    start = times[0].get("datetime") if times else None
    end = times[1].get("datetime") if len(times) > 1 else None
    current = None
    if date_range and re.search(r"\b(present|current)\b|تاکنون|اکنون", date_range, re.I):
        current = True
    elif end:
        current = False
    elif date_range and re.search(r"[-–—]\s*(?:[A-Z][a-z]{2} )?\d{4}", date_range):
        current = False
    return {"start_date": start, "end_date": end, "date_range": date_range, "is_current": current}


def sdui_jobs(node, inherited_company=None, inherited_url=None):
    nested = node.select("[componentkey^='entity-collection-item-']")
    all_paragraphs = [clean(p.get_text(" ", strip=True)) for p in node.select("p")]
    if (
        not nested
        and len(all_paragraphs) > 1
        and all_paragraphs[1]
        and re.search(r"\d+\s+(?:yrs?|mos?)\b", all_paragraphs[1])
    ):
        nested = [li for li in node.select("ul > li") if date_info(li)["date_range"]]
    paragraphs = [
        clean(p.get_text(" ", strip=True))
        for p in node.select("p")
        if not any(parent in nested for parent in p.parents)
    ]
    paragraphs = [p for p in paragraphs if p]
    company_link = node.select_one("a[href*='/company/']")
    company_url = safe_url(company_link.get("href")) if company_link else inherited_url
    if nested:
        company = paragraphs[0] if paragraphs else inherited_company
        children = [child for child in nested if not any(p in nested for p in child.parents)]
        return [job for child in children for job in sdui_jobs(child, company, company_url)]
    if not paragraphs:
        return []
    dates = date_info(node)
    company = inherited_company or (paragraphs[1] if len(paragraphs) > 1 else None)
    if company == dates["date_range"] or (company and re.match(r"^\d+ (?:yrs?|mos?)\b", company)):
        company = None
    header = next(
        (
            a
            for a in node.select("a")
            if dates["date_range"] and date_info(a)["date_range"] == dates["date_range"]
        ),
        None,
    )
    header_values = (
        [clean(p.get_text(" ", strip=True)) for p in header.select("p")] if header else paragraphs
    )
    date_index = (
        header_values.index(dates["date_range"]) if dates["date_range"] in header_values else None
    )
    location = (
        header_values[date_index + 1]
        if date_index is not None and len(header_values) > date_index + 1
        else None
    )
    if location in {"Present", "Full-time", "Part-time"}:
        location = None
    return [
        {
            "title": paragraphs[0],
            "company": company.split(" · ")[0] if company else None,
            "company_url": company_url,
            **dates,
            "location": location,
            "description": text_at(node, "[data-testid='expandable-text-box']"),
            "evidence": "html:experience:sdui",
        }
    ]


def jobs(section):
    result = []
    for node in entries(section, ".experience__list > li, .experience-item"):
        if node.get("componentkey", "").startswith("entity-collection-item-"):
            result.extend(sdui_jobs(node))
            continue
        company_link = node.select_one("a[href*='/company/']")
        company = text_at(node, ".experience-item__subtitle, .company-name")
        # Grouped roles in one company: use the parent company, then each child job.
        nested = node.select(".pvs-list > li")
        if nested:
            company = company or text_at(node, ".t-bold span[aria-hidden='true']")
        for role in nested or [node]:
            title = text_at(
                role, ".experience-item__title, .job-title, .t-bold span[aria-hidden='true'], h3"
            )
            role_company = company or text_at(role, ".t-14.t-normal span[aria-hidden='true']")
            if role_company:
                role_company = role_company.split(" · ")[0]
            if title:
                result.append(
                    {
                        "title": title,
                        "company": role_company,
                        "company_url": safe_url(company_link.get("href")) if company_link else None,
                        **date_info(role),
                        "location": text_at(role, ".experience-item__location, .job-location"),
                        "description": text_at(
                            role,
                            ".experience-item__description, .job-description, "
                            ".pvs-entity__sub-components .inline-show-more-text "
                            "span[aria-hidden='true']",
                        ),
                        "evidence": "html:experience",
                    }
                )
    return unique(result, lambda x: (x["title"], x["company"], x["date_range"]))


def studies(section):
    result = []
    for node in entries(section, ".education__list > li, .education__item"):
        if node.get("componentkey", "").startswith("entity-collection-item-"):
            paragraphs = [clean(p.get_text(" ", strip=True)) for p in node.select("p")]
            paragraphs = [p for p in paragraphs if p]
            dates = date_info(node)
            dates.pop("is_current")
            if paragraphs:
                result.append(
                    {
                        "school": paragraphs[0],
                        "degree": paragraphs[1]
                        if len(paragraphs) > 1 and paragraphs[1] != dates["date_range"]
                        else None,
                        "field_of_study": None,
                        **dates,
                        "description": text_at(node, "[data-testid='expandable-text-box']"),
                        "evidence": "html:education:sdui",
                    }
                )
            continue
        school = text_at(
            node, ".education__item--school, .school-name, .t-bold span[aria-hidden='true'], h3"
        )
        if school:
            dates = date_info(node)
            dates.pop("is_current")
            result.append(
                {
                    "school": school,
                    "degree": text_at(
                        node,
                        ".education__item--degree-info, .degree, "
                        ".t-14.t-normal span[aria-hidden='true']",
                    ),
                    "field_of_study": text_at(node, ".field-of-study"),
                    **dates,
                    "description": text_at(node, ".education__item--description"),
                    "evidence": "html:education",
                }
            )
    return unique(result, lambda x: (x["school"], x["degree"], x["date_range"]))


def skill_items(section):
    result = []
    for node in entries(section, ".skills__list > li, .skill-item"):
        name = text_at(node, ".skill-name, .t-bold span[aria-hidden='true'], h3, p")
        name = name or clean(node.get_text(" ", strip=True))
        if name:
            result.append({"name": name, "endorsements": None, "evidence": "html:skills"})
    return unique(result, lambda x: normalize(x["name"]))


def interests(section):
    result = []
    if section:
        for link in section.select("a[href]"):
            url = safe_url(link.get("href"))
            if url and re.search(r"/(?:in|company|school|groups)/[^/]+$", url):
                name = text_at(link, "p") or clean(link.get_text(" ", strip=True))
                if name:
                    result.append(
                        {
                            "name": name,
                            "url": url,
                            "category": "person" if "/in/" in url else "organization",
                            "evidence": "html:interests",
                        }
                    )
    for node in entries(section, ".interests__list > li, .interest-item"):
        name = text_at(node, ".interest-name, .t-bold span[aria-hidden='true'], h3")
        link = node.select_one("a[href]")
        if name:
            url = safe_url(link.get("href")) if link else None
            category = next(
                (
                    kind
                    for path, kind in (
                        ("/company/", "company"),
                        ("/school/", "school"),
                        ("/groups/", "group"),
                        ("/in/", "person"),
                    )
                    if url and path in url
                ),
                "unknown",
            )
            result.append(
                {"name": name, "url": url, "category": category, "evidence": "html:interests"}
            )
    return unique(result, lambda x: x["url"] or x["name"])


def activities(section, subject_url, subject_name):
    result = []
    for node in entries(
        section, ".activity__list > li, .activity-item, .feed-shared-update-v2, .base-main-card"
    ):
        is_sdui = node.get("componentkey", "").startswith("update-card-focus")
        text = text_at(
            node,
            ".activity-text, .feed-shared-update-v2__description, "
            ".update-components-text, .attributed-text-segment-list__content, "
            ".share-update-card__update-text",
        )
        action = text_at(node, ".activity-action, .update-components-header__text-view")
        if is_sdui:
            action = text_at(node, "p")
            text = text_at(node, "[data-testid='expandable-text-box']")
        kind = "unknown"
        for pattern, label in (
            (r"reposted|shared this|بازنشر", "repost"),
            (r"commented|نظر داد", "comment"),
            (r"reacted|liked|پسندید", "reaction"),
            (r"posted|منتشر کرد", "post"),
        ):
            if (
                action
                and normalize(action).startswith(normalize(subject_name) + " ")
                and re.search(pattern, action, re.I)
            ):
                kind = label
                break
        link = node.select_one("a[href*='/posts/'], a[href*='/feed/update/']")
        post_url = safe_url(link.get("href")) if link else None
        if is_sdui and post_url and normalize(action) == normalize(subject_name):
            kind = "post"
        target = node.select_one(
            ".activity-target[href*='/in/'], .update-components-actor a[href*='/in/']"
        )
        target_url = safe_url(target.get("href")) if target else None
        if is_sdui and kind in {"repost", "comment", "reaction"}:
            target_url = next(
                (
                    safe_url(a.get("href"))
                    for a in node.select("a[href*='/in/']")
                    if safe_url(a.get("href")) != subject_url
                ),
                None,
            )
        try:
            target_url = profile_url(target_url) if target_url else None
        except ValueError:
            target_url = None
        if kind not in {"repost", "comment", "reaction"} or target_url == subject_url:
            target_url = None
        time = node.select_one("time")
        date_text = clean(time.get_text(" ", strip=True)) if time else None
        if is_sdui and not date_text:
            date_text = next(
                (
                    clean(p.get_text(" ", strip=True))
                    for p in node.select("p")
                    if re.match(r"^\d+\s*(?:h|d|w|mo|yr)\b", p.get_text(strip=True))
                ),
                None,
            )
        if text or post_url or action:
            identity = (
                post_url or hashlib.sha256(f"{kind}:{text}:{action}".encode()).hexdigest()[:16]
            )
            result.append(
                {
                    "id": identity,
                    "kind": kind,
                    "text": text[:90].rstrip() if text else None,
                    "text_truncated": bool(text and len(text) > 90)
                    or bool(node.select_one("[data-text-truncated='true']")),
                    "captured_text": text,
                    "captured_text_truncated": bool(
                        node.select_one("[data-text-truncated='true']")
                    ),
                    "action_text": action,
                    "url": post_url,
                    "published_at": time.get("datetime") if time else None,
                    "date_text": date_text,
                    "target_profile_url": target_url,
                    "reactions_count": None,
                    "comments_count": None,
                    "evidence": "html:activity",
                }
            )
    return unique(result, lambda x: (x["id"], x["kind"], x["action_text"]))


def access_problem(html, final_url=""):
    soup = BeautifulSoup(html, "html.parser")
    if re.search(r"/(authwall|login|checkpoint|uas/)", final_url):
        return "authentication_or_access_restricted"
    if soup.select_one("form[action*='login'], input[name='session_password'], #captcha-internal"):
        return "authentication_or_access_restricted"
    title = text_at(soup, "title") or ""
    if re.search(r"sign in|log\s*in|security verification|captcha|authwall", title, re.I):
        return "authentication_or_access_restricted"
    return None


def sanitize_html(html):
    """Retain visible evidence and a safe subset of Person JSON-LD, never session state."""
    soup = BeautifulSoup(html, "html.parser")
    primary = soup.select_one("[aria-label='Primary content']")
    if primary:
        soup = BeautifulSoup(str(primary), "html.parser")
    for comment in soup.find_all(string=lambda value: isinstance(value, Comment)):
        comment.extract()
    # Exclude viewer-specific social context from an otherwise public subject profile.
    for paragraph in list(soup.select("p")):
        if re.match(r"^(?:Followed by|You and |You both )", paragraph.get_text(strip=True)):
            paragraph.decompose()
    allowed_json_keys = {
        "@context",
        "@type",
        "@graph",
        "mainEntity",
        "name",
        "url",
        "description",
        "jobTitle",
        "address",
        "addressLocality",
        "addressRegion",
        "addressCountry",
        "worksFor",
        "alumniOf",
        "knowsAbout",
        "image",
        "contentUrl",
    }

    def project(value):
        if isinstance(value, dict):
            return {k: project(v) for k, v in value.items() if k in allowed_json_keys}
        if isinstance(value, list):
            return [project(v) for v in value]
        return value

    for script in list(soup.select("script")):
        if script.get("type") == "application/ld+json":
            try:
                script.string = json.dumps(project(json.loads(script.string or "")))
                continue
            except (ValueError, TypeError, RecursionError):
                pass
        script.decompose()
    for node in list(
        soup.select(
            "style, noscript, iframe, form, input, button, nav, body > header, footer, "
            "dialog, [role='dialog'], code, template, .hidden, .invisible, [hidden], "
            "[aria-hidden='true'].visually-hidden"
        )
    ):
        node.decompose()
    for node in list(soup.find_all(True)):
        if node.attrs is None:
            continue
        keep = {
            "id",
            "class",
            "href",
            "alt",
            "aria-hidden",
            "aria-label",
            "role",
            "datetime",
            "type",
            "componentkey",
            "data-testid",
            "data-view-name",
            "data-text-truncated",
        }
        node.attrs = {k: v for k, v in node.attrs.items() if k in keep}
        for attr in ("href", "src"):
            if attr in node.attrs:
                value = safe_url(node.attrs[attr])
                if value:
                    node.attrs[attr] = value
                else:
                    del node.attrs[attr]
    return str(soup)


def extract_profile(html, url, *, source_kind="saved_html", is_synthetic=False, collected_at=None):
    url = profile_url(url)
    if problem := access_problem(html):
        raise ValueError(problem)
    soup = BeautifulSoup(html, "html.parser")
    # Exclude hidden elements and unrelated recommendation cards from section selectors.
    for node in list(soup.select("[hidden], [style*='display:none'], [style*='display: none']")):
        node.decompose()
    schema = person_jsonld(soup, url)
    sections = {key: section_at(soup, key) for key in SECTIONS}
    topcard = soup.select_one("[componentkey*='profile.card.'][componentkey$='Topcard']")
    top_paragraphs = topcard.select("p") if topcard else []
    top_values = [clean(p.get_text(" ", strip=True)) for p in top_paragraphs]
    top_values = [v for v in top_values if v and not re.match(r"^[·•]", v)]
    contact = topcard.select_one("a[href*='/overlay/contact-info']") if topcard else None
    location = None
    if contact:
        parent = contact.find_parent("p") or contact
        location = text_at(parent.parent, "p")
    about_heading = next((h for h in soup.select("h2") if h.get_text(strip=True) == "About"), None)
    about_section = about_heading.find_parent("section") if about_heading else None
    address = schema.get("address")
    if isinstance(address, dict):
        address = ", ".join(
            filter(
                None,
                (
                    named(address.get("addressLocality")),
                    named(address.get("addressRegion")),
                    named(address.get("addressCountry")),
                ),
            )
        )
    basic = {
        "full_name": text_at(soup, "h1.top-card-layout__title, h1.text-heading-xlarge, h1")
        or text_at(topcard, "h2")
        or named(schema.get("name")),
        "headline": text_at(soup, ".top-card-layout__headline, .text-body-medium.break-words")
        or (top_values[0] if top_values else None)
        or named(schema.get("jobTitle")),
        "location": text_at(
            soup, ".top-card__subline-item, .text-body-small.inline.t-black--light.break-words"
        )
        or location
        or named(address),
        "about": text_at(
            soup,
            ".summary .core-section-container__content, #about ~ div "
            "span[aria-hidden='true'], section.about p, .summary-text",
        )
        or text_at(about_section, "[data-testid='expandable-text-box']")
        or named(schema.get("description")),
    }
    if not basic["full_name"]:
        raise ValueError("no_profile_identity: no visible name or matching Person JSON-LD")
    experience = jobs(sections["experience"])
    if not experience:
        for org in as_list(schema.get("worksFor")):
            if company := named(org):
                experience.append(
                    {
                        "title": named(schema.get("jobTitle")),
                        "company": company,
                        "company_url": safe_url(org.get("url")) if isinstance(org, dict) else None,
                        "start_date": None,
                        "end_date": None,
                        "date_range": None,
                        "is_current": True,
                        "location": None,
                        "description": None,
                        "evidence": "jsonld:worksFor",
                    }
                )
    education = studies(sections["education"])
    if not education:
        education = [
            {
                "school": named(s),
                "degree": None,
                "field_of_study": None,
                "start_date": None,
                "end_date": None,
                "date_range": None,
                "description": None,
                "evidence": "jsonld:alumniOf",
            }
            for s in as_list(schema.get("alumniOf"))
            if named(s)
        ]
    skills = skill_items(sections["skills"])
    if not skills:
        skills = [
            {"name": named(s), "endorsements": None, "evidence": "jsonld:knowsAbout"}
            for s in as_list(schema.get("knowsAbout"))
            if named(s)
        ]
        skills = unique(skills, lambda x: normalize(x["name"]))
    result = {
        "schema_version": "1.0",
        "id": url.rsplit("/", 1)[-1],
        "url": url,
        "basic": basic,
        "experience": experience,
        "education": education,
        "skills": skills,
        "interests": interests(sections["interests"]),
        "activity": activities(sections["activity"], url, basic["full_name"]),
    }
    result["coverage"] = {
        key: {
            "status": "observed_partial" if result[key] else "unavailable",
            "items": len(result[key]),
        }
        for key in SECTIONS
    }
    result["coverage"]["basic"] = {
        "status": "observed_partial",
        "items": sum(v is not None for v in basic.values()),
    }
    result["provenance"] = {
        "source_kind": source_kind,
        "source_url": url,
        "collected_at": collected_at or utc_now(),
        "timestamp_basis": "source_capture_time" if collected_at else "import_time",
        "html_sha256": hashlib.sha256(html.encode("utf-8")).hexdigest(),
        "is_synthetic": bool(is_synthetic),
        "warnings": [
            "Only fields present in this snapshot were extracted; completeness is not established.",
            "Unavailable sections do not mean the person has no entries.",
        ]
        + (["Fictional fixture; this is not a real LinkedIn member."] if is_synthetic else []),
    }
    return result
