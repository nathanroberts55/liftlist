/* Drag reordering for plan days. The up/down buttons are the phone fallback. */
(function () {
  "use strict";

  function rows(container) {
    return container.querySelectorAll("[data-item-id]");
  }

  function submitOrder(container) {
    var section = container.closest("section");
    var form = section ? section.querySelector("[data-reorder-form]") : null;
    if (!form) {
      return;
    }
    var ids = Array.prototype.map
      .call(rows(container), function (row) {
        return row.getAttribute("data-item-id");
      })
      .filter(Boolean);
    var input = form.querySelector('input[name="ordered_ids"]');
    if (input) {
      input.value = ids.join(",");
    }
    if (typeof form.requestSubmit === "function") {
      form.requestSubmit();
    } else {
      form.submit();
    }
  }

  function initSortable(container) {
    if (container.dataset.sortableReady === "true") {
      return;
    }
    if (typeof Sortable === "undefined") {
      return;
    }
    if (!window.matchMedia("(min-width: 768px)").matches) {
      return;
    }

    container.dataset.sortableReady = "true";
    var initial = Array.prototype.map
      .call(rows(container), function (row) {
        return row.getAttribute("data-item-id");
      })
      .join(",");

    Sortable.create(container, {
      animation: 150,
      handle: "[data-drag-handle]",
      ghostClass: "opacity-40",
      onEnd: function () {
        var current = Array.prototype.map
          .call(rows(container), function (row) {
            return row.getAttribute("data-item-id");
          })
          .join(",");
        if (current !== initial) {
          submitOrder(container);
        }
      },
    });
  }

  function initAll(root) {
    var scope = root && root.querySelectorAll ? root : document;
    if (scope.matches && scope.matches("[data-sortable]")) {
      initSortable(scope);
    }
    scope.querySelectorAll("[data-sortable]").forEach(initSortable);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      initAll(document);
    });
  } else {
    initAll(document);
  }

  if (!window.__liftListReorderBound) {
    window.__liftListReorderBound = true;
    document.addEventListener("htmx:afterSwap", function () {
      // For an outerHTML swap the original target is detached. Scan the live
      // document so the replacement container is initialized too; the
      // data-sortable-ready guard keeps existing containers from double-binding.
      initAll(document);
    });
  }
})();
