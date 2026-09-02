const SELFHST_ICON_CDN = "https://cdn.jsdelivr.net/gh/selfhst/icons@main/svg/";

const HEALTHZ_ICON_IMG = {
  postgres: "postgresql.svg",
  redis: "redis.svg",
  supabase: "supabase.svg",
  openstack_me: "ovh.svg",
  tavily: "searxng.svg",
  brave: "brave.svg",
  google: "google.svg",
  appwrite: "appwrite.svg",
  keycloak: "keycloak.svg",
  sentry: "sentry.svg",
  datadog: "datadog.svg",
  pyroscope: "grafana.svg",
  litellm: "litellm.svg",
  cloudflare: "cloudflare.svg",
  pfsense: "pfsense.svg",
  albandrieu_twofactor: "2fauth.svg",
  albandrieu_nexus: "sonatype-nexus-repository.svg",
  albandrieu_keycloak_ui: "keycloak.svg",
  albandrieu_homarr: "homarr.svg",
  albandrieu_plumber_api: "docker.svg",
  albandrieu_reactive_resume: "reactive-resume.svg",
  albandrieu_vaultwarden: "vaultwarden.svg",
  sickz_url: "pfsense.svg",
};

const ICON_PATHS = {
  unleash:
    '<path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><line x1="4" x2="4" y1="22" y2="15"/>',
  infra_host: '<circle cx="12" cy="12" r="9"/><path d="M8 12h8M12 8v8"/>',
  _default:
    '<rect x="5" y="5" width="14" height="14" rx="2"/><path d="M9 12h6M12 9v6"/>',
};

function normalizeIconSrc(raw) {
  const value = raw == null ? "" : String(raw).trim();
  if (!value) return "";
  if (value.toLowerCase().slice(0, 2) === "//") return `https:${value}`;
  return value;
}

function iconSrcIsHttpUrl(value) {
  const lower = String(value).toLowerCase();
  return lower.slice(0, 8) === "https://" || lower.slice(0, 7) === "http://";
}

function serviceIconSvg(key, statusCls) {
  const imgFile = HEALTHZ_ICON_IMG[key];
  if (imgFile) {
    return (
      `<span class="health-row-icon health-row-icon--img health-row-icon--${statusCls}" aria-hidden="true">` +
      `<img src="${SELFHST_ICON_CDN}${imgFile}" alt="" width="26" height="26" loading="lazy" referrerpolicy="strict-origin-when-cross-origin" />` +
      "</span>"
    );
  }
  const path =
    ICON_PATHS[key] ||
    (key.indexOf("albandrieu_") === 0 ? ICON_PATHS.infra_host : ICON_PATHS._default);
  return (
    `<span class="health-row-icon health-row-icon--${statusCls}" aria-hidden="true">` +
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">' +
    path +
    "</svg></span>"
  );
}

export function escapeText(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export function rowIcon(check, key, statusCls) {
  let rawPick = "";
  if (check.icon_src && typeof check.icon_src === "string") rawPick = check.icon_src;
  else if (check.iconSrc && typeof check.iconSrc === "string") rawPick = check.iconSrc;
  const absRaw = normalizeIconSrc(rawPick);
  if (iconSrcIsHttpUrl(absRaw)) {
    return (
      `<span class="health-row-icon health-row-icon--img health-row-icon--${statusCls}" aria-hidden="true">` +
      `<img src="${escapeText(absRaw)}" alt="" width="26" height="26" loading="lazy" referrerpolicy="strict-origin-when-cross-origin" />` +
      "</span>"
    );
  }
  const filename = check.icon_filename;
  if (filename && typeof filename === "string") {
    return (
      `<span class="health-row-icon health-row-icon--img health-row-icon--${statusCls}" aria-hidden="true">` +
      `<img src="${SELFHST_ICON_CDN}${escapeText(filename)}" alt="" width="26" height="26" loading="lazy" referrerpolicy="strict-origin-when-cross-origin" />` +
      "</span>"
    );
  }
  return serviceIconSvg(key, statusCls);
}

export function sickzRowIcon(check, statusCls) {
  return rowIcon(check, "sickz_url", statusCls);
}

export function shortHostForDetail(url) {
  let value = String(url).replace(/^https?:\/\//i, "");
  const slash = value.indexOf("/");
  if (slash !== -1) value = value.slice(0, slash);
  const suffix = ".albandrieu.com";
  if (value.toLowerCase().endsWith(suffix)) {
    return value.slice(0, -suffix.length) || value;
  }
  return value;
}

export function lockHtml(tlsTrusted, hrefRaw) {
  const href = (hrefRaw || "").trim().toLowerCase();
  const isHttps = href.indexOf("https:") === 0;
  let wrapCls;
  let label;
  if (!isHttps) {
    wrapCls = "sickz-lock--unknown";
    label = "TLS: not applicable (non-HTTPS or no link)";
  } else if (tlsTrusted === true) {
    wrapCls = "sickz-lock--trusted";
    label = "TLS: certificate validated";
  } else if (tlsTrusted === false) {
    wrapCls = "sickz-lock--untrusted";
    label = "TLS: certificate not trusted";
  } else {
    wrapCls = "sickz-lock--unknown";
    label = "TLS: not validated (target unreachable or check incomplete)";
  }
  const lockPaths =
    '<rect x="5" y="11" width="14" height="10" rx="2" ry="2"/>' +
    '<path d="M7 11V7a5 5 0 0 1 10 0v4"/>';
  return (
    `<span class="sickz-lock-wrap ${wrapCls}" role="img" aria-label="${escapeText(label)}">` +
    '<svg class="sickz-lock-svg" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">' +
    lockPaths +
    "</svg></span>"
  );
}

export function tunnelHref(check) {
  const url =
    (check.tunnel_url && String(check.tunnel_url).trim()) ||
    (check.tunnelUrl && String(check.tunnelUrl).trim()) ||
    (check.href && String(check.href).trim()) ||
    (check.url && String(check.url).trim()) ||
    "";
  return url.trim();
}

export function httpStatusIsSuccess2xx(code) {
  if (code == null) return true;
  const status = Number(code);
  if (Number.isNaN(status)) return true;
  return status >= 200 && status < 300;
}
