// Run in DevTools on an already accessible www.linkedin.com profile page.
// Only rendered profile DOM is exported. No cookies, storage or private API calls.
(async () => {
  const slugs = [
    "clementdelangue",
    "julienchaumond",
    "thom-wolf",
    "lysandredebut",
    "ben-burtenshaw",
    "mkdouglas",
    "remifabre",
    "chuntelee",
    "gittospenelope-product-management-growth-bilingual",
    "dana-aubakirova-ai",
  ];
  if (location.origin !== "https://www.linkedin.com")
    throw Error("Open www.linkedin.com first");
  if (document.getElementById("profile-collector-panel"))
    throw Error("Collector already exists");
  const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  // A normal top-level window preserves the ordinary desktop page presentation.
  const popup = window.open(
    location.origin + "/in/" + slugs[0] + "/",
    "LinkedInResearchCollector",
    "popup,width=1280,height=900",
  );
  if (!popup) throw Error("Collector window could not be opened");
  const panel = document.createElement("div");
  panel.id = "profile-collector-panel";
  panel.style.cssText =
    "position:fixed;inset:0;z-index:2147483647;background:white;padding:12px;color:#123;font:16px sans-serif";
  const label = document.createElement("p");
  panel.append(label);
  document.body.append(panel);
  const captures = [];
  window.profileCollectorResults = captures;
  const keep = new Set([
    "id",
    "class",
    "href",
    "aria-label",
    "aria-hidden",
    "role",
    "datetime",
    "componentkey",
    "data-testid",
    "data-view-name",
  ]);
  const sanitize = (root) => {
    const clone = root.cloneNode(true);
    clone
      .querySelectorAll(
        "script,style,iframe,form,input,button,nav,dialog,video,audio,source,[hidden]",
      )
      .forEach((node) => node.remove());
    for (const node of [clone, ...clone.querySelectorAll("*")]) {
      for (const attr of [...node.attributes])
        if (!keep.has(attr.name)) node.removeAttribute(attr.name);
      if (node.hasAttribute("href")) {
        try {
          const url = new URL(node.getAttribute("href"), location.origin);
          if (!/^https?:$/.test(url.protocol) || url.username)
            throw Error("Unsafe link");
          url.search = "";
          url.hash = "";
          node.setAttribute("href", url.href);
        } catch {
          node.removeAttribute("href");
        }
      }
    }
    return clone.outerHTML;
  };
  for (let index = 0; index < slugs.length; index++) {
    const url = location.origin + "/in/" + slugs[index] + "/";
    label.textContent = `Profile collector ${index}/${slugs.length}: loading ${slugs[index]}`;
    console.log(label.textContent);
    try {
      if (index) popup.location.href = url;
      await pause(7000);
      let doc;
      for (let retry = 0; retry < 12; retry++) {
        doc = popup.document;
        if (doc?.querySelector("[aria-label='Primary content'],main h1")) break;
        await pause(1000);
      }
      if (!doc || !popup.location.pathname.includes("/in/" + slugs[index])) {
        throw Error("authentication_or_access_restricted");
      }
      for (let scroll = 0; scroll < 28; scroll++) {
        popup.scrollBy(0, 850);
        // New desktop layouts scroll inside main rather than the outer window.
        for (const element of doc.querySelectorAll("main,main *,body>div")) {
          if (
            element.clientHeight > 350 &&
            element.scrollHeight > element.clientHeight + 150 &&
            ["auto", "scroll"].includes(
              popup.getComputedStyle(element).overflowY,
            )
          ) {
            element.scrollBy(0, 850);
          }
        }
        await pause(450);
      }
      await pause(2000);
      const root =
        doc.querySelector("[aria-label='Primary content']") ||
        doc.querySelector("main");
      if (!root) throw Error("profile_content_unavailable");
      captures.push({
        url,
        collected_at: new Date().toISOString(),
        status: "saved",
        final_url: popup.location.href,
        acquisition: "existing_chrome_dom",
        html: sanitize(root),
      });
      label.textContent = `Profile collector ${index + 1}/${slugs.length}: saved ${slugs[index]}`;
    } catch (error) {
      captures.push({
        url,
        status: "failed",
        error: String(error.message).slice(0, 120),
      });
      if (/authentication/.test(error.message)) break;
    }
    await pause(5000);
  }
  popup.close();
  const blob = new Blob(
    [
      JSON.stringify(
        { schema_version: "1.0", requested: slugs.length, captures },
        null,
        2,
      ),
    ],
    { type: "application/json" },
  );
  const download = document.createElement("a");
  download.href = URL.createObjectURL(blob);
  download.download = "linkedin-session-export.json";
  download.textContent = "Download sanitized profile snapshots";
  panel.append(download);
  label.textContent = `Profile collector finished: ${captures.filter((c) => c.status === "saved").length}/${slugs.length} saved. Right-click the download link and Save Link As, then run import-session.`;
  console.log(label.textContent);
})();
