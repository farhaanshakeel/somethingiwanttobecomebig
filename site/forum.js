function forumApiUrl(path) {
  const config = window.TRIANGLE_SITE_CONFIG || {};
  const base = (config.apiBaseUrl || "").replace(/\/$/, "");
  return base ? `${base}${path}` : path;
}

async function mountTriangleForum() {
  const status = document.getElementById("forum-status");
  const categoriesElement = document.getElementById("forum-categories");
  const threadsElement = document.getElementById("forum-threads");
  const heading = document.getElementById("forum-heading");
  const count = document.getElementById("forum-count");
  const search = document.getElementById("forum-search");
  const sort = document.getElementById("forum-sort");
  const threadView = document.getElementById("thread-view");
  const composer = document.getElementById("thread-composer");
  const categorySelect = document.getElementById("thread-category");
  let csrfToken = "";
  let forum = { categories: [], threads: [] };
  let activeCategory = "All discussions";

  function setStatus(message, error = false) {
    status.textContent = message;
    status.className = `editor-status${error ? " is-error" : ""}`;
  }

  function formatDate(value) {
    if (!value) return "Recently";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "Recently" : new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(date);
  }

  function makeText(tag, className, text) {
    const element = document.createElement(tag);
    element.className = className || "";
    element.textContent = text || "";
    return element;
  }

  function visibleThreads() {
    const query = search.value.trim().toLowerCase();
    const filtered = forum.threads.filter((thread) => {
      const categoryMatch = activeCategory === "All discussions" || thread.category === activeCategory;
      const text = `${thread.title} ${thread.replies?.[0]?.body || ""} ${thread.author?.name || ""}`.toLowerCase();
      return categoryMatch && (!query || text.includes(query));
    });
    return filtered.sort((left, right) => {
      if (sort.value === "replies") return (right.replies || []).length - (left.replies || []).length;
      const leftDate = new Date(left.updated || left.created).getTime();
      const rightDate = new Date(right.updated || right.created).getTime();
      return sort.value === "oldest" ? leftDate - rightDate : rightDate - leftDate;
    });
  }

  function renderCategories() {
    categoriesElement.replaceChildren();
    ["All discussions", ...forum.categories].forEach((category) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `forum-category${category === activeCategory ? " active" : ""}`;
      button.textContent = category;
      button.addEventListener("click", () => {
        activeCategory = category;
        heading.textContent = category;
        renderCategories();
        renderThreads();
      });
      categoriesElement.appendChild(button);
    });
  }

  function renderThreads() {
    const threads = visibleThreads();
    threadsElement.replaceChildren();
    count.textContent = `${threads.length} discussion${threads.length === 1 ? "" : "s"}`;
    if (!threads.length) {
      threadsElement.appendChild(makeText("p", "small forum-empty", "No discussions here yet. Start the first one."));
      return;
    }
    threads.forEach((thread) => {
      const link = document.createElement("button");
      link.type = "button";
      link.className = "forum-thread-card";
      link.addEventListener("click", () => renderThread(thread));
      const title = makeText("h3", "", thread.title);
      const excerpt = makeText("p", "small forum-excerpt", thread.replies?.[0]?.body || "");
      const meta = makeText("p", "forum-meta", `${thread.author?.name || "Community member"} · ${formatDate(thread.updated)} · ${(thread.replies || []).length} post${(thread.replies || []).length === 1 ? "" : "s"}`);
      link.append(title, excerpt, meta);
      threadsElement.appendChild(link);
    });
  }

  function renderThread(thread) {
    threadView.hidden = false;
    threadView.replaceChildren();
    const header = document.createElement("div");
    header.className = "forum-thread-heading";
    header.append(makeText("div", "section-label", thread.category), makeText("h2", "", thread.title));
    threadView.appendChild(header);
    (thread.replies || []).forEach((reply, index) => {
      const article = document.createElement("article");
      article.className = "forum-post";
      article.append(makeText("strong", "forum-post-author", reply.author?.name || "Community member"), makeText("span", "forum-meta", formatDate(reply.created)), makeText("p", "", reply.body));
      if (index === 0) article.classList.add("forum-post-original");
      threadView.appendChild(article);
    });
    const replyForm = document.createElement("form");
    replyForm.className = "forum-form forum-reply-form";
    const replyInput = document.createElement("textarea");
    replyInput.rows = 4;
    replyInput.maxLength = 5000;
    replyInput.required = true;
    replyInput.placeholder = "Write a thoughtful reply...";
    const replyButton = document.createElement("button");
    replyButton.className = "auth-link auth-link-login";
    replyButton.type = "submit";
    replyButton.textContent = "Reply";
    replyForm.append(replyInput, replyButton);
    replyForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      replyButton.disabled = true;
      try {
        const response = await fetch(forumApiUrl(`/api/forum/threads/${encodeURIComponent(thread.id)}/replies`), { method: "POST", credentials: "include", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken }, body: JSON.stringify({ body: replyInput.value }) });
        if (!response.ok) throw new Error(await response.text());
        const data = await response.json();
        forum.threads = forum.threads.map((item) => item.id === thread.id ? data.thread : item);
        renderThreads();
        renderThread(data.thread);
      } catch (error) {
        setStatus(error.message, true);
        replyButton.disabled = false;
      }
    });
    threadView.appendChild(replyForm);
    threadView.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  document.getElementById("new-thread-button").addEventListener("click", () => { composer.hidden = false; composer.scrollIntoView({ behavior: "smooth", block: "start" }); });
  search.addEventListener("input", renderThreads);
  sort.addEventListener("change", renderThreads);
  document.getElementById("cancel-thread").addEventListener("click", () => { composer.hidden = true; });
  document.getElementById("thread-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = event.target.querySelector("button[type='submit']");
    button.disabled = true;
    try {
      const response = await fetch(forumApiUrl("/api/forum/threads"), { method: "POST", credentials: "include", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken }, body: JSON.stringify({ category: categorySelect.value, title: document.getElementById("thread-title").value, body: document.getElementById("thread-body").value }) });
      if (!response.ok) throw new Error(await response.text());
      const data = await response.json();
      forum.threads.unshift(data.thread);
      activeCategory = data.thread.category;
      heading.textContent = activeCategory;
      document.getElementById("thread-form").reset();
      composer.hidden = true;
      renderCategories();
      renderThreads();
      renderThread(data.thread);
    } catch (error) {
      setStatus(error.message, true);
    } finally {
      button.disabled = false;
    }
  });

  try {
    const tokenResponse = await fetch(forumApiUrl("/api/csrf"), { credentials: "include", cache: "no-store" });
    if (!tokenResponse.ok) throw new Error("Sign in with Discord to join the discussion.");
    csrfToken = (await tokenResponse.json()).token;
    const response = await fetch(forumApiUrl("/api/forum"), { credentials: "include", cache: "no-store" });
    if (!response.ok) throw new Error("The forum could not be loaded.");
    forum = await response.json();
    forum.categories.forEach((category) => { const option = document.createElement("option"); option.value = category; option.textContent = category; categorySelect.appendChild(option); });
    renderCategories();
    renderThreads();
  } catch (error) {
    setStatus(error.message, true);
    document.getElementById("new-thread-button").disabled = true;
  }
}
