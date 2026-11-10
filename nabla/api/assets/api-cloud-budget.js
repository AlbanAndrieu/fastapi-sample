// FastAPI Cloud Hobby budgets are published references, not account usage.
// Inspect local process RSS only on an explicit OWNER click. Never poll.
export const NANO_REFERENCE_BYTES = 500 * 1024 * 1024;

export function nanoProcessMemoryAssessment(rssBytes) {
  if (typeof rssBytes !== "number" || !Number.isFinite(rssBytes) || rssBytes < 0) {
    return { state: "unknown", percentage: null };
  }
  const percentage = (100 * rssBytes) / NANO_REFERENCE_BYTES;
  const state = percentage >= 100 ? "danger" : percentage >= 80 ? "warning" : "unknown";
  return { state, percentage };
}

export function installCloudProcessBudgetSample() {
  const button = document.getElementById("runtime-cloud-process-refresh");
  if (!button || button.dataset.bound === "true") return;
  button.dataset.bound = "true";
  button.addEventListener("click", async () => {
    const memory = document.getElementById("runtime-cloud-process-rss");
    const status = document.getElementById("runtime-cloud-process-status");
    const container = button.closest(".runtime-cloud-process");
    if (!memory || !status || !container) return;
    button.disabled = true;
    memory.textContent = "Checking…";
    container.dataset.severity = "unknown";
    status.textContent = "Reading one OWNER-only process snapshot…";
    try {
      const response = await fetch("/api/runtime/resources", {
        method: "GET",
        credentials: "same-origin",
        cache: "no-store",
        headers: { Accept: "application/json" },
      });
      if (response.status === 401 || response.status === 403) {
        memory.textContent = "Restricted";
        status.textContent = "OWNER session required. No resource data was read.";
        return;
      }
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const sample = await response.json();
      const rss = sample?.rss_bytes;
      const assessed = nanoProcessMemoryAssessment(rss);
      if (assessed.percentage === null) throw new Error("Process RSS not reported");
      memory.textContent = `${(rss / (1024 * 1024)).toFixed(1)} MiB process RSS · ${assessed.percentage.toFixed(1)}% of Nano 500 MiB`;
      container.dataset.severity = assessed.state;
      const cpuSeconds = sample?.process_cpu_seconds_total;
      const cpuNote = typeof cpuSeconds === "number" && Number.isFinite(cpuSeconds)
        ? ` CPU time: ${cpuSeconds.toFixed(1)} s cumulative (not CPU%).`
        : "";
      if (assessed.state === "danger") {
        status.textContent = `⚠ Process RSS exceeds the Nano reference. Confirm actual replica size and provider Metrics.${cpuNote}`;
      } else if (assessed.state === "warning") {
        status.textContent = `⚠ Process RSS approaches the Nano reference (≥80%). Confirm full replica memory in provider Metrics.${cpuNote}`;
      } else {
        status.textContent = `Process RSS is below 80% of the Nano reference. Total replica memory, compute hours and billed usage are still unknown.${cpuNote}`;
      }
    } catch (error) {
      memory.textContent = "Unavailable";
      container.dataset.severity = "unknown";
      status.textContent = `Could not read process sample: ${String(error?.message || error)}. No usage estimate available.`;
    } finally {
      button.disabled = false;
    }
  });
}
