const SECURITY_CONTROL_ICONS = [
  ["Snort", "🛡️"],
  ["pfBlockerNG", "🚫"],
  ["Unbound", "🌐"],
];

function decorateText(value) {
  let output = String(value || "");
  for (const [label, icon] of SECURITY_CONTROL_ICONS) {
    if (output.includes(`${icon} ${label}`)) continue;
    output = output.replaceAll(label, `${icon} ${label}`);
  }
  return output;
}

function decorateSecurityControls(root) {
  root.querySelectorAll(".truenas-stage-detail").forEach((node) => {
    const decorated = decorateText(node.textContent);
    if (decorated !== node.textContent) node.textContent = decorated;
  });
}

export function installSecurityControlIcons() {
  const pipeline = document.getElementById("truenas-pipeline");
  if (!pipeline) return;

  decorateSecurityControls(pipeline);
  const observer = new MutationObserver(() => decorateSecurityControls(pipeline));
  observer.observe(pipeline, {
    childList: true,
    subtree: true,
    characterData: true,
  });
}
