(() => {
  const _f = window.fetch;
  window.fetch = function (input, init) {
    const url = typeof input === "string" ? input : input?.url || "";
    const same = url.startsWith("/") || url.startsWith(location.origin);
    const ollama = url.includes("11434");
    if (same && !ollama) {
      init = init || {};
      const h = new Headers(init.headers);
      if (!h.has("Authorization")) h.set("Authorization", "Bearer atlas-local");
      init.headers = h;
    }
    return _f.call(this, input, init);
  };
})();
