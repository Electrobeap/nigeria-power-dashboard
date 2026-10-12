(() => {
    const button = document.getElementById("theme-toggle");
    if (!button) return;
    const updateLabel = () => {
        const dark = document.documentElement.dataset.theme === "dark";
        button.textContent = dark ? "Light" : "Dark";
        button.setAttribute("aria-pressed", String(dark));
    };
    updateLabel();
    button.addEventListener("click", () => {
        const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
        document.documentElement.dataset.theme = next;
        try { localStorage.setItem("grid-theme", next); } catch (_) {}
        updateLabel();
    });
})();
