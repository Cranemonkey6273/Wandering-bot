const target = "https://dayzwanderingbot.com/app?source=native";

window.addEventListener("load", () => {
  const link = document.getElementById("open-app");
  const retry = document.getElementById("retry-button");
  const label = document.getElementById("connection-label");
  const dot = document.getElementById("connection-dot");

  const setStatus = () => {
    const online = navigator.onLine !== false;
    if (label) {
      label.textContent = online ? "Connected to Wandering Bot" : "Offline - waiting for network";
    }
    if (dot) {
      dot.classList.toggle("offline", !online);
    }
  };

  const openDashboard = () => {
    window.location.assign(target);
  };

  if (link) {
    link.href = target;
    link.addEventListener("click", (event) => {
      event.preventDefault();
      openDashboard();
    });
  }

  if (retry) {
    retry.addEventListener("click", openDashboard);
  }

  window.addEventListener("online", setStatus);
  window.addEventListener("offline", setStatus);
  setStatus();

  window.setTimeout(() => {
    if (navigator.onLine !== false) {
      window.location.replace(target);
    }
  }, 900);
});
