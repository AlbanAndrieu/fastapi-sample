export function normalize(value) {
  return String(value || "")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .toLowerCase();
}

export function hostOf(value) {
  if (!value) return "";
  try {
    return new URL(String(value)).hostname.toLowerCase();
  } catch {
    return "";
  }
}
