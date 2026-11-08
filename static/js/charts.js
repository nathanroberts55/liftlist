/*
 * Chart.js initialisation for Stats and exercise detail (F-10).
 *
 * Data is server-rendered with json_script so the charts also work when the
 * /stats/api/ endpoints are not called directly. Colors come from CSS
 * variables, which keeps the charts in step with the active theme.
 */
(function () {
  "use strict";

  function cssVar(name, fallback) {
    var value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return value || fallback;
  }

  function palette() {
    return Array.from({ length: 8 }, function (_unused, index) {
      return cssVar("--ll-chart-" + (index + 1), "#2b7fff");
    });
  }

  function rgba(hex, alpha) {
    var value = hex.replace("#", "");
    if (value.length === 3) {
      value = value[0] + value[0] + value[1] + value[1] + value[2] + value[2];
    }
    var number = parseInt(value, 16);
    if (Number.isNaN(number)) {
      return hex;
    }
    var red = (number >> 16) & 255;
    var green = (number >> 8) & 255;
    var blue = number & 255;
    return "rgba(" + red + ", " + green + ", " + blue + ", " + alpha + ")";
  }

  function parseData(sourceId) {
    var element = document.getElementById(sourceId);
    if (!element) {
      return null;
    }
    try {
      return JSON.parse(element.textContent);
    } catch (error) {
      return null;
    }
  }

  function buildLine(canvas, data, colors) {
    var color = colors[(data.color_index || 0) % colors.length];
    return new Chart(canvas, {
      type: "line",
      data: {
        labels: data.labels,
        datasets: [
          {
            label: data.label || "Top set",
            data: data.values,
            borderColor: color,
            backgroundColor: rgba(color, 0.16),
            pointBackgroundColor: color,
            borderWidth: 2,
            pointRadius: 3,
            pointHoverRadius: 5,
            tension: 0.25,
            fill: true,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { intersect: false, mode: "index" },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: function (context) {
                return (data.tooltips && data.tooltips[context.dataIndex]) || context.formattedValue;
              },
            },
          },
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 6 },
          },
          y: {
            beginAtZero: false,
            grid: { color: cssVar("--ll-border", "#2a3038") },
            ticks: { precision: 0 },
          },
        },
      },
    });
  }

  function buildBar(canvas, data, colors) {
    return new Chart(canvas, {
      type: "bar",
      data: {
        labels: data.labels,
        datasets: data.series.map(function (series) {
          return {
            label: series.name,
            data: series.values,
            backgroundColor: colors[series.color_index % colors.length],
            borderRadius: 4,
          };
        }),
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { intersect: false, mode: "index" },
        plugins: {
          legend: {
            display: true,
            position: "bottom",
            labels: { boxWidth: 10, boxHeight: 10, usePointStyle: true },
          },
          tooltip: {
            callbacks: {
              label: function (context) {
                var value = context.formattedValue;
                return context.dataset.label + ": " + value + " " + (data.unit || "");
              },
            },
          },
        },
        scales: {
          x: {
            stacked: true,
            grid: { display: false },
            ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 8 },
          },
          y: {
            stacked: true,
            beginAtZero: true,
            grid: { color: cssVar("--ll-border", "#2a3038") },
            ticks: { precision: 0 },
          },
        },
      },
    });
  }

  function init() {
    if (typeof Chart === "undefined") {
      return;
    }
    Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
    Chart.defaults.color = cssVar("--ll-text-muted", "#9aa3af");
    Chart.defaults.borderColor = cssVar("--ll-border", "#2a3038");

    var colors = palette();
    document.querySelectorAll("canvas[data-chart]").forEach(function (canvas) {
      var data = parseData(canvas.dataset.chartSource);
      if (!data || !data.labels || !data.labels.length) {
        return;
      }
      if (canvas.dataset.chart === "line") {
        buildLine(canvas, data, colors);
      } else if (canvas.dataset.chart === "bar") {
        buildBar(canvas, data, colors);
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
