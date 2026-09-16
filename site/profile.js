function profileApiUrl(path) {
  const config = window.TRIANGLE_SITE_CONFIG || {};
  const base = (config.apiBaseUrl || "").replace(/\/$/, "");
  return base ? `${base}${path}` : path;
}

async function mountTriangleProfile() {
  const form = document.getElementById("profile-form");
  const status = document.getElementById("profile-status");
  const setStatus = (message, error = false) => {
    status.textContent = message;
    status.className = `editor-status${error ? " is-error" : ""}`;
  };
  const updateCompletion = () => {
    const bio = document.getElementById("profile-bio").value.trim();
    const subjects = document.getElementById("profile-subjects").value.split(",").map((item) => item.trim()).filter(Boolean);
    const completed = [bio, subjects.length].filter(Boolean).length;
    document.getElementById("profile-completion").textContent = `Profile completion: ${completed}/2 · ${bio.length}/500 bio characters`;
  };
  try {
    const csrfResponse = await fetch(profileApiUrl("/api/csrf"), { credentials: "include", cache: "no-store" });
    if (!csrfResponse.ok) throw new Error("Your login session has expired.");
    const csrfToken = (await csrfResponse.json()).token;
    const response = await fetch(profileApiUrl("/api/profile"), { credentials: "include", cache: "no-store" });
    if (!response.ok) throw new Error("Could not load your profile.");
    const profile = (await response.json()).profile;
    document.getElementById("profile-name").textContent = profile.display_name || "Discord member";
    document.getElementById("profile-avatar").src = profile.avatar || "logo.svg";
    document.getElementById("profile-bio").value = profile.bio || "";
    document.getElementById("profile-subjects").value = (profile.subjects || []).join(", ");
    document.getElementById("profile-private").checked = profile.private !== false;
    document.getElementById("profile-meta").textContent = `Member since ${new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(profile.joined_at))} · Discord identity is managed by Discord`;
    updateCompletion();
    document.getElementById("profile-bio").addEventListener("input", updateCompletion);
    document.getElementById("profile-subjects").addEventListener("input", updateCompletion);
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = form.querySelector("button[type='submit']");
      button.disabled = true;
      try {
        const saveResponse = await fetch(profileApiUrl("/api/profile"), {
          method: "PUT",
          credentials: "include",
          headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
          body: JSON.stringify({
            bio: document.getElementById("profile-bio").value,
            subjects: [...new Set(document.getElementById("profile-subjects").value.split(",").map((item) => item.trim()).filter(Boolean))],
            private: document.getElementById("profile-private").checked,
          }),
        });
        if (!saveResponse.ok) throw new Error(await saveResponse.text() || "Profile could not be saved.");
        setStatus("Profile saved.");
      } catch (error) {
        setStatus(error.message, true);
      } finally {
        button.disabled = false;
      }
    });
  } catch (error) {
    setStatus(error.message, true);
    form.querySelectorAll("input, textarea, button").forEach((field) => { field.disabled = true; });
  }
}
