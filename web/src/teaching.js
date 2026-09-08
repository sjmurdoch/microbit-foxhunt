/* Print buttons for the teaching pages, and the page count.
   One file rather than an inline handler on each of the three, so there is a
   single copy to change. It is bundled rather than copied so that it shares
   analytics.js with the setup page: the beacon exists once in the repo. */
import { pageview, event } from "./analytics.js";

document.addEventListener("DOMContentLoaded", function () {
  var buttons = document.querySelectorAll("[data-print]");
  for (var i = 0; i < buttons.length; i++) {
    buttons[i].hidden = false;
    buttons[i].addEventListener("click", function () { window.print(); });
  }
  pageview();
});

/* Counted on the event rather than the button, so Ctrl-P and the print button
   both land -- whether these pages actually get printed is the question, and
   AGENTS.md section 8 has print rendering off this machine as an open item. */
window.addEventListener("beforeprint", function () {
  var page = location.pathname.split("/").pop().replace(/\.html$/, "");
  event("print/" + (page || "index"));
});
