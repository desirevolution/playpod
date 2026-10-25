let registered = false;
export function registerPwa() {
  if (registered || !window.isSecureContext || !("serviceWorker" in navigator))
    return;
  registered = true;
  // Installation/update never reloads a tab or starts audio.
  void navigator.serviceWorker
    .register("/sw.js", { scope: "/", updateViaCache: "none" })
    .catch(() => {});
}
