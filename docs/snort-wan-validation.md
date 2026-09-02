# Snort WAN validation — TrueNAS and pfSense TLS listeners

This runbook records the corrected WAN protocol classification validated on
2026-09-02 after the Snort `http_inspect` false-positive incident.

## Validated port variables

The generated WAN configuration now contains:

```text
portvar HTTP_PORTS [80]
portvar SSL_PORTS [443,7000,10443]
```

and the SSL preprocessor contains:

```text
preprocessor ssl: \
  ports { 443 7000 10443 }, \
  trustservers, \
  noinspect_encrypted
```

This is the intended classification for the currently reviewed listeners:

- `80/tcp`: clear-text HTTP;
- `443/tcp`: TLS;
- `7000/tcp`: TLS to the public TrueNAS HAProxy listener;
- `10443/tcp`: TLS to the pfSense administration/API listener.

Do not re-add `7000` or `10443` to `HTTP_PORTS` while those listeners carry
TLS. Historical GID `120` / SID `3` and `18` alerts remain in rotated logs and
must not be mistaken for post-change alerts.

## TrueNAS path represented in the operations UI

```text
FastAPI Cloud
  -> pfSense WAN 82.66.4.247:7000
  -> Snort / PF
  -> HAProxy :7000
     - HTTP mode
     - native WebSocket upgrade forwarding
     - TLS re-encryption to backend
  -> TrueNAS 172.17.0.24:7000
  -> WebSocket upgrade
  -> API authentication
  -> TrueNAS API
```

HAProxy HTTP mode can proxy a valid WebSocket upgrade natively. Do not add
manual `Connection: Upgrade` or `Upgrade: websocket` rewriting merely because
the application uses WebSockets unless a specific upgrade failure is proven.

## Safe Snort re-enable sequence

Do not jump directly from Snort stopped to full automatic blocking.

1. Start Snort WAN with `Block Offenders` temporarily disabled.
2. Exercise both the TrueNAS `:7000` path and the pfSense `:10443` API path from
  the FastAPI Cloud runtime.
3. Confirm the current egress address is absent from `snort2c`.
4. Confirm no **new** `120:3` or `120:18` alert appears after the restart.
5. If clean, enable `Block Offenders`, `Kill States`, `Which IP = BOTH`, keeping
  Legacy Mode on the current WAN interface.
6. Repeat the same `:7000`, `:10443`, `snort2c`, alert and packet-capture checks.

A current healthy capture must show bidirectional data and a normal TCP close,
not merely an initial SYN.

## Self-diagnostic limitation

When `PFSENSE_API_URL` reaches pfSense through public WAN `:10443`, the Snort
security observer shares the same filtering path it is trying to diagnose. If
Snort inserts the FastAPI Cloud egress into `snort2c`, PF can block both
`:7000` and `:10443`, preventing the observer from reading `snort2c`.

Configure this honestly as:

```text
PFSENSE_SECURITY_PATH_MODE=shared_wan
```

A transport failure then means **telemetry unavailable / self-diagnostic blind
spot**, not proof of a Snort block. An HTTP response such as `403` is different:
it proves pfSense is reachable and indicates an authorization/configuration
problem.

The target design is an independent, sanitized out-of-band observer that reads
pfSense over LAN and exports only required security evidence over an outbound
authenticated channel. Do not expose the raw pfSense management API simply to
make block attribution self-observing.
