// Fusion Graph SVGs (class mf-fg): fade out everything not connected to the hovered or focused node.
// Safe to load more than once: each graph is set up only once.
(() => {
  function setUp(svg) {
    svg.dataset.mfReady = "true";
    const edges = [...svg.querySelectorAll(".mf-edge")];
    const clear = () => {
      svg.classList.remove("is-focused");
      svg.querySelectorAll(".is-related").forEach(el => el.classList.remove("is-related"));
    };
    svg.querySelectorAll(".mf-node").forEach(node => {
      const focus = () => {
        clear();
        svg.classList.add("is-focused");
        node.classList.add("is-related");
        for (const edge of edges) {
          const { from, to } = edge.dataset;
          if (from !== node.dataset.id && to !== node.dataset.id) continue;
          edge.classList.add("is-related");
          const other = from === node.dataset.id ? to : from;
          svg.querySelector(`.mf-node[data-id="${other}"]`).classList.add("is-related");
        }
      };
      node.addEventListener("mouseenter", focus);
      node.addEventListener("focus", focus);
      node.addEventListener("mouseleave", clear);
      node.addEventListener("blur", clear);
    });
  }

  const setUpAll = () => document.querySelectorAll("svg.mf-fg:not([data-mf-ready])").forEach(setUp);
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", setUpAll);
  } else {
    setUpAll();
  }
})();
