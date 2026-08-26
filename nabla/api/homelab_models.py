"""Typed, fail-closed contract for the homelab service catalog."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from ipaddress import ip_address
import re
from urllib.parse import urlsplit

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

_SERVICE_ID_RE = re.compile(r"[^a-z0-9]+")
_HOMELAB_DOMAIN_SUFFIX = ".albandrieu.com"
_DIRECT_EXTERNAL_DOMAIN_SUFFIX = ".int.albandrieu.com"


def _slugify_service_id(value: str) -> str:
    """Return a stable lowercase service identifier suitable for JSON keys."""
    slug = _SERVICE_ID_RE.sub("-", value.strip().lower()).strip("-")
    return slug or "service"


def _derive_service_id(name: str, tunnel_url: str | None) -> str:
    """Prefer the albandrieu.com hostname label, otherwise derive from the name."""
    if tunnel_url:
        try:
            host = (urlsplit(tunnel_url).hostname or "").lower().rstrip(".")
        except ValueError:
            host = ""
        if host.endswith(_HOMELAB_DOMAIN_SUFFIX):
            prefix = host[: -len(_HOMELAB_DOMAIN_SUFFIX)].strip(".")
            if prefix:
                return _slugify_service_id(prefix.replace(".", "-"))
    return _slugify_service_id(name)


class HomelabDiscoverySource(StrEnum):
    """Origin of inventory data, not an authorization source for exposure."""

    MANUAL = "manual"
    TRUENAS = "truenas"


class HomelabService(BaseModel):
    """One homelab service with explicit, opt-in external exposure.

    TrueNAS discovery is inventory only. It may populate internal service facts,
    but it must never infer ``external=True`` from ports, portals, DNS names, or
    the presence of an endpoint URL.
    """

    model_config = ConfigDict(
        extra="ignore",
        frozen=True,
        populate_by_name=True,
        str_strip_whitespace=True,
    )

    service_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
        validation_alias=AliasChoices("id", "serviceId", "service_id"),
        serialization_alias="id",
    )
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    icons: list[str] = Field(default_factory=list)
    icon_src: str | None = Field(
        default=None,
        validation_alias=AliasChoices("iconSrc", "icon_src"),
        serialization_alias="iconSrc",
    )

    internal_host: str | None = Field(
        default=None,
        validation_alias=AliasChoices("internalHost", "internal_host"),
        serialization_alias="internalHost",
    )
    internal_port: int | None = Field(
        default=None,
        ge=1,
        le=65535,
        validation_alias=AliasChoices("internalPort", "internal_port"),
        serialization_alias="internalPort",
    )
    internal_secure: bool = Field(
        default=False,
        validation_alias=AliasChoices("internalSecure", "internal_secure"),
        serialization_alias="internalSecure",
    )
    internal_path: str | None = Field(
        default=None,
        validation_alias=AliasChoices("internalPath", "internal_path"),
        serialization_alias="internalPath",
    )
    internal_title: str | None = Field(
        default=None,
        validation_alias=AliasChoices("internalTitle", "internal_title"),
        serialization_alias="internalTitle",
    )

    # ``tunnelUrl`` remains the wire-format name during the migration because
    # nabla-site-alban already consumes it for Cloudflare and non-Cloudflare endpoints.
    tunnel_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("tunnelUrl", "tunnel_url"),
        serialization_alias="tunnelUrl",
    )
    tunnel_secure: bool | None = Field(
        default=None,
        validation_alias=AliasChoices("tunnelSecure", "tunnel_secure"),
        serialization_alias="tunnelSecure",
    )
    tunnel_title: str | None = Field(
        default=None,
        validation_alias=AliasChoices("tunnelTitle", "tunnel_title"),
        serialization_alias="tunnelTitle",
    )
    endpoint_enabled: bool | None = Field(
        default=None,
        validation_alias=AliasChoices("endpointEnabled", "endpoint_enabled"),
        serialization_alias="endpointEnabled",
    )

    # Secure default: discovery and incomplete JSON are private unless exposure
    # intent is explicitly present. The misspelled legacy field is accepted only
    # as a transitional input alias and is never emitted again.
    external: bool = Field(
        default=False,
        validation_alias=AliasChoices("external", "reacheableFromOutside"),
        serialization_alias="external",
    )

    source: HomelabDiscoverySource = HomelabDiscoverySource.MANUAL
    source_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("sourceId", "source_id"),
        serialization_alias="sourceId",
    )
    port_html: str | None = Field(
        default=None,
        validation_alias=AliasChoices("portHtml", "port_html"),
        serialization_alias="portHtml",
    )

    @model_validator(mode="before")
    @classmethod
    def populate_service_id(cls, data: object) -> object:
        """Backfill a stable ID for legacy catalog entries that predate the field."""
        if not isinstance(data, dict):
            return data
        if any(data.get(key) for key in ("id", "serviceId", "service_id")):
            return data
        name = str(data.get("name") or "service")
        tunnel_url = data.get("tunnelUrl") or data.get("tunnel_url")
        payload = dict(data)
        payload["id"] = _derive_service_id(name, str(tunnel_url) if tunnel_url else None)
        return payload

    @model_validator(mode="before")
    @classmethod
    def reject_conflicting_exposure_aliases(cls, data: object) -> object:
        """Fail closed when old and new exposure flags disagree."""
        if not isinstance(data, dict):
            return data
        if "external" not in data or "reacheableFromOutside" not in data:
            return data
        if bool(data["external"]) != bool(data["reacheableFromOutside"]):
            raise ValueError("external conflicts with legacy reacheableFromOutside")
        return data

    @model_validator(mode="after")
    def validate_external_exposure(self) -> HomelabService:
        """Require an explicit, plausibly public endpoint for external access.

        ``*.int.albandrieu.com`` is an intentional legacy/direct-ingress exception:
        it may be externally reachable through Traefik rather than Cloudflare, but
        only when ``tunnelSecure=false`` makes that weaker security posture explicit.
        Sickz then reports the exception as a warning instead of treating it as secure.
        """
        if not self.external:
            return self
        if not self.tunnel_url:
            raise ValueError("external=true requires tunnelUrl")

        try:
            parsed = urlsplit(self.tunnel_url)
        except ValueError as exc:
            raise ValueError("external tunnelUrl is invalid") from exc

        if not parsed.scheme or not parsed.hostname:
            raise ValueError("external tunnelUrl must contain a scheme and host")
        if parsed.username or parsed.password:
            raise ValueError("external tunnelUrl must not contain credentials")

        scheme = parsed.scheme.lower()
        host = parsed.hostname.lower().rstrip(".")
        if scheme == "http":
            raise ValueError("external HTTP endpoints must use HTTPS")
        if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
            raise ValueError("external tunnelUrl must not target a local hostname")
        if host.endswith(_DIRECT_EXTERNAL_DOMAIN_SUFFIX) and self.tunnel_secure is not False:
            raise ValueError(
                "external *.int.albandrieu.com endpoints require tunnelSecure=false "
                "to declare the direct non-Cloudflare exposure exception"
            )

        try:
            address = ip_address(host)
        except ValueError:
            address = None
        if address is not None and not address.is_global:
            raise ValueError("external tunnelUrl must not target a non-global IP address")
        return self

    @classmethod
    def from_truenas_discovery(
        cls,
        *,
        name: str,
        source_id: str,
        description: str | None = None,
        internal_host: str | None = None,
        internal_port: int | None = None,
        internal_secure: bool = False,
        icon_src: str | None = None,
    ) -> HomelabService:
        """Create a private inventory entry from future TrueNAS ``app.query`` data.

        The method deliberately has no public endpoint/exposure arguments. A
        separate, reviewed configuration overlay must opt the service into
        external access after discovery.
        """
        return cls(
            service_id=_slugify_service_id(source_id),
            name=name,
            description=description,
            internal_host=internal_host,
            internal_port=internal_port,
            internal_secure=internal_secure,
            icon_src=icon_src,
            source=HomelabDiscoverySource.TRUENAS,
            source_id=source_id,
            external=False,
            endpoint_enabled=False,
        )

    def with_external_access(self, url: str) -> HomelabService:
        """Return a validated copy with explicitly approved external access."""
        payload = self.model_dump()
        payload.update(
            {
                "tunnel_url": url,
                "external": True,
                "endpoint_enabled": True,
            }
        )
        return type(self).model_validate(payload)

    @property
    def public_https_probe_url(self) -> str | None:
        """Return an HTTPS URL only when public exposure is explicitly enabled."""
        if not self.external or self.endpoint_enabled is False or not self.tunnel_url:
            return None
        if not self.tunnel_url.lower().startswith("https://"):
            return None
        return self.tunnel_url.rstrip("/") + "/"


class HomelabCatalog(BaseModel):
    """Versioned service inventory suitable for JSON/schema generation."""

    model_config = ConfigDict(
        extra="ignore",
        frozen=True,
        populate_by_name=True,
    )

    version: int = Field(default=2, ge=1)
    services: list[HomelabService] = Field(default_factory=list)
    generated_at: datetime | None = Field(
        default=None,
        validation_alias=AliasChoices("generatedAt", "generated_at"),
        serialization_alias="generatedAt",
    )

    @model_validator(mode="after")
    def require_unique_service_identity(self) -> HomelabCatalog:
        """Reject ambiguous duplicate service names or stable IDs."""
        names: set[str] = set()
        service_ids: set[str] = set()
        for service in self.services:
            normalized = service.name.casefold()
            if normalized in names:
                raise ValueError(f"duplicate homelab service name: {service.name}")
            if service.service_id in service_ids:
                raise ValueError(f"duplicate homelab service id: {service.service_id}")
            names.add(normalized)
            service_ids.add(service.service_id)
        return self

    @property
    def public_services(self) -> list[HomelabService]:
        """Services explicitly intended to be exposed outside the homelab."""
        return [service for service in self.services if service.external]
