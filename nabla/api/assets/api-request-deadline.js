// Bound both the HTTP handshake and response processing. A remote TrueNAS
// outage cannot hold the Cloud UI in a perpetual loading state.
export async function withRequestDeadline(task, timeoutMs = 6000) {
  const controller = new AbortController();
  let timeout;
  const deadline = new Promise((_, reject) => {
    timeout = window.setTimeout(() => {
      controller.abort();
      reject(new Error("Request deadline exceeded"));
    }, timeoutMs);
  });
  try {
    return await Promise.race([task(controller.signal), deadline]);
  } finally {
    window.clearTimeout(timeout);
  }
}
