/*
 * Preserve keyboard focus across an HTMX swap.
 *
 * hx-disabled-elt disables the pressed control while its request is in flight,
 * which moves focus to the document. Remember the active element's id before
 * the request and restore it after the swap when the replacement exists.
 */
(function () {
  "use strict";

  if (window.__liftListFocusBound) {
    return;
  }
  window.__liftListFocusBound = true;

  var focusId = null;

  document.addEventListener("htmx:beforeRequest", function () {
    var active = document.activeElement;
    focusId = active && active !== document.body && active.id ? active.id : null;
  });

  document.addEventListener("htmx:afterSettle", function () {
    if (!focusId) {
      return;
    }
    var replacement = document.getElementById(focusId);
    focusId = null;
    if (replacement && replacement.isConnected && !replacement.disabled) {
      replacement.focus({ preventScroll: true });
    }
  });
})();
