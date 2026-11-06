// Fills the version dropdown in the header from the site-wide versions.json.
// Shibuya writes the version list into each page at build time, so docs of an older release would never
// learn about newer ones. Loading the list from the site root keeps every version's dropdown up to date.
// If the file can't be loaded, the list written at build time stays.
document.addEventListener("DOMContentLoaded", async () => {
  const list = document.querySelector(".nav-versions-choices ul");
  if (!list) return;
  try {
    const response = await fetch("/_static/versions.json", { cache: "no-cache" });
    if (!response.ok) return;
    const versions = await response.json();
    list.replaceChildren(
      ...versions.map(({ version, url }) => {
        const link = document.createElement("a");
        link.href = url;
        link.textContent = version;
        const item = document.createElement("li");
        item.append(link);
        return item;
      })
    );
  } catch {
    // Keep the build-time list
  }
});
