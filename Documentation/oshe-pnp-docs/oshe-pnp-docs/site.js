// OSHE Pick and Place docs: small helpers. No libraries.
document.addEventListener("DOMContentLoaded", function () {
  // Image slots: each <figure class="img-slot" data-src="images/NAME"> starts as a gray
  // placeholder. If images/NAME exists, it replaces the placeholder, so adding a picture
  // is just a matter of saving it into images/ with the right name.
  document.querySelectorAll("figure.img-slot[data-src]").forEach(function (fig) {
    var img = new Image();
    img.alt = fig.getAttribute("data-alt") || "";
    img.onload = function () {
      var box = fig.querySelector(".img-placeholder");
      if (box) box.replaceWith(img);
      fig.classList.add("has-image");
    };
    img.src = fig.getAttribute("data-src");
  });

  // Mobile menu: the button opens and closes the sidebar on small screens.
  var toggle = document.querySelector(".nav-toggle");
  var nav = document.getElementById("site-nav");
  if (!toggle || !nav) return;

  function setOpen(open) {
    document.body.classList.toggle("nav-open", open);
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
  }

  toggle.addEventListener("click", function () {
    setOpen(!document.body.classList.contains("nav-open"));
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && document.body.classList.contains("nav-open")) {
      setOpen(false);
      toggle.focus();
    }
  });
  nav.addEventListener("click", function (e) {
    if (e.target.closest("a")) setOpen(false);
  });
  // Tapping the dimmed page beside the open menu closes it.
  document.addEventListener("click", function (e) {
    if (document.body.classList.contains("nav-open") &&
        !nav.contains(e.target) && !toggle.contains(e.target)) {
      setOpen(false);
    }
  });
});
