/*
 * Two short beeps for the rest timer. Uses Web Audio so there is no asset to
 * load and no network dependency in the gym. Browsers require a user gesture
 * before audio can start, so the context is primed on the first pointer event.
 */
(function () {
  "use strict";

  var context = null;

  function getContext() {
    if (context) {
      return context;
    }
    var AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) {
      return null;
    }
    try {
      context = new AudioCtx();
    } catch (error) {
      context = null;
    }
    return context;
  }

  function prime() {
    var ctx = getContext();
    if (ctx && ctx.state === "suspended" && typeof ctx.resume === "function") {
      ctx.resume().catch(function () {});
    }
  }

  document.addEventListener("pointerdown", prime, { once: true, passive: true });

  window.liftListBeep = function liftListBeep() {
    var ctx = getContext();
    if (!ctx) {
      return;
    }
    if (ctx.state === "suspended" && typeof ctx.resume === "function") {
      ctx.resume().catch(function () {});
    }
    var start = ctx.currentTime;
    [0, 0.18].forEach(function (offset) {
      var oscillator = ctx.createOscillator();
      var gain = ctx.createGain();
      oscillator.type = "sine";
      oscillator.frequency.value = 880;
      gain.gain.setValueAtTime(0.0001, start + offset);
      gain.gain.exponentialRampToValueAtTime(0.22, start + offset + 0.01);
      gain.gain.exponentialRampToValueAtTime(0.0001, start + offset + 0.12);
      oscillator.connect(gain);
      gain.connect(ctx.destination);
      oscillator.start(start + offset);
      oscillator.stop(start + offset + 0.14);
    });
  };
})();
