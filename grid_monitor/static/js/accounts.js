(() => {
  "use strict";
  try {
    document.documentElement.dataset.theme = localStorage.getItem("grid-theme")
      || (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  } catch (_) {}
  const input = document.getElementById("account-token");
  if (input && location.hash) {
    const token = new URLSearchParams(location.hash.slice(1)).get("token");
    if (token && /^[A-Za-z0-9_-]{43}$/.test(token)) input.value = token;
    history.replaceState(null, "", location.pathname);
  }
})();
