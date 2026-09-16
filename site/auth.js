function getTriangleSiteConfig() {
  return window.TRIANGLE_SITE_CONFIG || {};
}

function getTriangleEditorUserId() {
  return String(getTriangleSiteConfig().editorUserId || "").trim();
}

function getApiBaseUrl() {
  const apiBaseUrl = (getTriangleSiteConfig().apiBaseUrl || "").replace(/\/$/, "");
  if (apiBaseUrl) {
    return apiBaseUrl;
  }

  return "";
}

function buildTriangleApiUrl(path) {
  const apiBaseUrl = getApiBaseUrl();
  if (!apiBaseUrl) {
    return path;
  }
  return `${apiBaseUrl}${path}`;
}

function buildLoginUrl(nextPath = "/") {
  const siteConfig = getTriangleSiteConfig();
  if (siteConfig.loginUrl) {
    return siteConfig.loginUrl;
  }
  const apiBaseUrl = getApiBaseUrl();
  if (apiBaseUrl) {
    return `${apiBaseUrl}/login/start?next=${encodeURIComponent(nextPath)}`;
  }
  return `/login/start?next=${encodeURIComponent(nextPath)}`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function displayNameFromUser(user) {
  if (!user) return "Guest";
  return user.global_name || (user.discriminator && user.discriminator !== "0"
    ? `${user.username}#${user.discriminator}`
    : user.username) || "Discord user";
}

function isTriangleEditor(user) {
  return Boolean(user && getTriangleEditorUserId() && String(user.id) === getTriangleEditorUserId());
}

function avatarUrlFromUser(user) {
  if (user && user.avatar && user.id) {
    return `https://cdn.discordapp.com/avatars/${user.id}/${user.avatar}.png?size=64`;
  }
  return "https://cdn.discordapp.com/embed/avatars/0.png";
}

async function loadTriangleUser() {
  const response = await fetch(buildTriangleApiUrl("/api/me"), {
    credentials: "include",
    cache: "no-store",
  });
  if (!response.ok) {
    return null;
  }
  const data = await response.json();
  return data.user || null;
}

async function mountTriangleAuthWidget(containerId) {
  const container = document.getElementById(containerId);
  if (!container) return;

  const nextPath = window.location.pathname + window.location.search;
  container.innerHTML = '<div class="auth-widget-loading">Checking login...</div>';

  let user = null;
  try {
    user = await loadTriangleUser();
  } catch (error) {
    user = null;
  }

  if (!user) {
    container.innerHTML = `
      <div class="auth-widget auth-widget-guest">
        <span class="auth-status-label">Account</span>
        <a class="auth-link auth-link-login" href="${escapeHtml(buildLoginUrl(nextPath))}">Sign in with Discord</a>
      </div>
    `;
    return;
  }

  const editorBadge = isTriangleEditor(user)
    ? '<span class="auth-editor-badge">Site editor</span>'
    : '';

  container.innerHTML = `
    <div class="auth-widget auth-widget-signed-in">
      <span class="auth-status-label auth-status-label-signed-in">Signed in</span>
      ${editorBadge}
      <div class="auth-user">
        <img class="auth-avatar" src="${escapeHtml(avatarUrlFromUser(user))}" alt="Discord avatar" />
        <span class="auth-name">${escapeHtml(displayNameFromUser(user))}</span>
      </div>
      <a class="auth-link secondary" href="${escapeHtml(buildTriangleApiUrl('/profile'))}">My profile</a>
      <form action="${escapeHtml(buildTriangleApiUrl('/logout'))}" method="post">
        <button class="auth-link secondary" type="submit">Sign out</button>
      </form>
    </div>
  `;
}

async function mountTriangleEditorNote(containerId) {
  const container = document.getElementById(containerId);
  if (!container) return;

  try {
    const user = await loadTriangleUser();
    if (!isTriangleEditor(user)) {
      container.innerHTML = "";
      return;
    }

    container.innerHTML = `
      <div class="editor-note">
        <strong>Site editor access enabled.</strong>
        This Discord account can manage the site content and future admin tools.
        <div style="margin-top:8px;"><a class="auth-link" href="${escapeHtml(buildTriangleApiUrl('/editor'))}">Open site editor</a></div>
      </div>
    `;
  } catch (error) {
    container.innerHTML = "";
  }
}

async function mountDiscordServerStatus(containerId) {
  const container = document.getElementById(containerId);
  if (!container) return;

  const message = container.querySelector("[data-server-status-message]");
  const link = container.querySelector("[data-server-status-link]");
  const dot = container.querySelector(".server-status-dot");
  const activeMembers = container.parentElement.querySelector("[data-active-members]");
  const activeMembersList = container.parentElement.querySelector("[data-active-members-list]");

  try {
    const response = await fetch(buildTriangleApiUrl("/api/discord/status"), {
      cache: "no-store",
    });
    if (!response.ok) throw new Error("Discord status unavailable");
    const status = await response.json();
    if (!status.available) throw new Error("Discord status unavailable");

    const memberCount = Number.isFinite(status.members) ? ` · ${status.members} members` : "";
    message.textContent = `${status.online} online now${memberCount}`;
    dot.classList.add("is-online");
    if (activeMembers && activeMembersList && Array.isArray(status.activeMembers) && status.activeMembers.length) {
      activeMembers.hidden = false;
      activeMembersList.replaceChildren();
      status.activeMembers.forEach((member) => {
        const item = document.createElement("span");
        item.className = "active-member";
        item.title = `${member.name} is active`;
        if (member.avatar) {
          const avatar = document.createElement("img");
          avatar.src = member.avatar;
          avatar.alt = "";
          item.appendChild(avatar);
        }
        const name = document.createElement("span");
        name.textContent = member.name;
        item.appendChild(name);
        activeMembersList.appendChild(item);
      });
    } else if (activeMembers && activeMembersList && status.activeMembersAvailable === false) {
      activeMembers.hidden = false;
      activeMembersList.textContent = "Member names are unavailable until the Discord Server Widget is enabled.";
    }
    if (status.invite) {
      link.href = status.invite;
    }
  } catch (error) {
    message.textContent = "Server status is temporarily unavailable.";
    dot.classList.add("is-unavailable");
  }
}