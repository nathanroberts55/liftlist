/*
 * Runner helpers.
 *
 * runnerTimer is the Alpine component behind the rest screen. It counts toward
 * a fixed end time, so throttling in a background tab cannot drift; the next
 * set form is already in the DOM and is revealed when the countdown ends.
 *
 * setEntry powers the +/- buttons and the tap-again-to-clear difficulty
 * selector. Without JavaScript every field is still directly typeable and the
 * server renders the next set screen directly, so the workflow never breaks.
 */
(function () {
  "use strict";

  function formatDuration(totalSeconds) {
    var safe = Math.max(0, Math.round(totalSeconds));
    var minutes = Math.floor(safe / 60);
    var seconds = safe % 60;
    return minutes + ":" + String(seconds).padStart(2, "0");
  }

  window.runnerTimer = function runnerTimer(seconds) {
    var initial = Math.max(0, Math.round(Number(seconds) || 0));
    return {
      total: initial,
      remaining: initial,
      resting: initial > 0,
      endAt: 0,
      intervalId: null,
      announcement: "",
      boundTick: null,

      init: function () {
        this.boundTick = this.tick.bind(this);
        this.endAt = Date.now() + this.remaining * 1000;
        this.tick();
        this.intervalId = window.setInterval(this.boundTick, 250);
        if (this.$refs.setPanel) {
          this.$refs.setPanel.inert = true;
        }
        this.focusSkip();
        document.addEventListener("visibilitychange", this.boundTick);
      },

      destroy: function () {
        if (this.intervalId) {
          window.clearInterval(this.intervalId);
          this.intervalId = null;
        }
        if (this.boundTick) {
          document.removeEventListener("visibilitychange", this.boundTick);
          this.boundTick = null;
        }
      },

      get label() {
        return formatDuration(this.remaining);
      },

      get progress() {
        if (!this.total) {
          return 100;
        }
        var percent = (this.remaining / this.total) * 100;
        return Math.max(0, Math.min(100, percent));
      },

      focusSkip: function () {
        var self = this;
        this.$nextTick(function () {
          var skip = document.getElementById("rest-skip");
          if (skip && self.resting) {
            skip.focus({ preventScroll: true });
          }
        });
      },

      tick: function () {
        if (!this.resting) {
          return;
        }
        var previous = this.remaining;
        this.remaining = Math.max(0, Math.ceil((this.endAt - Date.now()) / 1000));
        if (previous > 10 && this.remaining <= 10 && this.remaining > 0) {
          this.announcement = "10 seconds left";
        }
        if (this.remaining <= 0) {
          this.finish();
        }
      },

      adjust: function (delta) {
        if (!this.resting) {
          return;
        }
        this.endAt = Math.max(Date.now(), this.endAt + delta * 1000);
        var left = Math.max(0, Math.ceil((this.endAt - Date.now()) / 1000));
        this.total = Math.max(this.total, left);
        this.tick();
      },

      finish: function () {
        if (!this.resting) {
          return;
        }
        this.resting = false;
        this.announcement = "Rest over. Next set ready.";
        if (this.intervalId) {
          window.clearInterval(this.intervalId);
          this.intervalId = null;
        }
        if (this.$refs.setPanel) {
          this.$refs.setPanel.inert = false;
        }
        if (typeof window.liftListBeep === "function") {
          window.liftListBeep();
        }
        var panel = this.$refs.setPanel;
        var target = panel ? panel.querySelector("[data-autofocus]") : null;
        if (target) {
          window.setTimeout(function () {
            target.focus({ preventScroll: true });
            if (typeof target.select === "function") {
              target.select();
            }
          }, 80);
        }
      },
    };
  };

  function stepValue(button) {
    var id = button.getAttribute("data-step-target");
    var target = id ? document.getElementById(id) : null;
    if (!target) {
      return;
    }
    var delta = Number(button.getAttribute("data-step"));
    if (!Number.isFinite(delta)) {
      delta = 0;
    }
    var current = Number(target.value);
    if (!Number.isFinite(current)) {
      current = 0;
    }
    var next = Math.max(0, current + delta);
    next = Math.round(next * 1000) / 1000;
    target.value = String(next);
    target.dispatchEvent(new Event("input", { bubbles: true }));
    target.focus({ preventScroll: true });
    if (typeof target.select === "function") {
      target.select();
    }
  }

  function findDifficultyRadio(element) {
    if (!element || !element.closest) {
      return null;
    }
    if (element.matches && element.matches("input[data-difficulty]")) {
      return element;
    }
    var label = element.closest("label");
    return label ? label.querySelector("input[data-difficulty]") : null;
  }

  document.addEventListener("click", function (event) {
    var button = event.target.closest ? event.target.closest("[data-step-target]") : null;
    if (button && button.getAttribute("data-step") !== null) {
      event.preventDefault();
      stepValue(button);
    }
  });

  // A second tap on the selected difficulty clears it (PRD F-05). A click on
  // an unchecked radio checks it and remembers the choice; the next click on
  // that same radio clears it again.
  var lastDifficulty = null;

  document.addEventListener(
    "click",
    function (event) {
      var radio =
        event.target.matches && event.target.matches("input[data-difficulty]")
          ? event.target
          : null;
      if (!radio) {
        return;
      }
      if (!radio.checked) {
        if (lastDifficulty === radio) {
          lastDifficulty = null;
        }
        return;
      }
      if (lastDifficulty === radio) {
        radio.checked = false;
        lastDifficulty = null;
      } else {
        lastDifficulty = radio;
      }
    },
    true
  );

  document.addEventListener("keydown", function (event) {
    if (event.key !== " " && event.key !== "Enter") {
      return;
    }
    var radio = findDifficultyRadio(event.target);
    if (radio && radio.checked) {
      event.preventDefault();
      radio.checked = false;
    }
  });

  function focusRunnerField() {
    var skip = document.getElementById("rest-skip");
    if (skip && skip.offsetParent !== null) {
      skip.focus({ preventScroll: true });
      return;
    }
    var runner = document.getElementById("runner");
    if (!runner) {
      return;
    }
    var target = runner.querySelector("[data-autofocus]");
    if (target && !target.disabled) {
      target.focus({ preventScroll: true });
      if (typeof target.select === "function" && target.type !== "radio") {
        target.select();
      }
    }
  }

  document.addEventListener("htmx:afterSettle", focusRunnerField);

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", focusRunnerField);
  } else {
    focusRunnerField();
  }
})();
