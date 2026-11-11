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

export function cgroupMemoryAssessment(cgroup) {
  const used = cgroup?.memory_current_bytes;
  const limit = cgroup?.memory_limit_bytes;
  if (
    typeof used !== "number" || !Number.isFinite(used) || used < 0 ||
    typeof limit !== "number" || !Number.isFinite(limit) || limit <= 0
  ) {
    return { state: "unknown", percentage: null };
  }
  const percentage = 100 * used / limit;
  return {
    state: percentage >= 100 ? "danger" : percentage >= 80 ? "warning" : "unknown",
    percentage,
  };
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
      const processAssessed = nanoProcessMemoryAssessment(rss);
      if (processAssessed.percentage === null) throw new Error("Process RSS not reported");
      const cgroup = sample?.cgroup;
      const containerAssessed = cgroupMemoryAssessment(cgroup);
      const actualCgroup = containerAssessed.percentage !== null;
      const assessed = actualCgroup ? containerAssessed : processAssessed;
      memory.textContent = actualCgroup
        ? `${(cgroup.memory_current_bytes / (1024 * 1024)).toFixed(1)} MiB container · ${assessed.percentage.toFixed(1)}% of measured cgroup limit · ${(rss / (1024 * 1024)).toFixed(1)} MiB process RSS`
        : `${(rss / (1024 * 1024)).toFixed(1)} MiB process RSS · ${assessed.percentage.toFixed(1)}% of Nano 500 MiB`;
      container.dataset.severity = assessed.state;
      const cpuSeconds = sample?.process_cpu_seconds_total;
      const cpuNote = typeof cpuSeconds === "number" && Number.isFinite(cpuSeconds)
        ? ` CPU time: ${cpuSeconds.toFixed(1)} s cumulative (not CPU%).`
        : "";
      const sourceLabel = actualCgroup ? "cgroup memory limit" : "Nano RSS reference";
      const oom = Number.isSafeInteger(cgroup?.oom_kill_count) && cgroup.oom_kill_count >= 0
        ? ` Cgroup OOM kills (cumulative): ${cgroup.oom_kill_count}.`
        : "";
      if (assessed.state === "danger") {
        status.textContent = `⚠ Memory reaches/exceeds the ${sourceLabel}. Confirm provider Metrics.${cpuNote}${oom}`;
      } else if (assessed.state === "warning") {
        status.textContent = `⚠ Memory approaches the ${sourceLabel} (≥80%). Verify replica memory in provider Metrics.${cpuNote}${oom}`;
      } else {
        status.textContent = `Memory is below 80% of the ${sourceLabel}. This is one instant, not compute hours or account billing.${cpuNote}${oom}`;
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
