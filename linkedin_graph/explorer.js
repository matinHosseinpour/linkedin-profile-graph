(() => {
  "use strict";
  const data = JSON.parse(document.getElementById("explorer-data").textContent);
  const $ = (id) => document.getElementById(id);
  const profiles = new Map(data.profiles.map((p) => [p.id, p]));
  const actions = new Map(data.actions.map((a) => [a.key, a]));
  const posts = new Map(data.posts.map((p) => [p.id, p]));
  const kinds = {
    post: "پست",
    repost: "بازنشر",
    comment: "نظر",
    reaction: "واکنش",
    unknown: "نوع نامشخص",
  };
  const number = (n) => new Intl.NumberFormat("fa-IR").format(n);
  const name = (id) => profiles.get(id)?.basic.full_name || id;
  const norm = (value) =>
    String(value || "")
      .normalize("NFKC")
      .toLocaleLowerCase();
  const state = {
    mode: "people",
    query: "",
    person: "",
    kind: "",
    selection: null,
    profileTab: "activity",
    positions: structuredClone(data.layouts),
    view: { x: 0, y: 0, k: 1 },
  };
  let visible = { nodes: [], edges: [], actions: [] };
  let drag = null;
  let suppressClick = false;
  const graph = $("graph");
  const stage = $("stage");
  const details = $("details");
  function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }
  function svg(tag, attrs = {}, text) {
    const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const [key, value] of Object.entries(attrs))
      node.setAttribute(key, value);
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function link(label, url) {
    try {
      const parsed = new URL(url);
      if (
        parsed.protocol !== "https:" ||
        !/(^|\.)linkedin\.com$/i.test(parsed.hostname) ||
        parsed.username ||
        parsed.password ||
        (parsed.port && parsed.port !== "443")
      )
        throw new Error("Untrusted URL");
      const node = el("a", "", label);
      node.href = parsed.href;
      node.target = "_blank";
      node.rel = "noopener noreferrer";
      return node;
    } catch {
      return el("span", "muted", "لینک معتبر در دسترس نیست");
    }
  }
  function fact(label, value, direction = "auto") {
    const row = el("div", "fact");
    const content = el("b");
    content.dir = direction;
    if (value instanceof Node) content.append(value);
    else content.textContent = value ?? "نامشخص";
    row.append(el("span", "", label), content);
    return row;
  }
  function date(value) {
    if (!value) return "نامشخص";
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime())
      ? value
      : new Intl.DateTimeFormat("fa-IR-u-ca-gregory", {
          dateStyle: "medium",
          timeZone: "Asia/Tehran",
        }).format(parsed);
  }
  function section(title) {
    return el("h4", "section-title", title);
  }
  function button(text, cls, callback) {
    const node = el("button", cls, text);
    node.type = "button";
    node.addEventListener("click", callback);
    return node;
  }
  function profileText(p) {
    return norm(
      [
        p.basic.full_name,
        p.basic.headline,
        p.basic.about,
        p.basic.location,
        ...p.experience.flatMap((j) => [j.title, j.company]),
        ...p.skills.map((s) => s.name),
      ].join(" "),
    );
  }
  const profileSearch = new Map(
    data.profiles.map((p) => [p.id, profileText(p)]),
  );
  function actionMatches(a) {
    return (
      (!state.kind || a.kind === state.kind) &&
      (!state.person ||
        a.actor_id === state.person ||
        a.target_id === state.person) &&
      (!state.query ||
        [
          profileSearch.get(a.actor_id),
          profileSearch.get(a.target_id),
          a.captured_text,
          a.text,
          a.action_text,
          a.url,
          a.target_profile_url,
        ].some((t) => norm(t).includes(state.query)))
    );
  }
  function connections(filtered) {
    const pairs = new Map();
    for (const a of filtered) {
      if (
        !a.target_id ||
        a.target_id === a.actor_id ||
        !["repost", "comment", "reaction"].includes(a.kind)
      )
        continue;
      const key = `people:${a.actor_id}:${a.target_id}`;
      if (!pairs.has(key))
        pairs.set(key, {
          id: key,
          source: a.actor_id,
          target: a.target_id,
          type: "people",
          action_ids: [],
        });
      pairs.get(key).action_ids.push(a.key);
    }
    return [...pairs.values()];
  }
  function computeVisible() {
    const filtered = data.actions.filter(actionMatches);
    let nodes = [],
      edges = [];
    const nodeIds = new Set();
    if (state.mode === "skills") {
      const matches = new Set(
        data.profiles
          .filter(
            (p) =>
              (!state.person || state.person === p.id) &&
              (!state.query || profileSearch.get(p.id).includes(state.query)),
          )
          .map((p) => p.id),
      );
      edges = data.affinity.edges
        .filter((e) => matches.has(e.source) || matches.has(e.target))
        .map((e, i) => ({
          ...e,
          id: `skills:${i}:${e.source}:${e.target}`,
          type: "skills",
          action_ids: [],
        }));
      for (const id of matches) nodeIds.add(id);
      for (const edge of edges) {
        nodeIds.add(edge.source);
        nodeIds.add(edge.target);
      }
    } else {
      edges =
        state.mode === "people"
          ? connections(filtered)
          : filtered.map((a) => ({
              id: `postedge:${a.key}`,
              source: a.actor_id,
              target: a.post_id,
              type: "posts",
              action_ids: [a.key],
            }));
      for (const p of data.profiles) {
        if (
          (!state.person || state.person === p.id) &&
          (!state.query || profileSearch.get(p.id).includes(state.query)) &&
          !state.kind
        )
          nodeIds.add(p.id);
      }
      for (const a of filtered) {
        nodeIds.add(a.actor_id);
        if (a.target_id) nodeIds.add(a.target_id);
        if (state.mode === "posts") nodeIds.add(a.post_id);
      }
      for (const edge of edges) {
        nodeIds.add(edge.source);
        nodeIds.add(edge.target);
      }
    }
    nodes = [...nodeIds].map((id) => ({
      id,
      type: profiles.has(id) ? "person" : "post",
    }));
    return { nodes, edges, actions: filtered };
  }
  function titleForPost(id) {
    const observations =
      posts.get(id)?.action_ids.map((key) => actions.get(key)) || [];
    return (
      observations.find((a) => a.captured_text || a.text)?.captured_text ||
      observations.find((a) => a.text)?.text ||
      "پست بدون متن ثبت‌شده"
    );
  }
  function initials(id) {
    return name(id)
      .split(/\s+/)
      .filter((x) => /[\p{L}\p{N}]/u.test(x))
      .slice(0, 2)
      .map((x) => [...x][0])
      .join("")
      .toUpperCase();
  }
  function position(id) {
    return state.positions[state.mode][id] || [0, 0];
  }
  function edgeDescription(edge) {
    if (edge.type === "skills")
      return `${name(edge.source)} ↔ ${name(edge.target)}\nمهارت مشترک: ${edge.shared_skills.join("، ")}`;
    const types = [
      ...new Set(edge.action_ids.map((key) => kinds[actions.get(key).kind])),
    ].join("، ");
    return `${name(edge.source)} → ${edge.type === "posts" ? titleForPost(edge.target).slice(0, 80) : name(edge.target)}\n${number(edge.action_ids.length)} فعالیت · ${types}`;
  }
  function showTooltip(event, text) {
    const tip = $("tooltip");
    tip.textContent = text;
    tip.hidden = false;
    const box = stage.getBoundingClientRect();
    tip.style.left =
      Math.max(
        8,
        Math.min(
          event.clientX - box.left + 12,
          box.width - tip.offsetWidth - 10,
        ),
      ) + "px";
    tip.style.top =
      Math.max(
        8,
        Math.min(
          event.clientY - box.top + 15,
          box.height - tip.offsetHeight - 10,
        ),
      ) + "px";
  }
  function activate(node, callback) {
    node.addEventListener("click", () => {
      if (!suppressClick) callback();
    });
    node.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        callback();
      }
    });
  }
  function draw() {
    $("node-layer").replaceChildren();
    $("edge-layer").replaceChildren();
    for (const edge of visible.edges) {
      const group = svg("g", {
        class: `edge ${edge.type}`,
        "data-edge-id": edge.id,
        tabindex: "0",
        role: "button",
        "aria-label": edgeDescription(edge),
      });
      group.append(
        svg("path", { class: "edge-hit" }),
        svg("path", {
          class: "edge-visible",
          ...(edge.type !== "skills" ? { "marker-end": "url(#arrow)" } : {}),
        }),
      );
      if (state.mode !== "posts")
        group.append(
          svg(
            "text",
            {},
            edge.type === "skills"
              ? `${Math.round(edge.weight * 100)}%`
              : `${number(edge.action_ids.length)} فعالیت`,
          ),
        );
      activate(group, () => select({ type: "edge", id: edge.id }));
      group.addEventListener("pointermove", (e) => {
        if (!drag) showTooltip(e, edgeDescription(edge));
      });
      group.addEventListener("pointerleave", () => {
        $("tooltip").hidden = true;
      });
      $("edge-layer").append(group);
    }
    for (const node of visible.nodes) {
      const isPerson = node.type === "person";
      const group = svg("g", {
        class: "graph-node",
        "data-node-id": node.id,
        tabindex: "0",
        role: "button",
        "aria-label": isPerson
          ? name(node.id)
          : titleForPost(node.id).slice(0, 150),
      });
      if (isPerson) {
        group.append(
          svg("circle", { class: "node-shape", r: "24", fill: "#127e76" }),
          svg("text", { class: "initials" }, initials(node.id)),
        );
        group.append(
          svg("text", { class: "node-name", y: "43" }, name(node.id)),
        );
      } else {
        group.append(
          svg("rect", {
            class: "node-shape",
            x: "-10",
            y: "-10",
            width: "20",
            height: "20",
            rx: "5",
            fill: "#d87c47",
          }),
        );
        if (visible.nodes.length < 35)
          group.append(
            svg(
              "text",
              { class: "node-name", y: "27" },
              titleForPost(node.id).slice(0, 24) + "…",
            ),
          );
      }
      activate(group, () =>
        select({ type: isPerson ? "person" : "post", id: node.id }),
      );
      group.addEventListener("pointerdown", (event) =>
        startDrag(event, node.id),
      );
      group.addEventListener("pointermove", (event) => {
        if (!drag)
          showTooltip(
            event,
            isPerson
              ? `${name(node.id)}\n${profiles.get(node.id).basic.headline || "عنوان ثبت نشده"}`
              : titleForPost(node.id).slice(0, 160),
          );
      });
      group.addEventListener("pointerleave", () => {
        $("tooltip").hidden = true;
      });
      $("node-layer").append(group);
    }
    updateGeometry();
    highlight();
  }
  function updateGeometry() {
    for (const node of $("node-layer").children) {
      const [x, y] = position(node.dataset.nodeId);
      node.setAttribute("transform", `translate(${x},${y})`);
    }
    visible.edges.forEach((edge, i) => {
      const [sx, sy] = position(edge.source),
        [tx, ty] = position(edge.target);
      const dx = tx - sx,
        dy = ty - sy,
        distance = Math.hypot(dx, dy) || 1;
      const reverse = visible.edges.some(
        (e) => e.source === edge.target && e.target === edge.source,
      );
      const bend = reverse ? 24 : state.mode === "posts" ? 0 : 9;
      const cx = (sx + tx) / 2 - (dy / distance) * bend;
      const cy = (sy + ty) / 2 + (dx / distance) * bend;
      const startDistance = Math.hypot(cx - sx, cy - sy) || 1;
      const endDistance = Math.hypot(tx - cx, ty - cy) || 1;
      const sourceRadius = profiles.has(edge.source) ? 27 : 14;
      const targetRadius = profiles.has(edge.target) ? 29 : 16;
      const startX = sx + ((cx - sx) / startDistance) * sourceRadius;
      const startY = sy + ((cy - sy) / startDistance) * sourceRadius;
      const endX = tx - ((tx - cx) / endDistance) * targetRadius;
      const endY = ty - ((ty - cy) / endDistance) * targetRadius;
      const path = `M${startX},${startY} Q${cx},${cy} ${endX},${endY}`;
      const group = $("edge-layer").children[i];
      group.querySelectorAll("path").forEach((p) => p.setAttribute("d", path));
      const text = group.querySelector("text");
      if (text) {
        text.setAttribute("x", (startX + endX + 2 * cx) / 4);
        text.setAttribute("y", (startY + endY + 2 * cy) / 4 - 8);
      }
    });
    transform();
  }
  function transform() {
    const v = state.view;
    $("viewport").setAttribute(
      "transform",
      `translate(${v.x},${v.y}) scale(${v.k})`,
    );
  }
  function fit() {
    const width = stage.clientWidth,
      height = stage.clientHeight;
    if (!visible.nodes.length) {
      state.view = { x: width / 2, y: height / 2, k: 1 };
      transform();
      return;
    }
    const coords = visible.nodes.map((n) => position(n.id));
    const minX = Math.min(...coords.map((p) => p[0])) - 85,
      maxX = Math.max(...coords.map((p) => p[0])) + 85;
    const minY = Math.min(...coords.map((p) => p[1])) - 55,
      maxY = Math.max(...coords.map((p) => p[1])) + 75;
    const k = Math.min(
      1.8,
      (width - 50) / (maxX - minX),
      (height - 80) / (maxY - minY),
    );
    state.view = {
      k,
      x: width / 2 - ((minX + maxX) / 2) * k,
      y: height / 2 - ((minY + maxY) / 2) * k,
    };
    transform();
  }
  function zoom(factor, x = stage.clientWidth / 2, y = stage.clientHeight / 2) {
    const v = state.view,
      k = Math.max(0.15, Math.min(5, v.k * factor)),
      ratio = k / v.k;
    state.view = { k, x: x - (x - v.x) * ratio, y: y - (y - v.y) * ratio };
    transform();
  }
  function startDrag(event, id = null) {
    if (event.button !== 0) return;
    if (id) event.stopPropagation();
    $("tooltip").hidden = true;
    const p = id ? [...position(id)] : [state.view.x, state.view.y];
    drag = { id, x: event.clientX, y: event.clientY, p, moved: false };
  }
  graph.addEventListener("pointerdown", (e) => {
    if (!e.target.closest(".graph-node,.edge")) startDrag(e);
  });
  graph.addEventListener("pointermove", (event) => {
    if (!drag) return;
    const dx = event.clientX - drag.x,
      dy = event.clientY - drag.y;
    if (Math.hypot(dx, dy) > 4 && !drag.moved) {
      drag.moved = true;
      graph.setPointerCapture(event.pointerId);
    }
    if (!drag.moved) return;
    if (drag.id) {
      state.positions[state.mode][drag.id] = [
        drag.p[0] + dx / state.view.k,
        drag.p[1] + dy / state.view.k,
      ];
      updateGeometry();
    } else {
      state.view.x = drag.p[0] + dx;
      state.view.y = drag.p[1] + dy;
      transform();
    }
  });
  function endDrag() {
    if (drag) {
      suppressClick = drag.moved;
      setTimeout(() => {
        suppressClick = false;
      }, 0);
      drag = null;
    }
  }
  graph.addEventListener("pointerup", endDrag);
  graph.addEventListener("pointercancel", endDrag);
  graph.addEventListener("lostpointercapture", endDrag);
  graph.addEventListener(
    "wheel",
    (event) => {
      event.preventDefault();
      const r = stage.getBoundingClientRect();
      zoom(
        Math.exp(-event.deltaY * 0.0015),
        event.clientX - r.left,
        event.clientY - r.top,
      );
    },
    { passive: false },
  );
  function highlight() {
    const s = state.selection;
    const related = new Set();
    const chosenEdge =
      s?.type === "edge" ? visible.edges.find((e) => e.id === s.id) : null;
    const relatedEdges = new Set();
    for (const edge of visible.edges) {
      if (
        chosenEdge?.id === edge.id ||
        (s &&
          s.type !== "edge" &&
          (edge.source === s.id || edge.target === s.id))
      ) {
        relatedEdges.add(edge.id);
        related.add(edge.source);
        related.add(edge.target);
      }
    }
    if (s && s.type !== "edge") related.add(s.id);
    for (const node of $("node-layer").children) {
      const id = node.dataset.nodeId;
      node.classList.toggle("selected", s?.id === id);
      node.classList.toggle("related", related.has(id));
      node.classList.toggle("dim", !!s && !related.has(id));
    }
    for (const edge of $("edge-layer").children) {
      edge.classList.toggle("selected", chosenEdge?.id === edge.dataset.edgeId);
      edge.classList.toggle(
        "dim",
        !!s && !relatedEdges.has(edge.dataset.edgeId),
      );
    }
  }
  function select(selection) {
    state.selection = selection;
    state.profileTab = "activity";
    renderDetails();
    highlight();
    details.scrollTop = 0;
    if (window.innerWidth <= 800 && selection)
      details.scrollIntoView({
        behavior: matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "instant"
          : "smooth",
        block: "start",
      });
  }
  function panelHeader(label, title, subtitle) {
    const top = el("div", "panel-top"),
      text = el("div");
    text.append(
      el("div", "panel-eyebrow", label),
      el("h3", "panel-title", title),
    );
    top.append(
      text,
      button("×", "close-panel", () => select(null)),
    );
    top.lastChild.setAttribute("aria-label", "بستن جزئیات و نمایش فهرست");
    details.append(top);
    if (subtitle) details.append(el("p", "panel-subtitle", subtitle));
  }
  function actionCard(a, open = false) {
    const card = el("article", "activity-card");
    card.dataset.actionId = a.key;
    card.append(
      el("span", `activity-badge ${a.kind}`, kinds[a.kind] || "نوع نامشخص"),
    );
    const actor = name(a.actor_id),
      target = a.target_id
        ? name(a.target_id)
        : a.target_profile_url
          ? "نویسنده خارج از نمونه"
          : "نویسندهٔ نامشخص";
    const description = el(
      "h4",
      "",
      `${actor}${["repost", "comment", "reaction"].includes(a.kind) ? ` → ${target}` : ""}`,
    );
    description.dir = "auto";
    card.append(description);
    const excerpt = el(
      "p",
      "post-excerpt",
      a.text || "متن این فعالیت ثبت نشده است.",
    );
    excerpt.dir = "auto";
    card.append(excerpt);
    const expanded = el("details");
    expanded.open = open;
    expanded.append(el("summary", "", "متن ثبت‌شده و جزئیات فعالیت"));
    const captured = el(
      "div",
      "post-text",
      a.captured_text || a.text || "متن در دسترس نیست",
    );
    captured.dir = "auto";
    expanded.append(captured);
    if (a.captured_text_truncated || (!a.captured_text && a.text_truncated))
      expanded.append(
        el(
          "p",
          "notice",
          "متن در منبع ذخیره‌شده کوتاه شده است؛ ادامهٔ آن فقط از لینک پست قابل بررسی است.",
        ),
      );
    expanded.append(
      fact("عبارت فعالیت در منبع", a.action_text),
      fact("تاریخ نمایشی در زمان ثبت", a.date_text),
      fact("تاریخ انتشار دقیق", a.published_at),
      fact("ثبت صفحه", date(a.captured_at)),
    );
    if (a.target_profile_url)
      expanded.append(
        fact(
          "پروفایل مرتبط در منبع",
          link(
            a.target_id ? name(a.target_id) : a.target_profile_url,
            a.target_profile_url,
          ),
        ),
      );
    expanded.append(
      fact("تعداد واکنش‌ها", a.reactions_count),
      fact("تعداد نظرها", a.comments_count),
      fact("شاهد استخراج", a.evidence),
    );
    card.append(expanded);
    const footer = el("div", "card-footer");
    footer.append(
      link("باز کردن پست ↗", a.url),
      el(
        "span",
        "muted",
        a.date_text ? `${a.date_text} · هنگام ثبت` : "تاریخ نامشخص",
      ),
    );
    card.append(footer);
    return card;
  }
  function pairButton(edge) {
    const node = button("", "pair-button", () =>
      select({ type: "edge", id: edge.id }),
    );
    node.append(
      el(
        "span",
        "pair-names",
        `${name(edge.source)} ${edge.type === "skills" ? "↔" : "→"} ${name(edge.target)}`,
      ),
    );
    node.append(
      el(
        "span",
        "pair-meta",
        edge.type === "skills"
          ? `مهارت مشترک: ${edge.shared_skills.join("، ")}`
          : `${number(edge.action_ids.length)} فعالیت · کلیک برای مشاهدهٔ پست‌ها`,
      ),
    );
    return node;
  }
  function overview() {
    panelHeader(
      "راهنمای کاوش",
      "جزئیات، یک کلیک دورتر",
      "یک فرد یا خط ارتباط را انتخاب کنید. هر فعالیت به متن ذخیره‌شده و پست اصلی وصل است.",
    );
    details.append(
      el(
        "div",
        "help-box",
        state.mode === "posts"
          ? "دایره‌ها افراد و مربع‌های نارنجی پست‌ها هستند. فیلتر یک فرد، پست‌های مرتبط با او را جدا می‌کند."
          : state.mode === "skills"
            ? "این خطوط از مهارت‌های ثبت‌شده ساخته شده‌اند. روی یک خط بزنید تا مهارت مشترک و محاسبهٔ شباهت را ببینید."
            : "فلش از فردی که فعالیت را انجام داده به نویسندهٔ شناسایی‌شده در منبع می‌رود. عدد روی خط، تعداد فعالیت‌های ثبت‌شده است.",
      ),
    );
    details.append(
      section(
        state.mode === "skills" ? "اشتراک مهارت‌ها" : "ارتباط‌های قابل بررسی",
      ),
    );
    const edges =
      state.mode === "skills" ? visible.edges : connections(visible.actions);
    if (state.mode === "posts") {
      for (const a of visible.actions.slice(0, 15))
        details.append(actionCard(a));
      if (visible.actions.length > 15)
        details.append(
          el(
            "p",
            "panel-subtitle",
            "برای محدود کردن فهرست، یک فرد یا عبارت را در فیلترها انتخاب کنید.",
          ),
        );
    } else if (edges.length)
      edges
        .sort((a, b) => b.action_ids.length - a.action_ids.length)
        .forEach((edge) => details.append(pairButton(edge)));
    else
      details.append(
        el(
          "p",
          "panel-subtitle",
          state.mode === "people"
            ? "در این نما ارتباطِ دارای هدف شناسایی‌شده در نمونه ثبت نشده است. برای دیدن پست‌ها نمای «افراد و پست‌ها» را باز کنید."
            : "در این نما مهارت مشترکی بالاتر از آستانه ثبت نشده است.",
        ),
      );
  }
  function showProfile(id) {
    const p = profiles.get(id);
    const own = visible.actions.filter((a) => a.actor_id === id);
    const incoming = visible.actions.filter(
      (a) => a.target_id === id && a.actor_id !== id,
    );
    panelHeader("پروفایل مشاهده‌شده", name(id), p.basic.headline);
    details.append(
      fact("موقعیت", p.basic.location),
      fact("پروفایل اصلی", link("مشاهده در لینکدین ↗", p.url)),
      fact("زمان ثبت", date(p.provenance.collected_at)),
    );
    const tabs = el("div", "profile-tabs");
    tabs.append(
      button(
        `فعالیت‌ها (${number(own.length + incoming.length)})`,
        state.profileTab === "activity" ? "active" : "",
        () => {
          state.profileTab = "activity";
          renderDetails();
        },
      ),
      button(
        "سوابق و مهارت‌ها",
        state.profileTab === "background" ? "active" : "",
        () => {
          state.profileTab = "background";
          renderDetails();
        },
      ),
    );
    details.append(tabs);
    if (state.profileTab === "activity") {
      details.append(
        button("نمایش پست‌های این فرد در گراف ↗", "secondary", () => {
          state.mode = "posts";
          state.person = id;
          $("person-filter").value = id;
          state.selection = null;
          refresh();
        }),
      );
      if (own.length) {
        details.append(section(`فعالیت‌های این فرد · ${number(own.length)}`));
        own.forEach((a, i) => details.append(actionCard(a, i === 0)));
      }
      if (incoming.length) {
        details.append(
          section(`فعالیت دیگران با هدف این فرد · ${number(incoming.length)}`),
        );
        incoming.forEach((a) => details.append(actionCard(a)));
      }
      if (!own.length && !incoming.length)
        details.append(
          el(
            "div",
            "notice",
            "فعالیتی با این فیلتر ثبت نشده است. نبود داده، به معنی نبود فعالیت نیست.",
          ),
        );
    } else {
      if (p.basic.about) {
        details.append(section("دربارهٔ فرد"));
        const about = el("p", "post-text", p.basic.about);
        about.dir = "auto";
        details.append(about);
      }
      details.append(section("مهارت‌های ثبت‌شده"));
      if (p.skills.length)
        p.skills.forEach((skill) => {
          const chip = el("span", "chip", skill.name);
          chip.dir = "auto";
          details.append(chip);
        });
      else details.append(el("p", "muted", "داده در دسترس نیست"));
      for (const [label, records, heading] of [
        ["سوابق کاری", p.experience, "company"],
        ["تحصیلات", p.education, "school"],
      ]) {
        details.append(section(label));
        if (!records.length)
          details.append(el("p", "muted", "داده در دسترس نیست"));
        for (const record of records) {
          const box = el("div", "job");
          box.dir = "auto";
          box.append(
            el("strong", "", record.title || record.degree || record[heading]),
            el("p", "", record[heading]),
            el("p", "", record.date_range || "تاریخ نامشخص"),
          );
          if (record.description) box.append(el("p", "", record.description));
          if (record.is_current === true)
            box.append(el("span", "chip", "در زمان ثبت: شغل فعلی"));
          details.append(box);
        }
      }
      details.append(section("علاقه‌مندی‌های ثبت‌شده"));
      if (!p.interests.length)
        details.append(el("p", "muted", "داده در دسترس نیست"));
      p.interests.forEach((interest) => {
        const item = el("div", "job");
        item.append(
          interest.url
            ? link(interest.name, interest.url)
            : el("span", "", interest.name),
        );
        details.append(item);
      });
      details.append(section("پوشش و منبع"));
      for (const [key, value] of Object.entries(p.coverage))
        details.append(fact(key, `${value.status} · ${value.items}`, "ltr"));
      details.append(
        fact("روش دریافت", p.provenance.source_kind),
        fact("مبنای زمان", p.provenance.timestamp_basis),
        el("p", "source-evidence", `SHA-256: ${p.provenance.html_sha256}`),
      );
    }
  }
  function showEdge(edge) {
    if (edge.type === "posts") {
      showPost(edge.target, edge.action_ids);
      return;
    }
    panelHeader(
      edge.type === "skills" ? "شباهت استنباط‌شده" : "ارتباط مبتنی بر فعالیت",
      `${name(edge.source)} ${edge.type === "skills" ? "↔" : "→"} ${name(edge.target)}`,
    );
    if (edge.type === "skills") {
      details.append(
        el(
          "div",
          "help-box",
          "این ارتباط فقط از اشتراک مهارت‌های ثبت‌شده به دست آمده است؛ شاهد فعالیت یا ارتباط مستقیم بین دو فرد نیست.",
        ),
        section("مهارت‌های مشترک"),
      );
      edge.shared_skills.forEach((skill) =>
        details.append(el("span", "chip", skill)),
      );
      const left = new Set(
        profiles
          .get(edge.source)
          .skills.map((s) => norm(s.name).replace(/\s+/g, " ").trim()),
      );
      const right = new Set(
        profiles
          .get(edge.target)
          .skills.map((s) => norm(s.name).replace(/\s+/g, " ").trim()),
      );
      const union = new Set([...left, ...right]);
      details.append(
        fact(
          "شباهت Jaccard",
          `${number(edge.shared_skills.length)} ÷ ${number(union.size)} = ${new Intl.NumberFormat("fa-IR", { style: "percent", maximumFractionDigits: 1 }).format(edge.weight)}`,
        ),
        fact("آستانهٔ ساخت ارتباط", data.metadata.jaccard_threshold),
      );
      for (const id of [edge.source, edge.target]) {
        details.append(section(name(id)));
        profiles
          .get(id)
          .skills.forEach((skill) =>
            details.append(el("span", "chip", skill.name)),
          );
        details.append(
          fact("منبع", link("پروفایل اصلی ↗", profiles.get(id).url)),
        );
      }
    } else {
      details.append(
        el(
          "p",
          "panel-subtitle",
          `${number(edge.action_ids.length)} فعالیت ثبت‌شده از انجام‌دهنده به نویسندهٔ شناسایی‌شده. هر کارت، یک شاهد مستقل دارد.`,
        ),
      );
      edge.action_ids
        .map((key) => actions.get(key))
        .forEach((a, i) => details.append(actionCard(a, i === 0)));
    }
  }
  function showPost(id, actionIds) {
    const list = (actionIds || posts.get(id).action_ids)
      .map((key) => actions.get(key))
      .filter(actionMatches);
    panelHeader(
      "پست و فعالیت‌های مرتبط",
      "روایت یک پست",
      `${number(list.length)} مشاهده در این نما؛ فعالیت چند فرد روی یک پست جداگانه ثبت می‌شود.`,
    );
    list.forEach((a, i) => details.append(actionCard(a, i === 0)));
  }
  function renderDetails() {
    details.replaceChildren();
    const s = state.selection;
    if (!s) overview();
    else if (s.type === "person") showProfile(s.id);
    else if (s.type === "post") showPost(s.id);
    else {
      const edge = visible.edges.find((e) => e.id === s.id);
      if (edge) showEdge(edge);
      else overview();
    }
  }
  function refresh() {
    state.selection = null;
    visible = computeVisible();
    document
      .querySelectorAll("[data-mode]")
      .forEach((tab) =>
        tab.setAttribute(
          "aria-selected",
          String(tab.dataset.mode === state.mode),
        ),
      );
    $("kind-filter").disabled = state.mode === "skills";
    const copy = {
      people: [
        "چه کسی با چه کسی تعامل داشته؟",
        "خطوط فقط فعالیت‌های دارای هدف شناسایی‌شده در همین نمونه را نشان می‌دهند. افراد بدون ارتباط ثبت‌شده هم قابل بررسی‌اند.",
        "فعالیت مشاهده‌شده؛ فلش از انجام‌دهنده به نویسنده",
      ],
      posts: [
        "از فرد، به فعالیت، به خودِ پست",
        "هر مربع یک پست است؛ خط از فرد به پستی می‌رود که روی آن فعالیت داشته است. برای جزئیات دقیق روی خط یا پست بزنید.",
        "فعالیت فرد روی پست؛ نوع فعالیت در جزئیات",
      ],
      skills: [
        "کدام مهارت، دو نفر را به هم وصل می‌کند؟",
        "شباهت مهارت‌ها با ضریب Jaccard محاسبه شده است. خط نقطه‌چین یک شباهت استنباط‌شده را نشان می‌دهد.",
        "شباهت استنباط‌شده از مهارت‌های ثبت‌شده",
      ],
    }[state.mode];
    $("view-title").textContent = copy[0];
    $("view-description").textContent = copy[1];
    $("edge-legend").textContent = copy[2];
    $("post-legend").hidden = state.mode !== "posts";
    $("view-count").textContent =
      `${number(visible.nodes.length)} گره · ${number(visible.edges.length)} ارتباط`;
    $("empty").hidden = visible.nodes.length > 0;
    draw();
    renderDetails();
    fit();
  }
  const captures = data.profiles
    .map((p) => p.provenance.collected_at)
    .filter(Boolean)
    .sort();
  $("capture-date").textContent = captures.length
    ? `ثبت داده: ${date(captures[0])}${date(captures[0]) !== date(captures.at(-1)) ? ` تا ${date(captures.at(-1))}` : ""}`
    : "زمان ثبت نامشخص";
  $("dataset-label").textContent =
    {
      observed: "دادهٔ مشاهده‌شده · جزئی",
      synthetic: "دادهٔ نمایشی و ساختگی",
      mixed: "ترکیبی از دادهٔ واقعی و ساختگی",
      empty: "بدون داده",
    }[data.metadata.dataset_kind] || data.metadata.dataset_kind;
  $("dataset-label").classList.toggle(
    "synthetic",
    data.metadata.synthetic_profiles > 0,
  );
  $("coverage-note").textContent =
    `این فایل از ${number(data.profiles.length)} پروفایل ذخیره‌شده ساخته شده؛ اطلاعات زنده و تاریخچهٔ کامل نیست. متن جزئیات، فقط متن موجود در همان صفحهٔ ثبت‌شده است.`;
  for (const [label, count, note] of [
    ["پروفایل", data.profiles.length, "قابل بررسی با جزئیات"],
    ["فعالیت ثبت‌شده", data.actions.length, "پست، بازنشر و سایر فعالیت‌ها"],
    [
      "تعامل درون نمونه",
      data.metadata.observed_activity_edges,
      `${number(data.activity.edges.length)} مسیر جهت‌دار`,
    ],
    ["شباهت مهارتی", data.affinity.edges.length, "همراه مهارت مشترک و محاسبه"],
  ]) {
    const metric = el("div", "metric"),
      text = el("div");
    text.append(el("span", "", label), el("small", "", note));
    metric.append(text, el("strong", "", number(count)));
    $("metrics").append(metric);
  }
  for (const p of [...data.profiles].sort((a, b) =>
    name(a.id).localeCompare(name(b.id)),
  )) {
    const option = el("option", "", name(p.id));
    option.value = p.id;
    $("person-filter").append(option);
  }
  document.querySelectorAll("[data-mode]").forEach((tab) =>
    tab.addEventListener("click", () => {
      state.mode = tab.dataset.mode;
      refresh();
    }),
  );
  $("search").addEventListener("input", (event) => {
    state.query = norm(event.target.value).trim();
    refresh();
  });
  $("person-filter").addEventListener("change", (event) => {
    state.person = event.target.value;
    refresh();
  });
  $("kind-filter").addEventListener("change", (event) => {
    state.kind = event.target.value;
    refresh();
  });
  $("clear-filters").addEventListener("click", () => {
    state.query = state.person = state.kind = "";
    $("search").value = $("person-filter").value = $("kind-filter").value = "";
    refresh();
  });
  $("zoom-in").addEventListener("click", () => zoom(1.25));
  $("zoom-out").addEventListener("click", () => zoom(0.8));
  $("fit").addEventListener("click", fit);
  $("export").addEventListener("click", () => {
    const selectedEdge =
      state.selection?.type === "edge"
        ? visible.edges.find((e) => e.id === state.selection.id)
        : null;
    const exported = {
      metadata: data.metadata,
      view: {
        mode: state.mode,
        query: state.query,
        person: state.person,
        kind: state.mode === "skills" ? null : state.kind,
      },
      selection: state.selection,
      selected_edge: selectedEdge,
      nodes: visible.nodes,
      edges: visible.edges,
      profiles: data.profiles.filter((p) =>
        visible.nodes.some((n) => n.id === p.id),
      ),
      actions: state.mode === "skills" ? [] : visible.actions,
      positions: Object.fromEntries(
        visible.nodes.map((n) => [n.id, position(n.id)]),
      ),
    };
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(exported, null, 2)], {
        type: "application/json;charset=utf-8",
      }),
    );
    const anchor = el("a");
    anchor.href = url;
    anchor.download = `linkedin-${state.mode}-view.json`;
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  new ResizeObserver(fit).observe(stage);
  refresh();
})();
