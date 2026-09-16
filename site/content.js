function triangleContentUrl(path = "/api/site-content") {
  const config = window.TRIANGLE_SITE_CONFIG || {};
  const base = (config.apiBaseUrl || "").replace(/\/$/, "");
  return base ? `${base}${path}` : path;
}

async function loadTriangleContent() {
  try {
    const response = await fetch(triangleContentUrl(), { cache: "no-store", credentials: "include" });
    if (!response.ok) return null;
    return await response.json();
  } catch (error) {
    return null;
  }
}

function setContentText(content, selector, value) {
  const element = document.querySelector(selector);
  if (element && value !== undefined && value !== null) element.textContent = value;
}

function renderTriangleBanner(content) {
  const banner = document.getElementById("site-banner");
  if (!banner || !content?.banner) return;
  const item = content.banner;
  if (!item.enabled) {
    banner.hidden = true;
    return;
  }
  setContentText(item, "[data-content='banner.eyebrow']", item.eyebrow);
  setContentText(item, "[data-content='banner.title']", item.title);
  setContentText(item, "[data-content='banner.text']", item.text);
  const button = banner.querySelector("[data-content='banner.button']");
  if (button) {
    button.textContent = item.buttonText || "Learn more";
    button.href = item.buttonUrl || "#";
  }
  const image = banner.querySelector("[data-content='banner.image']");
  if (image) {
    image.hidden = !item.imageUrl;
    image.src = item.imageUrl || "";
  }
}

function renderTriangleProfiles(content) {
  const container = document.getElementById("site-profiles");
  if (!container || !Array.isArray(content?.profiles)) return;
  container.innerHTML = "";
  content.profiles.forEach((profile) => {
    const article = document.createElement("article");
    article.className = "lesson-card profile-card";
    if (profile.imageUrl) {
      const image = document.createElement("img");
      image.src = profile.imageUrl;
      image.alt = profile.name || "Profile image";
      image.className = "profile-image";
      article.appendChild(image);
    }
    const title = document.createElement("h3");
    title.textContent = profile.name || "Profile";
    const description = document.createElement("p");
    description.className = "small";
    description.textContent = profile.description || "";
    article.append(title, description);
    if (profile.linkUrl) {
      const link = document.createElement("a");
      link.href = profile.linkUrl;
      link.textContent = profile.linkText || "View profile";
      article.appendChild(link);
    }
    container.appendChild(article);
  });
}

function renderTrianglePage(content, pageName) {
  const page = content?.pages?.[pageName];
  if (!page) return;
  Object.entries(page).forEach(([key, value]) => {
    if (Array.isArray(value)) {
      const list = document.querySelector(`[data-content-list='pages.${pageName}.${key}']`);
      if (!list) return;
      list.innerHTML = "";
      value.forEach((item) => {
        const child = document.createElement("li");
        child.textContent = item;
        list.appendChild(child);
      });
    } else {
      setContentText(page, `[data-content='pages.${pageName}.${key}']`, value);
    }
  });
}

async function mountTriangleContent(pageName) {
  const content = await loadTriangleContent();
  if (!content) return;
  const brand = content.brand || {};
  document.querySelectorAll("[data-content='brand.name']").forEach((element) => {
    element.textContent = brand.name || "Pi-space";
  });
  document.querySelectorAll("[data-content='brand.tagline']").forEach((element) => {
    element.textContent = brand.tagline || "Academy";
  });
  document.querySelectorAll(".site-logo[data-content='brand.logoUrl']").forEach((element) => {
    if (brand.logoUrl) element.src = brand.logoUrl;
  });
  renderTriangleBanner(content);
  renderTriangleProfiles(content);
  renderTrianglePage(content, pageName);
}
