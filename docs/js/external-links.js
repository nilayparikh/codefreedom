// Open external links in a new window
document.addEventListener("DOMContentLoaded", function () {
  var origin = window.location.origin;
  document.querySelectorAll("a[href]").forEach(function (link) {
    var href = link.getAttribute("href");
    if (href && (href.indexOf("http://") === 0 || href.indexOf("https://") === 0)) {
      var a = document.createElement("a");
      a.href = href;
      if (a.origin !== origin) {
        link.setAttribute("target", "_blank");
        link.setAttribute("rel", "noopener noreferrer");
      }
    }
  });
});
