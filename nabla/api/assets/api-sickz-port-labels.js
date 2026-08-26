const PORT_SERVICES = {
  22: "SSH",
  3000: "ntopng",
  4000: "LiteLLM",
  8200: "Vault",
  10443: "pfSense",
};

function chipStateFromPfsenseRow(wrap) {
  const primary = wrap.querySelector(".sickz-pfsense-row .health-row-primary");
  if (!primary) return { cls: "sickz-pfsense-port--na", text: "indeterminate" };
  if (primary.classList.contains("health-row-primary--green")) {
    return { cls: "sickz-pfsense-port--closed", text: "blocked · expected" };
  }
  if (primary.classList.contains("health-row-primary--red")) {
    return { cls: "sickz-pfsense-port--open", text: "reachable · unexpected" };
  }
  return { cls: "sickz-pfsense-port--na", text: "indeterminate" };
}

function ensureServiceLabel(chip) {
  const num = chip.querySelector(".sickz-pfsense-port-num");
  const state = chip.querySelector(".sickz-pfsense-port-st");
  if (!num || !state || chip.querySelector(".sickz-pfsense-port-svc")) return;
  const service = PORT_SERVICES[Number(num.textContent)];
  if (!service) return;
  const label = document.createElement("span");
  label.className = "sickz-pfsense-port-svc";
  label.textContent = service;
  state.before(label);
}

function ensurePfsense10443(wrap) {
  const ports = wrap.querySelector(".sickz-pfsense-ports");
  if (!ports) return;
  const existing = Array.from(ports.querySelectorAll(".sickz-pfsense-port-num")).some(
    (node) => Number(node.textContent) === 10443,
  );
  if (existing) return;

  const state = chipStateFromPfsenseRow(wrap);
  const chip = document.createElement("span");
  chip.className = `sickz-pfsense-port ${state.cls}`;
  chip.title = `TCP 10443 · pfSense: ${state.text} · expected blocked from FastAPI Cloud`;
  chip.innerHTML =
    '<span class="sickz-pfsense-port-num">10443</span>' +
    '<span class="sickz-pfsense-port-svc">pfSense</span>' +
    `<span class="sickz-pfsense-port-st">${state.text}</span>`;
  ports.appendChild(chip);
}

function decoratePfsensePorts() {
  const wrap = document.getElementById("sickz-pfsense-wrap");
  if (!wrap || wrap.hidden) return;
  wrap.querySelectorAll(".sickz-pfsense-port").forEach(ensureServiceLabel);
  ensurePfsense10443(wrap);
}

export function installPfsensePortLabels() {
  const wrap = document.getElementById("sickz-pfsense-wrap");
  if (!wrap) return;
  new MutationObserver(decoratePfsensePorts).observe(wrap, {
    childList: true,
    subtree: true,
  });
  decoratePfsensePorts();
}
