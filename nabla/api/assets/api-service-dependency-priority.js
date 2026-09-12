import { fetchTopology } from "./api-topology-data.js";

const PHASE_WEIGHT = new Map([
  ["bootstrap-runtime", 0],
  ["foundation", 1],
  ["network-edge", 2],
  ["primary-data", 3],
  ["secondary-data", 4],
  ["platform-services", 5],
  ["applications", 6],
]);
const CRITICALITY_WEIGHT = new Map([
  ["critical", 0],
  ["high", 1],
  ["medium", 2],
  ["low", 3],
]);

let nodes = new Map();
let scheduled = false;

function nodeIdFromHref(href) {
  const value = String(href || "");
  const match = value.match(/#service-(?:exposure-)?([a-z0-9-]+)$/i);
  return match?.[1] || "";
}

function rank(node) {
  const lifecycle = node?.lifecycle || {};
  return [
    PHASE_WEIGHT.get(String(lifecycle.phase || "")) ?? 99,
    Number.isFinite(Number(lifecycle.priority))
      ? Number(lifecycle.priority)
      : 9999,
    CRITICALITY_WEIGHT.get(String(node?.criticality || "")) ?? 9,
    String(node?.name || node?.id || "").toLocaleLowerCase(),
  ];
}

function compareRank(left, right) {
  for (let index = 0; index < left.length; index += 1) {
    if (left[index] === right[index]) continue;
    if (typeof left[index] === "number" && typeof right[index] === "number") {
      return left[index] - right[index];
    }
    return String(left[index]).localeCompare(String(right[index]));
  }
  return 0;
}

function nodeForLink(link) {
  return nodes.get(nodeIdFromHref(link?.getAttribute("href"))) || null;
}

function annotateLink(link) {
  const node = nodeForLink(link);
  if (!node) return;
  const lifecycle = node.lifecycle || {};
  const pieces = [node.name || node.id];
  if (lifecycle.phase) pieces.push(`lifecycle=${lifecycle.phase}`);
  if (Number.isFinite(Number(lifecycle.priority))) {
    pieces.push(`priority=${lifecycle.priority}`);
  }
  if (node.criticality) pieces.push(`criticality=${node.criticality}`);
  link.title = pieces.join(" · ");
}

function sortRelationList(list) {
  const items = [...list.children].filter(
    (item) => item instanceof HTMLElement,
  );
  items.sort((left, right) => {
    const leftOptional = /\boptional\b/i.test(left.textContent || "") ? 1 : 0;
    const rightOptional = /\boptional\b/i.test(right.textContent || "") ? 1 : 0;
    if (leftOptional !== rightOptional) return leftOptional - rightOptional;
    const leftLink = left.querySelector("a[href^='#service-']");
    const rightLink = right.querySelector("a[href^='#service-']");
    return compareRank(
      rank(nodeForLink(leftLink)),
      rank(nodeForLink(rightLink)),
    );
  });
  items.forEach((item) => {
    const link = item.querySelector("a[href^='#service-']");
    if (link) annotateLink(link);
    list.appendChild(item);
  });
}

function sortLinkedList(host) {
  const links = [...host.querySelectorAll(":scope > a[href^='#service-']")];
  links.sort((left, right) =>
    compareRank(rank(nodeForLink(left)), rank(nodeForLink(right))),
  );
  links.forEach((link) => {
    annotateLink(link);
    host.appendChild(link);
  });
}

function apply() {
  document
    .querySelectorAll(".service-detail-relation-block ul")
    .forEach(sortRelationList);
  document.querySelectorAll(".service-hover-list").forEach(sortLinkedList);
}

function schedule() {
  if (scheduled) return;
  scheduled = true;
  window.setTimeout(() => {
    scheduled = false;
    apply();
  }, 0);
}

export async function installServiceDependencyPriority() {
  try {
    const topology = await fetchTopology();
    nodes = new Map(
      (topology?.nodes || []).map((node) => [String(node.id), node]),
    );
  } catch {
    nodes = new Map();
  }
  schedule();
  document.addEventListener("health-board-refreshed", schedule);
  document.addEventListener("click", schedule, true);
}
