/* 离线兜底：页面与图标缓存，数据始终走网络并保留最后一次可用结果。
   路径全部用相对写法，这样本地 http://127.0.0.1:8000/ 和
   GitHub Pages 的 /<仓库名>/ 子路径下都能用。
   注意：局域网 http://192.168.x.x 属于非安全上下文，浏览器不会注册 SW；
   此时页面照常工作，只是没有离线能力。部署到 https 后自动生效。 */
const SHELL = "radar-shell-v4";
const ASSETS = ["./", "./setup.html", "./manifest.webmanifest",
                "./assets/icon-192.png", "./assets/icon-512.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(SHELL).then((c) => c.addAll(ASSETS)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== SHELL).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);

  // 数据：网络优先，失败回落到缓存
  if (url.pathname.indexOf("/data/") >= 0) {
    e.respondWith(
      fetch(e.request)
        .then((res) => {
          const copy = res.clone();
          caches.open(SHELL).then((c) => c.put(e.request, copy));
          return res;
        })
        .catch(() => caches.match(e.request))
    );
    return;
  }

  // 其余：缓存优先，后台更新
  if (e.request.method === "GET") {
    e.respondWith(
      caches.match(e.request).then((hit) => {
        const net = fetch(e.request).then((res) => {
          const copy = res.clone();
          caches.open(SHELL).then((c) => c.put(e.request, copy));
          return res;
        }).catch(() => hit);
        return hit || net;
      })
    );
  }
});
