# [1.5.0](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.4.1...1.5.0) (2026-08-23)


### Bug Fixes

* pin Python 3.13 for FastAPI Cloud ([#46](https://github.com/AlbanAndrieu/fastapi-sample/issues/46)) ([2a0d89a](https://github.com/AlbanAndrieu/fastapi-sample/commit/2a0d89a18e252bdc44c5f9229d0d3f8dcbad55a9))


### Features

* add homelab service contract skill ([#49](https://github.com/AlbanAndrieu/fastapi-sample/issues/49)) ([eaf081d](https://github.com/AlbanAndrieu/fastapi-sample/commit/eaf081dc343ad0be3625a2aa84a1beab00705914))
* add public homelab health API ([#51](https://github.com/AlbanAndrieu/fastapi-sample/issues/51)) ([de68681](https://github.com/AlbanAndrieu/fastapi-sample/commit/de68681921184f0574f0655c154202d4c9ad0cff))
* add secure typed homelab catalog ([#50](https://github.com/AlbanAndrieu/fastapi-sample/issues/50)) ([050debb](https://github.com/AlbanAndrieu/fastapi-sample/commit/050debbf51e67920725b7f3cf890c406dca60eeb))
* add TrueNAS dependency health signal ([#53](https://github.com/AlbanAndrieu/fastapi-sample/issues/53)) ([f246b59](https://github.com/AlbanAndrieu/fastapi-sample/commit/f246b59e0f5a306a7a18a37c22114a91b4ee629d))
* consolidate runtime, platform and observability health ([#54](https://github.com/AlbanAndrieu/fastapi-sample/issues/54)) ([2e5a939](https://github.com/AlbanAndrieu/fastapi-sample/commit/2e5a939a48142f51b13efd9695793d8a84d763d1))
* prepare read-only Cloudflare tunnel observer ([#52](https://github.com/AlbanAndrieu/fastapi-sample/issues/52)) ([ab4ddc3](https://github.com/AlbanAndrieu/fastapi-sample/commit/ab4ddc325d292393209335ff74fea4d208abe2d6))

## [1.4.1](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.4.0...1.4.1) (2026-08-21)


### Bug Fixes

* **release:** harden version sync and refactor config settings ([#45](https://github.com/AlbanAndrieu/fastapi-sample/issues/45)) ([d32bd74](https://github.com/AlbanAndrieu/fastapi-sample/commit/d32bd749242b27007be32dc60e238e788e7c1a4d))

# [1.4.0](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.3.8...1.4.0) (2026-08-21)


### Bug Fixes

* **ci:** ignore transient MegaLinter GitHub config in Checkov ([#32](https://github.com/AlbanAndrieu/fastapi-sample/issues/32)) ([254724f](https://github.com/AlbanAndrieu/fastapi-sample/commit/254724fba083751e98f5f58ef64ec78e9b58f4a5))
* **logfire:** simplify FastAPI Cloud integration ([#43](https://github.com/AlbanAndrieu/fastapi-sample/issues/43)) ([26b8c60](https://github.com/AlbanAndrieu/fastapi-sample/commit/26b8c60185ca71a8d1c72169b626af036a69742a))
* **mcp:** expose canonical streamable HTTP endpoint ([#35](https://github.com/AlbanAndrieu/fastapi-sample/issues/35)) ([93ec084](https://github.com/AlbanAndrieu/fastapi-sample/commit/93ec084b4a5283fcfbedcebb7b1dd16d835ed898))
* **observability:** enable Logfire on FastAPI Cloud ([#39](https://github.com/AlbanAndrieu/fastapi-sample/issues/39)) ([0c66b29](https://github.com/AlbanAndrieu/fastapi-sample/commit/0c66b298908070328c6bf57cd7f8a002d7d931cc))
* **runtime:** make Datadog optional on FastAPI Cloud ([#38](https://github.com/AlbanAndrieu/fastapi-sample/issues/38)) ([b8c08b2](https://github.com/AlbanAndrieu/fastapi-sample/commit/b8c08b2af87cb9025d39237491e707962c234c3e))
* **runtime:** stabilize FastAPI Cloud and start config refactor ([#40](https://github.com/AlbanAndrieu/fastapi-sample/issues/40)) ([2c489df](https://github.com/AlbanAndrieu/fastapi-sample/commit/2c489df62ff762d0cc9daf4e3b25b2b819e6cc0e))


### Features

* **mcp:** add persistent Streamable HTTP outbound clients ([#37](https://github.com/AlbanAndrieu/fastapi-sample/issues/37)) ([2ddbd33](https://github.com/AlbanAndrieu/fastapi-sample/commit/2ddbd337c6631bfdba8e44fbd614b3f20b5b4abc))
* **mcp:** improve OpenWebUI MCP discovery guidance ([#31](https://github.com/AlbanAndrieu/fastapi-sample/issues/31)) ([a529a93](https://github.com/AlbanAndrieu/fastapi-sample/commit/a529a930ef7858a01cb6e260f4c0cc47f67a833f))
* **release:** migrate semantic-release to GitHub ([#42](https://github.com/AlbanAndrieu/fastapi-sample/issues/42)) ([2385b1c](https://github.com/AlbanAndrieu/fastapi-sample/commit/2385b1caac771f9d710fa84c7c125fd6bf321923))

# 1.0.0 (2026-07-10)


### Bug Fixes

* Add Ollama Client to test MCP Server ([fbd53bb](https://gitlab.com/AlbanAndrieu/fastapi-sample/commit/fbd53bb0f27ba8dd5363f74303d0ba6e2c3f2e7b))
* disable vercel deploy in gitlab ([dffb7a6](https://gitlab.com/AlbanAndrieu/fastapi-sample/commit/dffb7a6c0523be733c3ee1566abae0c8ccc02398))
* use smaller model : llama3.1:70b ([9c9045f](https://gitlab.com/AlbanAndrieu/fastapi-sample/commit/9c9045f1dd9b17e03d09ab6adf4ea4110d7f7765))
* Use uv in tox and fix ruff format ([ba5f6ec](https://gitlab.com/AlbanAndrieu/fastapi-sample/commit/ba5f6ec423f3e0cb5fcedecb53a1bf98f5cb69e9))

## [1.3.7](https://gitlab.com/AlbanAndrieu/fastapi-sample/compare/1.3.6...1.3.7) (2026-04-02)


### Bug Fixes

* Save poetry before switching to uv ([5a8caf1](https://gitlab.com/AlbanAndrieu/fastapi-sample/commit/5a8caf11fcc3550f6b153f0d8525fcbda762d6a5))

## [1.3.6](https://gitlab.com/AlbanAndrieu/fastapi-sample/compare/1.3.5...1.3.6) (2026-04-01)


### Bug Fixes

* Save peotry before switching to uv ([caea92a](https://gitlab.com/AlbanAndrieu/fastapi-sample/commit/caea92ade28aa516b42e729dd909a0cdff379b22))

## [1.3.5](https://gitlab.com/AlbanAndrieu/fastapi-sample/compare/1.3.4...1.3.5) (2026-03-18)


### Bug Fixes

* urls ([86a7a6f](https://gitlab.com/AlbanAndrieu/fastapi-sample/commit/86a7a6fe41fceb2d8db1e28e5950bf9a634da3c1))

## [1.3.4](https://gitlab.com/AlbanAndrieu/fastapi-sample/compare/1.3.3...1.3.4) (2026-03-04)


### Bug Fixes

* update ([2d8eef1](https://gitlab.com/AlbanAndrieu/fastapi-sample/commit/2d8eef10588b7f341cee3b1607270ed551c6a0c2))
* update ([4000fe4](https://gitlab.com/AlbanAndrieu/fastapi-sample/commit/4000fe45960e6795ad1311cb24fd6c94b1084a0b))
* update ([d4cb5bc](https://gitlab.com/AlbanAndrieu/fastapi-sample/commit/d4cb5bcda969583daa1594a1f8550919c05928ea))
* update ([453e245](https://gitlab.com/AlbanAndrieu/fastapi-sample/commit/453e24532255af378db1aed6e7e6044989acf5ca))
* update ([33cf313](https://gitlab.com/AlbanAndrieu/fastapi-sample/commit/33cf313ce68548ac06d06b4f2fed22404bde4b16))
* update ([4fcc110](https://gitlab.com/AlbanAndrieu/fastapi-sample/commit/4fcc110ec47dc3f58ea1c99d9b1d1c0fa2c4eada))
* update ([c61b450](https://gitlab.com/AlbanAndrieu/fastapi-sample/commit/c61b45016a7209e65d791d7ec62a0828a1df7a0a))
* update ([b58e191](https://gitlab.com/AlbanAndrieu/fastapi-sample/commit/b58e191551197cb48d426d541f8746cedae598bc))

## [1.3.3](https://gitlab.com/AlbanAndrieu/fastapi-sample/compare/1.3.2...1.3.3) (2026-02-18)

### Bug Fixes

* Format with prettier ([8566a68](https://gitlab.com/AlbanAndrieu/fastapi-sample/commit/8566a68f660e3d7d6ca11c0bd8fdf61053161385))

## [1.3.2](https://gitlab.com/AlbanAndrieu/fastapi-sample/compare/1.3.1...1.3.2) (2026-02-06)


### Bug Fixes

* python 3.12 ([1e89ca4](https://gitlab.com/AlbanAndrieu/fastapi-sample/commit/1e89ca43f0c019baab7628d8f548fe18cf41c0f7))

## [1.3.1](https://gitlab.com/AlbanAndrieu/fastapi-sample/compare/1.3.0...1.3.1) (2026-01-26)


### Bug Fixes

* deploy ([a94ec94](https://gitlab.com/AlbanAndrieu/fastapi-sample/commit/a94ec9415502544bed960d9abffcb05034c16f6d))
* deploy ([160b825](https://gitlab.com/AlbanAndrieu/fastapi-sample/commit/160b825cb4688a86d2d93f156e78767eb14affeb))
* deploy ([b4d76b3](https://gitlab.com/AlbanAndrieu/fastapi-sample/commit/b4d76b3821ad3ad5bf536a6cf78195f1175d4152))
* prettier --write ([fbe7148](https://gitlab.com/AlbanAndrieu/fastapi-sample/commit/fbe71487aed4fb82452462b0116fc9529eaab83f))

# [1.3.0](https://gitlab.com/AlbanAndrieu/fastapi-sample/compare/1.2.4...1.3.0) (2026-01-17)

### Bug Fixes

- Helm lint ([c079c07](https://gitlab.com/AlbanAndrieu/fastapi-sample/commit/c079c0759d01f358b0f6c67ffca1fae3337b5ba0))
- Helm lint ([10c6fe2](https://gitlab.com/AlbanAndrieu/fastapi-sample/commit/10c6fe24b2b8d495ff9a7fc10903a4623ff578af))
- pre-commit run ([a9021ad](https://gitlab.com/AlbanAndrieu/fastapi-sample/commit/a9021ade8d81802350bb057014f2ec523390f382))
- pre-commit run ([e66f513](https://gitlab.com/AlbanAndrieu/fastapi-sample/commit/e66f5134d534590aed2856af2c600e424e0fb1e0))
- prepare for uv ([f50d947](https://gitlab.com/AlbanAndrieu/fastapi-sample/commit/f50d9470c94857f6078409ab8612c5367cbe3d58))
- Rename .python-version-direnv for vercel ([2233092](https://gitlab.com/AlbanAndrieu/fastapi-sample/commit/2233092acec34947023ff9ef7c25ef95ffac1bda))
- test new ci ([14ce3fe](https://gitlab.com/AlbanAndrieu/fastapi-sample/commit/14ce3fee155649a4dd6d238c65d583af0553c5b9))
- test new CI ([db0b382](https://gitlab.com/AlbanAndrieu/fastapi-sample/commit/db0b38271ac270e818c50323a0b30307d8073550))
- test new CI ([02cb74e](https://gitlab.com/AlbanAndrieu/fastapi-sample/commit/02cb74ec71c7ae36e654c8db7c08bbf674a94152))
- Update requirements.txt ([c141b57](https://gitlab.com/AlbanAndrieu/fastapi-sample/commit/c141b57acff6754a2439477157d02e58cb72bdec))
- uv ([dfce583](https://gitlab.com/AlbanAndrieu/fastapi-sample/commit/dfce583fa7427d4e81024bac97df52e1e70e97cd))
- vercel ([ecdcc67](https://gitlab.com/AlbanAndrieu/fastapi-sample/commit/ecdcc67fe69ffa904779f5b4790faa9d4e608846))
- versions ([dbdfd2d](https://gitlab.com/AlbanAndrieu/fastapi-sample/commit/dbdfd2d27a5397a4be2839708563933a2d03ca24))

### Features

- commitizen integration ([c0c23bf](https://gitlab.com/AlbanAndrieu/fastapi-sample/commit/c0c23bff45a5926455edb13cf696ade960e50c39))

## 1.2.5 (2026-01-02)

### Fix

- uv

## [1.2.4](https://gitlab.com/AlbanAndrieu/fastapi-sample/compare/1.2.3...1.2.4) (2025-10-13)

### Fix

- Add vscode files ([43f71e4](https://gitlab.com/AlbanAndrieu/fastapi-sample/commit/43f71e4c7e9aaf1e80a5dd7e80d9abb60ea9d687))

## [1.2.3](https://gitlab.com/AlbanAndrieu/fastapi-sample/compare/1.2.2...1.2.3) (2025-10-13)

### Fix

- pytest ([b4b26b7](https://gitlab.com/AlbanAndrieu/fastapi-sample/commit/b4b26b7f8a16cdf4ab49dee44bd435909e1fc1b6))

## [1.2.2](https://gitlab.com/AlbanAndrieu/fastapi-sample/compare/1.2.1...1.2.2) (2025-10-13)

### Fix

- pipfile lock ([63a1c9b](https://gitlab.com/AlbanAndrieu/fastapi-sample/commit/63a1c9b14c95bd8cfb764c9a63d2460b3e082287))

## [1.2.1](https://gitlab.com/AlbanAndrieu/fastapi-sample/compare/1.2.0...1.2.1) (2025-10-10)

### Fix

- upgrade to version 1.2.0 ([f58d847](https://gitlab.com/AlbanAndrieu/fastapi-sample/commit/f58d84728d3c75db839ac1add2aa6d63f074ce5d))

# [1.2.0](https://gitlab.com/AlbanAndrieu/fastapi-sample/compare/1.1.4...1.2.0) (2025-10-09)

### Feat

- Add feature flags ([6ef3c40](https://gitlab.com/AlbanAndrieu/fastapi-sample/commit/6ef3c40ab4bb64cdc3c5ca11d1e5b04f52cd6551))

# [1.2.0](https://gitlab.com/AlbanAndrieu/fastapi-sample/compare/1.1.4...1.2.0) (2025-10-08)

### Feat

- Add feature flags ([6ef3c40](https://gitlab.com/AlbanAndrieu/fastapi-sample/commit/6ef3c40ab4bb64cdc3c5ca11d1e5b04f52cd6551))

## [1.1.4](https://gitlab.com/AlbanAndrieu/fastapi-sample/compare/1.1.3...1.1.4) (2025-10-07)

### Fix

- gitlab pages ([3215ffd](https://gitlab.com/AlbanAndrieu/fastapi-sample/commit/3215ffd3a65c1be4141d421184dead04ca4ec138))

# [1.1.3]

Docker images 6.02GB

### Feat

- Add labchain with GPU and CUDA

# [1.1.0](https://gitlab.com/AlbanAndrieu/fastapi-sample/compare/1.0.5...1.1.0) (2024-12-10)

### Feat

- **env:** add Go installation and configuration to .envrc for better development setup ([f321726](https://gitlab.com/AlbanAndrieu/fastapi-sample/commit/f3217266728970e901cf3c0245868f252a42b551))
- **go.mod:** initialize Go module with module path and Go version ([7444150](https://gitlab.com/AlbanAndrieu/fastapi-sample/commit/7444150ce6b704827c9751bb2ad73991b7857484))
