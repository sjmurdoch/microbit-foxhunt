/* Print buttons for the teaching pages.
   One file rather than an inline handler on each of the three, so there is a
   single copy to change. */
document.addEventListener("DOMContentLoaded", function () {
  var buttons = document.querySelectorAll("[data-print]");
  for (var i = 0; i < buttons.length; i++) {
    buttons[i].hidden = false;
    buttons[i].addEventListener("click", function () { window.print(); });
  }
});
