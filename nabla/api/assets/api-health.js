(() => {
  const LABELS = {
    redis: "Redis",
    postgres: "PostgreSQL",
    supabase: "Supabase",
    openstack_me: "OVH / OpenStack API",
    tavily: "Tavily Search",
    brave: "Brave Search",
    google: "Google Programmable Search",
    appwrite: "Appwrite",
    keycloak: "Keycloak (OpenID)",
    unleash: "Unleash",
    sentry: "Sentry",
    logfire: "Pydantic Logfire",
    datadog: "Datadog Agent",
    pyroscope: "Pyroscope",
    litellm: "LiteLLM proxy",
    cloudflare: "Cloudflare Tunnels",
    pfsense: "pfSense API",
    albandrieu_twofactor: "twofactor-auth",
    albandrieu_nexus: "nexus",
    albandrieu_keycloak_ui: "keycloak",
    albandrieu_homarr: "homarr",
    albandrieu_plumber_api: "plumber-api",
    albandrieu_reactive_resume: "reactive-resume",
    albandrieu_vaultwarden: "vaultwarden-albandrieu",
  };

  const MANDATORY = new Set([
    "postgres",
    "redis",
    "supabase",
    "albandrieu_twofactor",
    "albandrieu_nexus",
    "albandrieu_keycloak_ui",
    "albandrieu_homarr",
    "albandrieu_plumber_api",
    "albandrieu_reactive_resume",
    "albandrieu_vaultwarden",
  ]);

  /* Filenames from https://selfh.st/icons/ (selfhst/icons repo, default SVG variant). */
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

  function healthBoardNormalizeIconSrc(raw) {
    const value = raw == null ? "" : String(raw).trim();
    if (!value) return "";
    if (value.toLowerCase().slice(0, 2) === "//") return `https:${value}`;
    return value;
  }

  function healthBoardIconSrcIsHttpUrl(value) {
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

  function sickzEscapeText(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function healthRowIcon(check, key, statusCls) {
    let rawPick = "";
    if (check.icon_src && typeof check.icon_src === "string") rawPick = check.icon_src;
    else if (check.iconSrc && typeof check.iconSrc === "string") rawPick = check.iconSrc;
    const absRaw = healthBoardNormalizeIconSrc(rawPick);
    if (healthBoardIconSrcIsHttpUrl(absRaw)) {
      return (
        `<span class="health-row-icon health-row-icon--img health-row-icon--${statusCls}" aria-hidden="true">` +
        `<img src="${sickzEscapeText(absRaw)}" alt="" width="26" height="26" loading="lazy" referrerpolicy="strict-origin-when-cross-origin" />` +
        "</span>"
      );
    }
    const filename = check.icon_filename;
    if (filename && typeof filename === "string") {
      return (
        `<span class="health-row-icon health-row-icon--img health-row-icon--${statusCls}" aria-hidden="true">` +
        `<img src="${SELFHST_ICON_CDN}${sickzEscapeText(filename)}" alt="" width="26" height="26" loading="lazy" referrerpolicy="strict-origin-when-cross-origin" />` +
        "</span>"
      );
    }
    return serviceIconSvg(key, statusCls);
  }

  function sickzShortHostForDetail(url) {
    let value = String(url).replace(/^https?:\/\//i, "");
    const slash = value.indexOf("/");
    if (slash !== -1) value = value.slice(0, slash);
    const suffix = ".albandrieu.com";
    if (value.toLowerCase().endsWith(suffix)) {
      return value.slice(0, -suffix.length) || value;
    }
    return value;
  }

  function sickzLockHtml(tlsTrusted, hrefRaw) {
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
    } else {
      wrapCls = "sickz-lock--untrusted";
      label =
        tlsTrusted === false
          ? "TLS: certificate not trusted"
          : "TLS: not validated (unreachable or check incomplete)";
    }
    const lockPaths =
      '<rect x="5" y="11" width="14" height="10" rx="2" ry="2"/>' +
      '<path d="M7 11V7a5 5 0 0 1 10 0v4"/>';
    return (
      `<span class="sickz-lock-wrap ${wrapCls}" role="img" aria-label="${sickzEscapeText(label)}">` +
      '<svg class="sickz-lock-svg" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">' +
      lockPaths +
      "</svg></span>"
    );
  }

  function sickzRowIcon(check, statusCls) {
    let rawPick = "";
    if (check.icon_src && typeof check.icon_src === "string") rawPick = check.icon_src;
    else if (check.iconSrc && typeof check.iconSrc === "string") rawPick = check.iconSrc;
    const absRaw = healthBoardNormalizeIconSrc(rawPick);
    if (healthBoardIconSrcIsHttpUrl(absRaw)) {
      return (
        `<span class="health-row-icon health-row-icon--img health-row-icon--${statusCls}" aria-hidden="true">` +
        `<img src="${sickzEscapeText(absRaw)}" alt="" width="26" height="26" loading="lazy" referrerpolicy="strict-origin-when-cross-origin" />` +
        "</span>"
      );
    }
    const filename = check.icon_filename;
    if (filename && typeof filename === "string") {
      return (
        `<span class="health-row-icon health-row-icon--img health-row-icon--${statusCls}" aria-hidden="true">` +
        `<img src="${SELFHST_ICON_CDN}${sickzEscapeText(filename)}" alt="" width="26" height="26" loading="lazy" referrerpolicy="strict-origin-when-cross-origin" />` +
        "</span>"
      );
    }
    return serviceIconSvg("sickz_url", statusCls);
  }

  function healthBoardTunnelHref(check) {
    const url =
      (check.tunnel_url && String(check.tunnel_url).trim()) ||
      (check.tunnelUrl && String(check.tunnelUrl).trim()) ||
      (check.href && String(check.href).trim()) ||
      "";
    return url.trim();
  }

  function healthRowTitleHtml(check, key) {
    let rowTitle = "";
    if (check.name != null && String(check.name).trim()) rowTitle = String(check.name).trim();
    else if (check.display_label != null) rowTitle = String(check.display_label);
    else if (LABELS[key]) rowTitle = LABELS[key];
    else rowTitle = key;
    const hrefRaw = healthBoardTunnelHref(check);
    const lock = sickzLockHtml(check.tls_trusted, hrefRaw);
    const inner =
      hrefRaw.length > 0
        ? `<a class="sickz-target-link" target="_blank" rel="noopener noreferrer" href="${sickzEscapeText(hrefRaw)}">${sickzEscapeText(rowTitle)}</a>`
        : `<span>${sickzEscapeText(rowTitle)}</span>`;
    return `<div class="health-row-name health-row-name--sickz">${lock}${inner}</div>`;
  }

  function httpStatusIsSuccess2xx(code) {
    if (code == null) return true;
    const status = Number(code);
    if (Number.isNaN(status)) return true;
    return status >= 200 && status < 300;
  }

  function healthHttpStatusIsSuccess2xx(check) {
    return httpStatusIsSuccess2xx(check.http_status);
  }

  function isExpectedSentryDebugFailure(key, check) {
    return (
      key === "sentry" &&
      check.reachable === true &&
      Number(check.http_status) === 500 &&
      (check.via === "/sentry-debug" || check.path === "/sentry-debug")
    );
  }

  function classify(key, check) {
    if (check.skipped === true) return "yellow";
    if (isExpectedSentryDebugFailure(key, check)) return "green";
    if (check.reachable === true) {
      if (!healthHttpStatusIsSuccess2xx(check)) return "blue";
      return "green";
    }
    if (check.reachable === false) return "red";
    return "gray";
  }

  function mandatoryFailed(key, check) {
    if (!MANDATORY.has(key)) return false;
    if (check.skipped === true) return false;
    return check.reachable === false;
  }

  function detailText(key, check) {
    if (check.skipped) return check.reason || "Not configured (intentionally disabled).";
    if (isExpectedSentryDebugFailure(key, check)) {
      return "HTTP 500 · Expected: the test error was intentionally triggered and captured by Sentry.";
    }
    if (check.reachable === true) {
      const parts = [];
      if (check.http_status != null) parts.push(`HTTP ${check.http_status}`);
      if (check.path) parts.push(check.path);
      if (check.host != null && check.port != null) parts.push(`${check.host}:${check.port}`);
      if (check.url) parts.push(String(check.url).replace(/^https?:\/\//i, ""));
      return parts.length ? parts.join(" · ") : "Connected.";
    }
    if (check.error) return check.error;
    return "Unreachable.";
  }

  function sortKeys(keys) {
    const first = [
      "postgres",
      "redis",
      "supabase",
      "albandrieu_twofactor",
      "albandrieu_nexus",
      "albandrieu_keycloak_ui",
      "albandrieu_homarr",
      "albandrieu_plumber_api",
      "albandrieu_reactive_resume",
      "albandrieu_vaultwarden",
      "albandrieu_truenas",
      "cloudflare",
      "pfsense",
      "litellm",
      "sentry",
      "logfire",
    ];
    const rest = keys.filter((key) => first.indexOf(key) === -1).sort();
    return first.filter((key) => keys.indexOf(key) !== -1).concat(rest);
  }

  function computeOverall(data) {
    const checks = data.checks || {};
    let anyYellow = false;
    let anyOptionalRed = false;
    let anyBlue = false;

    for (const key of Object.keys(checks)) {
      const check = checks[key];
      if (mandatoryFailed(key, check)) {
        return {
          cls: "red",
          text: "A required check failed: PostgreSQL, Redis, Supabase (when configured), and required albandrieu.com infra HTTPS endpoints must be reachable.",
        };
      }
      const classification = classify(key, check);
      if (classification === "yellow") anyYellow = true;
      if (classification === "red" && !MANDATORY.has(key)) anyOptionalRed = true;
      if (classification === "blue") anyBlue = true;
    }

    const status = data.status;
    if (status && status !== "healthy") {
      anyYellow = true;
      const critical =
        status === "health_fetch_failed" ||
        status === "health_endpoint_non_200" ||
        status === "health_invalid_json" ||
        status === "health_unexpected_shape";
      if (critical) {
        return {
          cls: "red",
          text: `Base /health check failed (${status}).${data.error ? ` ${data.error}` : ""}`,
        };
      }
    }

    if (anyOptionalRed) {
      return {
        cls: "yellow",
        text: "Core dependencies OK. One or more optional integrations are failing.",
      };
    }
    if (anyBlue) {
      return {
        cls: "blue",
        text: "A service responded over HTTP but returned a status outside 2xx (e.g. 400, 502, 530); see rows for codes.",
      };
    }
    if (anyYellow) {
      return {
        cls: "yellow",
        text: "Core dependencies OK. Yellow = env not set (disabled on purpose) or minor /health note.",
      };
    }
    return { cls: "green", text: "All probed services are reachable." };
  }

  function render(data) {
    const listEl = document.getElementById("health-checks");
    const summaryEl = document.getElementById("health-summary");
    const summaryText = document.getElementById("health-summary-text");
    const summaryLed = document.getElementById("health-summary-led");
    const errEl = document.getElementById("health-fetch-error");

    errEl.hidden = true;
    errEl.textContent = "";

    const overall = computeOverall(data);
    summaryEl.className = `health-summary health-summary--${overall.cls}`;
    summaryLed.className = `health-led health-led--${overall.cls}`;
    summaryText.textContent = overall.text;

    const checks = data.checks || {};
    const keys = sortKeys(Object.keys(checks));
    listEl.innerHTML = "";

    keys.forEach((key) => {
      const check = checks[key];
      const tier = MANDATORY.has(key)
        ? key.indexOf("albandrieu_") === 0
          ? "Required infra (albandrieu.com)"
          : "Required for core stack"
        : "Optional integration";
      const cls = classify(key, check);
      const item = document.createElement("li");
      item.className = "health-row";
      item.innerHTML =
        healthRowIcon(check, key, cls) +
        `<span class="health-row-led-wrap"><span class="health-led health-led--${cls}" title="${cls}"></span></span>` +
        '<div class="health-row-main">' +
        `<div class="health-row-primary health-row-primary--${cls}">` +
        healthRowTitleHtml(check, key) +
        `<div class="health-row-detail">${detailText(key, check)}</div></div>` +
        `<div class="health-row-tags">${tier}</div>` +
        "</div>";
      listEl.appendChild(item);
    });
  }

  function showFetchError(message) {
    const summaryEl = document.getElementById("health-summary");
    const summaryText = document.getElementById("health-summary-text");
    const summaryLed = document.getElementById("health-summary-led");
    const errEl = document.getElementById("health-fetch-error");
    document.getElementById("health-checks").innerHTML = "";
    summaryEl.className = "health-summary health-summary--red";
    summaryLed.className = "health-led health-led--red";
    summaryText.textContent = "Could not load /healthz.";
    errEl.hidden = false;
    errEl.textContent = message;
  }

  function sickzReachableHttpStatuses(check) {
    if (check.alias_results && check.aliases_probed) {
      const out = [];
      check.aliases_probed.forEach((url) => {
        const result = check.alias_results[url];
        if (result && result.reachable === true && result.http_status != null) {
          out.push(result.http_status);
        }
      });
      return out;
    }
    if (check.reachable === true && check.http_status != null) return [check.http_status];
    return [];
  }

  function sickzIsForbiddenOnlyReachable(check) {
    if (check.skipped === true || check.reachable !== true) return false;
    const statuses = sickzReachableHttpStatuses(check);
    if (statuses.length === 0) return false;
    return statuses.every((status) => status === 403);
  }

  function sickzHasReachableNon2xxHttp(check) {
    if (check.skipped === true || check.reachable !== true) return false;
    if (sickzIsForbiddenOnlyReachable(check)) return false;
    const statuses = sickzReachableHttpStatuses(check);
    if (statuses.length === 0) return false;
    return statuses.some((status) => !httpStatusIsSuccess2xx(status));
  }

  function classifySick(check) {
    if (check.skipped === true) return "yellow";
    if (check.reachable === true) {
      if (sickzIsForbiddenOnlyReachable(check)) return "yellow";
      if (sickzHasReachableNon2xxHttp(check)) return "blue";
      return "red";
    }
    if (check.reachable === false) return "green";
    return "gray";
  }

  function detailSickText(check) {
    if (check.skipped === true) {
      const intro = check.reason || "Not probed (LAN skip).";
      if (check.aliases_probed && check.aliases_probed.length) {
        return `${intro} Targets: ${check.aliases_probed.map(sickzShortHostForDetail).join(" · ")}`;
      }
      return intro;
    }
    if (check.alias_results && check.aliases_probed) {
      const bits = [];
      check.aliases_probed.forEach((url) => {
        const result = check.alias_results[url];
        const tail = sickzShortHostForDetail(url);
        if (!result) return;
        if (result.reachable === true) {
          bits.push(
            `${tail} → reachable${result.http_status != null ? ` (HTTP ${result.http_status})` : ""}`,
          );
        } else if (result.error) {
          bits.push(`${tail} → unreachable (${result.error})`);
        } else {
          bits.push(`${tail} → unreachable`);
        }
      });
      const line = bits.join(" · ");
      if (sickzIsForbiddenOnlyReachable(check)) {
        return `${line} — HTTP 403 only: host responded but access is forbidden (yellow, not full exposure).`;
      }
      return line;
    }
    if (check.reachable === true) {
      const parts = ["Reachable (should be blocked)."];
      if (check.http_status != null) parts.push(`HTTP ${check.http_status}`);
      if (sickzIsForbiddenOnlyReachable(check)) {
        parts.push("HTTP 403: host reached but forbidden — shown as yellow.");
      }
      return parts.join(" ");
    }
    if (check.reachable === false) {
      if (check.error) return `Unreachable as expected. ${check.error}`;
      return "Unreachable as expected.";
    }
    return "Unknown state.";
  }

  function sickzNetworkPhrase(data) {
    return data.network_label ? `"${data.network_label}"` : "this deployment";
  }

  function computeSickOverall(data) {
    const network = sickzNetworkPhrase(data);
    if (data.status === "skipped_internal_network") {
      return {
        cls: "yellow",
        text: `${data.detail || "Sickz skipped on internal network."} Network: ${network}.`,
      };
    }
    if (data.status === "no_targets" || Object.keys(data.checks || {}).length === 0) {
      return {
        cls: "yellow",
        text: `${data.detail || "No sickz targets configured."} Network: ${network}.`,
      };
    }
    const checks = data.checks || {};
    let anyOpenReach2xx = false;
    let anyOpenReachNon2xx = false;
    let anyForbiddenOnly = false;
    for (const key of Object.keys(checks)) {
      const check = checks[key];
      if (check.skipped === true) continue;
      if (check.reachable === true) {
        if (sickzIsForbiddenOnlyReachable(check)) anyForbiddenOnly = true;
        else if (sickzHasReachableNon2xxHttp(check)) anyOpenReachNon2xx = true;
        else anyOpenReach2xx = true;
      }
    }
    if (anyOpenReach2xx) {
      return {
        cls: "red",
        text: `From network ${network}, at least one target is reachable with HTTP 2xx; it should stay blocked from this context.`,
      };
    }
    if (anyOpenReachNon2xx) {
      return {
        cls: "blue",
        text: `From network ${network}, at least one target responded but with a non-2xx HTTP status (e.g. 400, 502); see rows.`,
      };
    }
    if (anyForbiddenOnly) {
      return {
        cls: "yellow",
        text: `From network ${network}, at least one target responded with HTTP 403 (Forbidden) only — the host is reachable but access is denied.`,
      };
    }
    return {
      cls: "green",
      text: `From network ${network}, all listed targets are unreachable (expected).`,
    };
  }

  function sickzFindPfsenseEntry(checks) {
    const keys = Object.keys(checks || {});
    for (const key of keys) {
      const check = checks[key];
      if (!check) continue;
      if (check.display_label === "PfSense" || check.name === "PfSense") {
        return { key, check };
      }
      if (check.pfsense_tcp_ports && typeof check.pfsense_tcp_ports === "object") {
        return { key, check };
      }
    }
    return null;
  }

  function sickzPfsenseTcpPortNumbers(map) {
    if (!map || typeof map !== "object") return [];
    return Object.keys(map)
      .map((value) => Number.parseInt(value, 10))
      .filter((value) => !Number.isNaN(value))
      .sort((left, right) => left - right);
  }

  function sickzPfsensePortChipClass(reachable) {
    if (reachable === true) return "sickz-pfsense-port--open";
    if (reachable === false) return "sickz-pfsense-port--closed";
    return "sickz-pfsense-port--na";
  }

  function sickzPfsensePortLabel(reachable) {
    if (reachable === true) return "reachable";
    if (reachable === false) return "unreachable";
    return "not probed";
  }

  function sickzBuildPfsenseSectionHtml(_pfKey, pfCheck) {
    const cls = classifySick(pfCheck);
    const hrefRaw = healthBoardTunnelHref(pfCheck);
    const safeHref = hrefRaw.length ? sickzEscapeText(hrefRaw) : "";
    const lockTls = pfCheck.skipped === true ? null : pfCheck.tls_trusted;
    const lockHref = pfCheck.skipped === true ? "" : hrefRaw;
    const portsMap = pfCheck.pfsense_tcp_ports;
    const nums = sickzPfsenseTcpPortNumbers(portsMap);
    let chips = "";
    nums.forEach((port) => {
      const reachable = portsMap[String(port)];
      const portClass = sickzPfsensePortChipClass(reachable);
      const portLabel = sickzPfsensePortLabel(reachable);
      chips +=
        `<span class="sickz-pfsense-port ${portClass}" title="TCP ${port}: ${portLabel}">` +
        `<span class="sickz-pfsense-port-num">${port}</span>` +
        `<span class="sickz-pfsense-port-st">${sickzEscapeText(portLabel)}</span></span>`;
    });
    let meta =
      "HTTPS aliases use the same sickz rules as other targets. PfSense additionally runs TCP connect checks on " +
      '<code class="sickz-pfsense-host">home.albandrieu.com</code> for the ports below.';
    if (pfCheck.pfsense_tcp_ports_skipped === true) {
      meta += " TCP probes were not run (LAN skip).";
    }
    const rowName =
      pfCheck.name != null && String(pfCheck.name).trim()
        ? String(pfCheck.name).trim()
        : String(pfCheck.display_label || "PfSense");
    const titleLink =
      safeHref.length > 0
        ? `<a class="sickz-target-link" target="_blank" rel="noopener noreferrer" href="${safeHref}">${sickzEscapeText(rowName)}</a>`
        : `<span>${sickzEscapeText(rowName)}</span>`;
    return (
      '<h4 class="sickz-pfsense-title">PfSense</h4>' +
      `<p class="health-board-meta sickz-pfsense-intro">${meta}</p>` +
      '<ul class="health-checks sickz-pfsense-main"><li class="health-row sickz-pfsense-row">' +
      sickzRowIcon(pfCheck, cls) +
      `<span class="health-row-led-wrap"><span class="health-led health-led--${cls}" title="${cls}"></span></span>` +
      '<div class="health-row-main">' +
      `<div class="health-row-primary health-row-primary--${cls}">` +
      '<div class="health-row-name health-row-name--sickz">' +
      sickzLockHtml(lockTls, lockHref) +
      titleLink +
      "</div>" +
      `<div class="health-row-detail">${sickzEscapeText(detailSickText(pfCheck))}</div></div>` +
      '<div class="health-row-tags">PfSense · HTTPS UI + extra TCP ports</div>' +
      "</div></li></ul>" +
      '<div class="sickz-pfsense-ports-label">TCP ports (home.albandrieu.com)</div>' +
      `<div class="sickz-pfsense-ports">${chips}</div>`
    );
  }

  function renderSickz(data) {
    const listEl = document.getElementById("sickz-checks");
    const summaryEl = document.getElementById("sickz-summary");
    const summaryText = document.getElementById("sickz-summary-text");
    const summaryLed = document.getElementById("sickz-summary-led");
    const errEl = document.getElementById("sickz-fetch-error");

    errEl.hidden = true;
    errEl.textContent = "";

    const overall = computeSickOverall(data);
    summaryEl.className = `health-summary health-summary--${overall.cls}`;
    summaryLed.className = `health-led health-led--${overall.cls}`;
    summaryText.textContent = overall.text;

    const hintEl = document.getElementById("sickz-lan-hint");
    const runtime = data.runtime || {};
    if (hintEl) {
      if (data.status === "skipped_internal_network") {
        hintEl.hidden = false;
        if (runtime.sickz_internal_network_implicit) {
          hintEl.textContent = `LAN skip was inferred from ${runtime.internal_network_inferred_from || "SICKZ_NETWORK_LABEL / APP_DOMAIN rules"} (SICKZ_INTERNAL_NETWORK was not required).`;
        } else {
          hintEl.textContent = "LAN skip from SICKZ_INTERNAL_NETWORK=true.";
        }
      } else if (
        runtime.cloud_paas_detected &&
        (runtime.sickz_internal_network_config || runtime.sickz_internal_network_implicit)
      ) {
        hintEl.hidden = false;
        hintEl.textContent =
          "Cloud/PaaS runtime: sickz probes still run even though this host would match home-LAN rules (env or implicit label/domain).";
      } else {
        hintEl.hidden = true;
        hintEl.textContent = "";
      }
    }

    const checks = data.checks || {};
    const pfEntry = sickzFindPfsenseEntry(checks);
    const pfKey = pfEntry ? pfEntry.key : null;
    const wrapPf = document.getElementById("sickz-pfsense-wrap");
    if (wrapPf) {
      if (!pfEntry) {
        wrapPf.hidden = true;
        wrapPf.innerHTML = "";
      } else {
        wrapPf.hidden = false;
        wrapPf.innerHTML = sickzBuildPfsenseSectionHtml(pfEntry.key, pfEntry.check);
      }
    }

    const keys = Object.keys(checks)
      .filter((key) => key !== pfKey)
      .sort();
    listEl.innerHTML = "";

    keys.forEach((key) => {
      const check = checks[key];
      const cls = classifySick(check);
      const item = document.createElement("li");
      item.className = "health-row";
      const hrefRaw = healthBoardTunnelHref(check);
      const safeHref = hrefRaw.length ? sickzEscapeText(hrefRaw) : "";
      let rowTitle = "";
      if (check.name != null && String(check.name).trim()) rowTitle = String(check.name).trim();
      else if (check.display_label != null) rowTitle = String(check.display_label);
      else rowTitle = key;
      const lockTls = check.skipped === true ? null : check.tls_trusted;
      const lockHref = check.skipped === true ? "" : hrefRaw;
      const titleInner =
        safeHref.length > 0
          ? `<a class="sickz-target-link" target="_blank" rel="noopener noreferrer" href="${safeHref}">${sickzEscapeText(rowTitle)}</a>`
          : `<span>${sickzEscapeText(rowTitle)}</span>`;
      item.innerHTML =
        sickzRowIcon(check, cls) +
        `<span class="health-row-led-wrap"><span class="health-led health-led--${cls}" title="${cls}"></span></span>` +
        '<div class="health-row-main">' +
        `<div class="health-row-primary health-row-primary--${cls}">` +
        '<div class="health-row-name health-row-name--sickz">' +
        sickzLockHtml(lockTls, lockHref) +
        titleInner +
        "</div>" +
        `<div class="health-row-detail">${detailSickText(check)}</div></div>` +
        `<div class="health-row-tags">${
          check.skipped
            ? "Listed for reference; not probed on this network"
            : check.alias_results
              ? "Equivalent URLs (any alias reachable fails the check)"
              : "Must not be reachable"
        }</div>` +
        "</div>";
      listEl.appendChild(item);
    });
  }

  function showSickzFetchError(message) {
    const summaryEl = document.getElementById("sickz-summary");
    const summaryText = document.getElementById("sickz-summary-text");
    const summaryLed = document.getElementById("sickz-summary-led");
    const errEl = document.getElementById("sickz-fetch-error");
    const wrapPf = document.getElementById("sickz-pfsense-wrap");
    if (wrapPf) {
      wrapPf.hidden = true;
      wrapPf.innerHTML = "";
    }
    document.getElementById("sickz-checks").innerHTML = "";
    summaryEl.className = "health-summary health-summary--red";
    summaryLed.className = "health-led health-led--red";
    summaryText.textContent = "Could not load /sickz.";
    errEl.hidden = false;
    errEl.textContent = message;
  }

  function loadHealth() {
    fetch("/healthz", { headers: { Accept: "application/json" } })
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
      })
      .then(render)
      .catch((error) => {
        showFetchError(String(error.message || error));
      });
  }

  function loadSickz() {
    fetch("/sickz", { headers: { Accept: "application/json" } })
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
      })
      .then(renderSickz)
      .catch((error) => {
        showSickzFetchError(String(error.message || error));
      });
  }

  function loadHealthBoards() {
    loadHealth();
    loadSickz();
  }

  document.querySelectorAll(".health-refresh").forEach((button) => {
    button.addEventListener("click", loadHealthBoards);
  });
  loadHealthBoards();
})();
