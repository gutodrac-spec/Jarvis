// Service worker: recebe a "ligação" do Jarvis mesmo com o app fechado
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

self.addEventListener("push", (event) => {
  let data = {};
  try { data = event.data.json(); } catch { data = { title: "Jarvis", body: event.data && event.data.text() }; }
  const isCall = data.kind === "call";
  const title = data.title || (isCall ? "📞 Jarvis está te ligando" : "Jarvis");
  const options = {
    body: data.body || "",
    icon: "/icon-192.png",
    badge: "/icon-192.png",
    tag: isCall ? "jarvis-call" : "jarvis-notify",
    renotify: true,
    requireInteraction: isCall,
    vibrate: isCall ? [600, 300, 600, 300, 600, 300, 600] : [200],
    data: { ...data, url: isCall ? `/?call=${data.callId}` : "/" },
    actions: isCall
      ? [{ action: "accept", title: "✅ Atender" }, { action: "decline", title: "❌ Recusar" }]
      : [],
  };
  event.waitUntil(
    (async () => {
      await self.registration.showNotification(title, options);
      // se o app estiver aberto, mostra a tela de chamada direto
      const wins = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
      wins.forEach((w) => w.postMessage({ type: "push", data }));
    })()
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const data = event.notification.data || {};
  let url = data.url || "/";
  if (event.action === "accept") url += (url.includes("?") ? "&" : "?") + "action=accept";
  if (event.action === "decline") url += (url.includes("?") ? "&" : "?") + "action=decline";
  event.waitUntil(
    (async () => {
      const wins = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
      for (const w of wins) {
        if ("focus" in w) {
          w.postMessage({ type: "notification_action", action: event.action || "open", data });
          return w.focus();
        }
      }
      return self.clients.openWindow(url);
    })()
  );
});
