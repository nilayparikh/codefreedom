/**
 * get_elements.js
 *
 * Extracts all interactive elements from the current page.
 * Injected via Playwright's page.evaluate().
 *
 * Returns an array of element objects with selectors and positions,
 * suitable for automated clicking/interaction.
 *
 * @param {boolean} visibleOnly - If true, only return elements in viewport
 * @returns {Array<Object>} Array of element descriptors
 */
(visibleOnly) => {
  const SELECTORS = [
    "a[href]", "button", "input", "select", "textarea",
    '[role="button"]', '[role="link"]', '[role="checkbox"]',
    '[role="radio"]', '[role="tab"]', '[role="menuitem"]',
    "[onclick]", '[tabindex]:not([tabindex="-1"])',
    "label[for]", "summary", '[contenteditable="true"]',
  ].join(",");

  const getSelector = (el) => {
    if (el.id) return "#" + el.id;
    if (el.className && typeof el.className === "string") {
      const cls = el.className.trim().split(/\s+/).filter((c) => c)[0];
      if (cls) {
        const sel = el.tagName.toLowerCase() + "." + cls;
        try {
          if (document.querySelectorAll(sel).length === 1) return sel;
        } catch (e) {}
      }
    }
    if (el.name) return el.tagName.toLowerCase() + '[name="' + el.name + '"]';
    for (const attr of ["data-testid", "aria-label", "title", "placeholder"]) {
      const val = el.getAttribute(attr);
      if (val) return el.tagName.toLowerCase() + "[" + attr + '="' + val.replace(/"/g, '\\"') + '"]';
    }
    const parts = [];
    let node = el;
    while (node && node.nodeType === 1) {
      let idx = 1, sib = node.previousSibling;
      while (sib) {
        if (sib.nodeType === 1 && sib.tagName === node.tagName) idx++;
        sib = sib.previousSibling;
      }
      parts.unshift(node.tagName.toLowerCase() + "[" + idx + "]");
      node = node.parentNode;
    }
    return "/" + parts.join("/");
  };

  const results = [];
  const elements = document.querySelectorAll(SELECTORS);
  const seen = new Set();

  for (const el of elements) {
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) continue;

    const selector = getSelector(el);
    if (seen.has(selector)) continue;
    seen.add(selector);

    const visible = (
      rect.top < window.innerHeight && rect.bottom > 0 &&
      rect.left < window.innerWidth && rect.right > 0
    );

    if (visibleOnly && !visible) continue;

    const style = window.getComputedStyle(el);
    if (style.visibility === "hidden" || style.display === "none") continue;

    results.push({
      i: results.length,
      tag: el.tagName.toLowerCase(),
      id: el.id || null,
      text: (el.textContent || "").trim().substring(0, 60),
      selector: selector,
      x: Math.round(rect.left + rect.width / 2),
      y: Math.round(rect.top + rect.height / 2),
      w: Math.round(rect.width),
      h: Math.round(rect.height),
      visible: visible,
    });
  }

  return results;
};
