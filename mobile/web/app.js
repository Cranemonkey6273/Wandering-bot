const target = "https://dayzwanderingbot.com/app?source=native_fallback";

window.addEventListener("load", () => {
  const link = document.getElementById("open-app");
  if (link) {
    link.href = target;
  }
  window.setTimeout(() => {
    window.location.replace(target);
  }, 700);
});
