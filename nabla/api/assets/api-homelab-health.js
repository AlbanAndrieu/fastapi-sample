let homelabHealthRequest = null;

export function resetHomelabHealthRequest() {
  homelabHealthRequest = null;
}

export function fetchHomelabHealth() {
  if (!homelabHealthRequest) {
    homelabHealthRequest = fetch("/api/homelab/health", {
      cache: "no-store",
      headers: { Accept: "application/json", "Cache-Control": "no-cache" },
    }).then((response) => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.json();
    });
  }
  return homelabHealthRequest;
}
