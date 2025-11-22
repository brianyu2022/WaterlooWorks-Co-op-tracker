document.addEventListener("DOMContentLoaded", () => {
  const stageCanvas = document.getElementById("stageChart");
  const velocityCanvas = document.getElementById("velocityChart");

  if (stageCanvas) {
    const labels = JSON.parse(stageCanvas.dataset.labels || "[]");
    const values = JSON.parse(stageCanvas.dataset.values || "[]");
    new Chart(stageCanvas, {
      type: "doughnut",
      data: {
        labels,
        datasets: [
          {
            data: values,
            backgroundColor: ["#0d6efd", "#ffc107", "#0dcaf0", "#20c997", "#e95454"],
            borderWidth: 0,
          },
        ],
      },
      options: {
        plugins: {
          legend: { position: "bottom" },
        },
        cutout: "60%",
      },
    });
  }

  if (velocityCanvas) {
    const labels = JSON.parse(velocityCanvas.dataset.labels || "[]");
    const values = JSON.parse(velocityCanvas.dataset.values || "[]");
    new Chart(velocityCanvas, {
      type: "bar",
      data: {
        labels,
        datasets: [
          {
            label: "Applications",
            data: values,
            backgroundColor: "#0d6efd",
            borderRadius: 6,
          },
        ],
      },
      options: {
        plugins: { legend: { display: false } },
        scales: {
          y: { beginAtZero: true, ticks: { precision: 0 } },
        },
      },
    });
  }
});
