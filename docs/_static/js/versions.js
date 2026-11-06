// Fills the version dropdown in the header from the latest versions.txt.
// Sphinx writes the version list into each page at build time, so docs of an older release would never
// learn about newer ones. Loading the list from the site root keeps every version's dropdown up to date.
// If the file can't be loaded, the list written at build time stays.
document.addEventListener("DOMContentLoaded", async () => {
  function createVersionLink(version, url) {
    const link = document.createElement("a");
    link.href = url;
    link.textContent = version;
    const item = document.createElement("li");
    item.append(link);
    return item;
  }
  const list = document.querySelector(".nav-versions-choices ul");
  if (!list) return;
  try {
    const response = await fetch("/latest/_static/versions.txt", { cache: "no-cache" });
    if (!response.ok) {
        console.log("Failed to fetch newest versions:", response)
        return;
    }
    const versions = (await response.text()).split("\n").map(s => s.trim()).filter(s => s);
    list.replaceChildren(
      createVersionLink("latest", "/latest/"),
      ...versions.map(version => createVersionLink(version, `/v${version}/`))
    );
  } catch (error) {
    console.warn("Failed to fetch newest versions:", error);
  }
});
