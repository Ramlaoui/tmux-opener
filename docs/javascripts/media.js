// Click a screenshot or recording to see it at full size; click again or press
// Escape to close. Delegated from the document so it keeps working across
// instant navigation.
document.addEventListener("click", (event) => {
  const media = event.target.closest(".demo");
  const open = document.querySelector(".zoom");
  if (open) {
    open.remove();
    return;
  }
  if (!media) return;
  const overlay = document.createElement("div");
  overlay.className = "zoom";
  overlay.setAttribute("role", "dialog");
  overlay.setAttribute("aria-label", media.getAttribute("aria-label") || media.alt || "Recording");
  const full = media.cloneNode(true);
  if (full.tagName === "VIDEO") {
    full.controls = true;
    full.play();
  }
  overlay.append(full);
  document.body.append(overlay);
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") document.querySelector(".zoom")?.remove();
});

// Play recordings only while they are on screen, and respect reduced motion.
const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
const watcher = new IntersectionObserver((entries) => {
  for (const entry of entries) {
    const video = entry.target;
    if (entry.isIntersecting && !reduceMotion.matches) video.play().catch(() => {});
    else video.pause();
  }
}, { threshold: 0.25 });

function watchVideos() {
  for (const video of document.querySelectorAll("video.demo")) {
    if (video.dataset.watched) continue;
    video.dataset.watched = "1";
    if (reduceMotion.matches) video.removeAttribute("autoplay");
    watcher.observe(video);
  }
}

if (typeof document$ !== "undefined") document$.subscribe(watchVideos);
else document.addEventListener("DOMContentLoaded", watchVideos);
