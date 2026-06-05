// Open external links in a new tab.
//
// MkDocs Material's `navigation.instant` feature replaces page content
// via XHR (SPA-style). The classic `DOMContentLoaded` event fires only
// once on the initial page load, so any links added by subsequent
// navigations would never be processed. We subscribe to the `document$`
// Observable that Material exposes globally -- it emits on every page
// transition (initial load + every instant-navigation).
(function () {
  function processExternalLinks() {
    var origin = window.location.origin;
    var links = document.querySelectorAll(
      "a[href]:not([data-external-processed])"
    );
    links.forEach(function (link) {
      // Mark processed so the same link isn't re-evaluated on every event.
      link.setAttribute("data-external-processed", "true");
      var href = link.getAttribute("href");
      if (!href) return;
      if (href.indexOf("http://") !== 0 && href.indexOf("https://") !== 0) {
        return;
      }
      var url;
      try {
        url = new URL(href);
      } catch (e) {
        return;
      }
      // Same-origin absolute URLs (e.g. absolute site URLs) stay in the same tab.
      if (url.origin === origin) return;
      link.setAttribute("target", "_blank");
      link.setAttribute("rel", "noopener noreferrer");
    });
  }

  if (
    typeof document$ !== "undefined" &&
    document$ &&
    typeof document$.subscribe === "function"
  ) {
    document$.subscribe(processExternalLinks);
  } else {
    // Fallback: theme without `document$` support, or `navigation.instant` disabled.
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", processExternalLinks);
    } else {
      processExternalLinks();
    }
  }
})();
