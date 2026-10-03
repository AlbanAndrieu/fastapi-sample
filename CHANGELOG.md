## [1.20.18](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.20.17...1.20.18) (2026-10-03)


### Bug Fixes

* **truenas:** ne plus afficher l’authentification verte sur timeout API ([#314](https://github.com/AlbanAndrieu/fastapi-sample/issues/314)) ([c2ade3b](https://github.com/AlbanAndrieu/fastapi-sample/commit/c2ade3b1c153acf97d25bbaf57d86a3430938f5d))

## [1.20.17](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.20.16...1.20.17) (2026-10-03)


### Bug Fixes

* **health:** corriger la CI et diagnostiquer l’ingress TrueNAS :7000 ([#313](https://github.com/AlbanAndrieu/fastapi-sample/issues/313)) ([139a9bc](https://github.com/AlbanAndrieu/fastapi-sample/commit/139a9bcf2acc46b9aac06100a2e37f39eab6ab32))

## [1.20.16](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.20.15...1.20.16) (2026-10-03)


### Bug Fixes

* **quality:** corriger le gate post-[#309](https://github.com/AlbanAndrieu/fastapi-sample/issues/309) et poursuivre les diagnostics catalogue ([#311](https://github.com/AlbanAndrieu/fastapi-sample/issues/311)) ([8629c77](https://github.com/AlbanAndrieu/fastapi-sample/commit/8629c77657ca2da1167a3ca56451c4b381939c6c))

## [1.20.15](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.20.14...1.20.15) (2026-10-03)


### Bug Fixes

* **health:** fiabiliser TrueNAS WAN, TLS et les verdicts d’exposition ([#308](https://github.com/AlbanAndrieu/fastapi-sample/issues/308)) ([0d77f51](https://github.com/AlbanAndrieu/fastapi-sample/commit/0d77f51a0472518a2971c5d84f7da84c668e1bb9))
* **truenas:** séparer appliance, WAN ingress, pfSense et Cloudflare ([#307](https://github.com/AlbanAndrieu/fastapi-sample/issues/307)) ([37f989a](https://github.com/AlbanAndrieu/fastapi-sample/commit/37f989ad55e92fafa522385bf72ae26ba629c5f4))
* **ui:** align mobile navigation and TrueNAS catalog [skip ci] ([#306](https://github.com/AlbanAndrieu/fastapi-sample/issues/306)) ([3bc9428](https://github.com/AlbanAndrieu/fastapi-sample/commit/3bc942860074ad6d8218effb725ae0e8a0f75337))

## [1.20.14](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.20.13...1.20.14) (2026-10-01)


### Bug Fixes

* **deps:** bump devalue ([#303](https://github.com/AlbanAndrieu/fastapi-sample/issues/303)) ([900bc1d](https://github.com/AlbanAndrieu/fastapi-sample/commit/900bc1df9c30a4b571d67c0a6f2ad97b9b7eb033))
* **deps:** bump virtualenv ([#304](https://github.com/AlbanAndrieu/fastapi-sample/issues/304)) ([da64c65](https://github.com/AlbanAndrieu/fastapi-sample/commit/da64c65390a667f0a05ac039ea9cb155e1be7982))
* **health:** fiabiliser les probes, Topology et l’UX mobile ([#302](https://github.com/AlbanAndrieu/fastapi-sample/issues/302)) ([de90467](https://github.com/AlbanAndrieu/fastapi-sample/commit/de9046794ae7b5416d17376fffde4e2fed5ed3fe))

## [1.20.13](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.20.12...1.20.13) (2026-09-30)


### Bug Fixes

* **deps:** bump brace-expansion ([#300](https://github.com/AlbanAndrieu/fastapi-sample/issues/300)) ([30780ad](https://github.com/AlbanAndrieu/fastapi-sample/commit/30780ad015fe979339e8d17fe0d2a0692c72336e))

## [1.20.12](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.20.11...1.20.12) (2026-09-30)


### Bug Fixes

* **deps:** bump the uv group across 1 directory with 3 updates ([#298](https://github.com/AlbanAndrieu/fastapi-sample/issues/298)) ([7cda1a2](https://github.com/AlbanAndrieu/fastapi-sample/commit/7cda1a2fbf75e4f4940683a2bcae80874fd53015))

## [1.20.11](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.20.10...1.20.11) (2026-09-30)


### Bug Fixes

* **deps:** bump the npm_and_yarn group across 1 directory with 2 updates ([#296](https://github.com/AlbanAndrieu/fastapi-sample/issues/296)) ([9123351](https://github.com/AlbanAndrieu/fastapi-sample/commit/9123351add1e3a139721ef55258871d547f418a7))

## [1.20.10](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.20.9...1.20.10) (2026-09-28)


### Bug Fixes

* **health:** préserver les warnings TrueNAS HTTPS ([#289](https://github.com/AlbanAndrieu/fastapi-sample/issues/289)) ([d4a3249](https://github.com/AlbanAndrieu/fastapi-sample/commit/d4a3249f70c576bb1bae6c9adeb7aecf5f59f050))
* **ui:** compacter les filtres health sur mobile ([#291](https://github.com/AlbanAndrieu/fastapi-sample/issues/291)) ([8e08b2d](https://github.com/AlbanAndrieu/fastapi-sample/commit/8e08b2dc9b2a96dde096d521e548312ee621cbb9))

## [1.20.9](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.20.8...1.20.9) (2026-09-27)


### Bug Fixes

* **catalog:** fail closed on pre-cutover v1 schema ([#281](https://github.com/AlbanAndrieu/fastapi-sample/issues/281)) ([08c0c88](https://github.com/AlbanAndrieu/fastapi-sample/commit/08c0c8870e3f291e3c8fddb7b0fe4e072a5bd650))
* **deps-dev:** bump @semantic-release/npm from 13.1.5 to 13.2.0 ([#288](https://github.com/AlbanAndrieu/fastapi-sample/issues/288)) ([6b7dc48](https://github.com/AlbanAndrieu/fastapi-sample/commit/6b7dc4803ed9e9985a48be5b7bef9bead1f332f4))
* **deps:** bump @astrojs/vercel from 11.0.10 to 11.0.11 ([#285](https://github.com/AlbanAndrieu/fastapi-sample/issues/285)) ([b973763](https://github.com/AlbanAndrieu/fastapi-sample/commit/b973763dc566cb7f023327074c528523df20caf4))
* **deps:** bump @supabase/supabase-js from 2.101.1 to 2.117.1 ([#287](https://github.com/AlbanAndrieu/fastapi-sample/issues/287)) ([f8b9624](https://github.com/AlbanAndrieu/fastapi-sample/commit/f8b9624aba526c13bdc10c5e8540112a2dbe0208))
* **deps:** bump vercel from 55.0.0 to 59.26.0 ([#284](https://github.com/AlbanAndrieu/fastapi-sample/issues/284)) ([d783801](https://github.com/AlbanAndrieu/fastapi-sample/commit/d783801b58a76247859a3723dc693872e2c7245d))


### Performance Improvements

* **health:** stale-refresh static homelab catalogs ([#280](https://github.com/AlbanAndrieu/fastapi-sample/issues/280)) ([f3079e6](https://github.com/AlbanAndrieu/fastapi-sample/commit/f3079e6a0909e77d71b245f776039338cf98bf2d))

## [1.20.8](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.20.7...1.20.8) (2026-09-20)


### Bug Fixes

* **deps-dev:** bump prisma from 6.19.3 to 7.10.0 ([#275](https://github.com/AlbanAndrieu/fastapi-sample/issues/275)) ([8be0a7e](https://github.com/AlbanAndrieu/fastapi-sample/commit/8be0a7e2d7899a2fe61537af0de78bc4a78018c3))
* **deps:** bump @astrojs/vercel from 11.0.7 to 11.0.10 ([#277](https://github.com/AlbanAndrieu/fastapi-sample/issues/277)) ([c2b47d8](https://github.com/AlbanAndrieu/fastapi-sample/commit/c2b47d8421513cb14146cb108ca2662c892e901a))
* **security:** fail closed MCP ops for local control plane [skip ci] ([#274](https://github.com/AlbanAndrieu/fastapi-sample/issues/274)) ([c710485](https://github.com/AlbanAndrieu/fastapi-sample/commit/c7104855d2788ef39205d1542624abbf636367af))

## [1.20.7](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.20.6...1.20.7) (2026-09-13)


### Performance Improvements

* **health:** harden post-264 probe fanout and provider reuse ([#270](https://github.com/AlbanAndrieu/fastapi-sample/issues/270)) ([f23684b](https://github.com/AlbanAndrieu/fastapi-sample/commit/f23684be03d91d1c0c22661ea03eff3733cf3d58))

## [1.20.6](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.20.5...1.20.6) (2026-09-13)


### Bug Fixes

* **deps-dev:** bump cz-emoji-conventional from 1.0.1 to 1.3.0 ([#267](https://github.com/AlbanAndrieu/fastapi-sample/issues/267)) ([bdfb0d3](https://github.com/AlbanAndrieu/fastapi-sample/commit/bdfb0d32998def0f0b96959c1905b39b5bc6ff1e))

## [1.20.5](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.20.4...1.20.5) (2026-09-13)


### Bug Fixes

* **deps-dev:** bump @commitlint/cli from 20.4.1 to 21.2.2 ([#269](https://github.com/AlbanAndrieu/fastapi-sample/issues/269)) ([8ef32d8](https://github.com/AlbanAndrieu/fastapi-sample/commit/8ef32d88ebf89a0286db4a5a4354554716c8aeb9))
* **deps-dev:** bump @commitlint/cz-commitlint from 20.3.1 to 21.2.2 ([#265](https://github.com/AlbanAndrieu/fastapi-sample/issues/265)) ([cd38c3f](https://github.com/AlbanAndrieu/fastapi-sample/commit/cd38c3fc77c9273b55d6685688943436c6009f77))
* **deps-dev:** bump globals from 17.11.0 to 17.12.0 ([#266](https://github.com/AlbanAndrieu/fastapi-sample/issues/266)) ([c4b412a](https://github.com/AlbanAndrieu/fastapi-sample/commit/c4b412a2f87fab442f87a7b822d42edfa47d5e10))
* **deps-dev:** bump prettier from 3.7.4 to 3.9.6 ([#268](https://github.com/AlbanAndrieu/fastapi-sample/issues/268)) ([ad82768](https://github.com/AlbanAndrieu/fastapi-sample/commit/ad82768c50a61d489b9f9130bc91ed4f505f1269))

## [1.20.4](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.20.3...1.20.4) (2026-09-13)


### Bug Fixes

* **health-ui:** pin probe columns and sync homelab fallback ([#264](https://github.com/AlbanAndrieu/fastapi-sample/issues/264)) ([efc0b0e](https://github.com/AlbanAndrieu/fastapi-sample/commit/efc0b0e35bf52458338c6df8f91a7b819b3c4c59))

## [1.20.3](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.20.2...1.20.3) (2026-09-12)


### Bug Fixes

* **health-ui:** stabilize TrueNAS diagnostics and responsive layout ([#262](https://github.com/AlbanAndrieu/fastapi-sample/issues/262)) ([617ba9a](https://github.com/AlbanAndrieu/fastapi-sample/commit/617ba9a182ae670043ee2f377e6925b17e49da95))

## [1.20.2](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.20.1...1.20.2) (2026-09-12)


### Bug Fixes

* **health-ui:** clarify Cloudflare and pfSense diagnostics ([#256](https://github.com/AlbanAndrieu/fastapi-sample/issues/256)) ([54d92ab](https://github.com/AlbanAndrieu/fastapi-sample/commit/54d92abde995681bad73a46cf24960cc1f05ba37))

## [1.20.1](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.20.0...1.20.1) (2026-09-12)


### Bug Fixes

* **ui:** separate public and LAN service probe evidence ([#255](https://github.com/AlbanAndrieu/fastapi-sample/issues/255)) ([e7f782e](https://github.com/AlbanAndrieu/fastapi-sample/commit/e7f782eea3fc4c4d6083f75bca54e15205be950b))

# [1.20.0](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.19.2...1.20.0) (2026-09-12)


### Features

* **ui:** stabilize homelab health board diagnostics ([#257](https://github.com/AlbanAndrieu/fastapi-sample/issues/257)) ([8a63a52](https://github.com/AlbanAndrieu/fastapi-sample/commit/8a63a5266166d027c1dd618b73f6f63b0164ea07))

## [1.19.2](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.19.1...1.19.2) (2026-09-12)


### Bug Fixes

* **health:** stabilize service filters and Access evidence ([#254](https://github.com/AlbanAndrieu/fastapi-sample/issues/254)) ([e10ceb5](https://github.com/AlbanAndrieu/fastapi-sample/commit/e10ceb5e0172878becf816877b69b6504adbeae1))

## [1.19.1](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.19.0...1.19.1) (2026-09-12)


### Bug Fixes

* **observability:** reduce local runtime log noise ([#251](https://github.com/AlbanAndrieu/fastapi-sample/issues/251)) ([c0682f0](https://github.com/AlbanAndrieu/fastapi-sample/commit/c0682f013913dc6151b71c95290aaed05f34dbb7))

# [1.19.0](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.18.0...1.19.0) (2026-09-11)


### Features

* **ui:** separate topology dependency and network views ([#250](https://github.com/AlbanAndrieu/fastapi-sample/issues/250)) ([6c4dd8e](https://github.com/AlbanAndrieu/fastapi-sample/commit/6c4dd8e8013b4d9237a256525b5b89fb7bedba96))

# [1.18.0](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.17.0...1.18.0) (2026-09-11)


### Features

* **ui:** make health filters shareable and compact ([#247](https://github.com/AlbanAndrieu/fastapi-sample/issues/247)) ([f61a06f](https://github.com/AlbanAndrieu/fastapi-sample/commit/f61a06f62de844a611c8629128ca0a7f7a82de8b))

# [1.17.0](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.16.1...1.17.0) (2026-09-11)


### Features

* **ui:** add diagnostic health filters and probe evidence ([#246](https://github.com/AlbanAndrieu/fastapi-sample/issues/246)) ([5117ca8](https://github.com/AlbanAndrieu/fastapi-sample/commit/5117ca81edab6010c08c8b8d6be713bf233dc42f))

## [1.16.1](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.16.0...1.16.1) (2026-09-11)


### Bug Fixes

* **health:** complete pfSense and provider flow observability ([#240](https://github.com/AlbanAndrieu/fastapi-sample/issues/240)) ([54c9bad](https://github.com/AlbanAndrieu/fastapi-sample/commit/54c9bada2f37378368339289e0a02da8576f2ff1))

# [1.16.0](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.15.1...1.16.0) (2026-09-11)


### Features

* **api:** improve homelab probe operator diagnostics ([#238](https://github.com/AlbanAndrieu/fastapi-sample/issues/238)) ([05376ed](https://github.com/AlbanAndrieu/fastapi-sample/commit/05376ed4ef01211322f7961297dcbbe70cea2037))

## [1.15.1](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.15.0...1.15.1) (2026-09-10)


### Bug Fixes

* **health:** preserve availability when Cloudflare evidence is unconfirmed ([#239](https://github.com/AlbanAndrieu/fastapi-sample/issues/239)) ([b63a389](https://github.com/AlbanAndrieu/fastapi-sample/commit/b63a389d275e51205660fb4729644a9a2ea081f6))

# [1.15.0](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.14.0...1.15.0) (2026-09-10)


### Features

* **kubernetes:** harden generic-service for Restricted PSS ([#237](https://github.com/AlbanAndrieu/fastapi-sample/issues/237)) ([dd54ab9](https://github.com/AlbanAndrieu/fastapi-sample/commit/dd54ab927a73db7a2873bd91f896e25928069786))

# [1.14.0](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.13.15...1.14.0) (2026-09-10)


### Features

* **health:** report local runtime dependency evidence ([#236](https://github.com/AlbanAndrieu/fastapi-sample/issues/236)) ([020a372](https://github.com/AlbanAndrieu/fastapi-sample/commit/020a372750a8a9e026a988ee83ea74119d9f3b91))

## [1.13.15](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.13.14...1.13.15) (2026-09-10)


### Bug Fixes

* **health:** keep probe deadlines and Cloudflare uncertainty non-degrading ([#235](https://github.com/AlbanAndrieu/fastapi-sample/issues/235)) ([025a760](https://github.com/AlbanAndrieu/fastapi-sample/commit/025a76077f60dc0f8e4318ff14bf24dc16fe170a))

## [1.13.14](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.13.13...1.13.14) (2026-09-10)


### Bug Fixes

* **health:** avoid false homelab deadlines and neutralize Cloudflare uncertainty ([#234](https://github.com/AlbanAndrieu/fastapi-sample/issues/234)) ([845bc62](https://github.com/AlbanAndrieu/fastapi-sample/commit/845bc62c0d1d9c70ccb9341cbf787ae05d3346eb))

## [1.13.13](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.13.12...1.13.13) (2026-09-10)


### Bug Fixes

* **truenas:** preserve app.query runtime binding evidence ([#233](https://github.com/AlbanAndrieu/fastapi-sample/issues/233)) ([2c07529](https://github.com/AlbanAndrieu/fastapi-sample/commit/2c075292b2b82dfcdc27dbeb9f295aaf0accb469))

## [1.13.12](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.13.11...1.13.12) (2026-09-09)


### Bug Fixes

* **ui:** render TrueNAS probe flow before aggregate health ([#232](https://github.com/AlbanAndrieu/fastapi-sample/issues/232)) ([548ec80](https://github.com/AlbanAndrieu/fastapi-sample/commit/548ec803944f15cbf199ea5f43d0514258c0cdb1))

## [1.13.11](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.13.10...1.13.11) (2026-09-09)


### Performance Improvements

* **health:** bound homelab diagnostics and stabilize Docker cache ([#231](https://github.com/AlbanAndrieu/fastapi-sample/issues/231)) ([7a900a0](https://github.com/AlbanAndrieu/fastapi-sample/commit/7a900a0c4cfe90e463ff814fa45e85cbf1c2f06b))

## [1.13.10](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.13.9...1.13.10) (2026-09-09)


### Bug Fixes

* **deploy:** restore production validation and publish release image ([#230](https://github.com/AlbanAndrieu/fastapi-sample/issues/230)) ([51504f6](https://github.com/AlbanAndrieu/fastapi-sample/commit/51504f6d96ba0a574f292b94e00d7b9059a5520a))

## [1.13.9](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.13.8...1.13.9) (2026-09-09)


### Bug Fixes

* **health:** preserve TrueNAS diagnostics under homelab probe fan-out ([#229](https://github.com/AlbanAndrieu/fastapi-sample/issues/229)) ([e98c0fe](https://github.com/AlbanAndrieu/fastapi-sample/commit/e98c0fecea95ee6535df0354d82edab3c226f22b))

## [1.13.8](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.13.7...1.13.8) (2026-09-08)


### Bug Fixes

* **ci:** apply Biome formatting after [#225](https://github.com/AlbanAndrieu/fastapi-sample/issues/225) ([#226](https://github.com/AlbanAndrieu/fastapi-sample/issues/226)) ([73782b7](https://github.com/AlbanAndrieu/fastapi-sample/commit/73782b7858dd921bdd20940ad12d6dc28647f27d))
* **deps:** bump the npm_and_yarn group across 1 directory with 4 updates ([#228](https://github.com/AlbanAndrieu/fastapi-sample/issues/228)) ([d42acb9](https://github.com/AlbanAndrieu/fastapi-sample/commit/d42acb97922f0ea60d5d25f5c49ced0e8d4d4585))

## [1.13.7](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.13.6...1.13.7) (2026-09-08)


### Bug Fixes

* **ui:** distinguish TrueNAS HTTPS exposure from API health ([#225](https://github.com/AlbanAndrieu/fastapi-sample/issues/225)) ([b76ea03](https://github.com/AlbanAndrieu/fastapi-sample/commit/b76ea038d13fd5a13478e5b11d24be18c1b4c9dd))

## [1.13.6](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.13.5...1.13.6) (2026-09-08)


### Bug Fixes

* **homelab:** reconcile Garage exposure bootstrap ([#224](https://github.com/AlbanAndrieu/fastapi-sample/issues/224)) ([d18e4b1](https://github.com/AlbanAndrieu/fastapi-sample/commit/d18e4b1602d6576c847a6ec996826ff84e4a148e))

## [1.13.5](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.13.4...1.13.5) (2026-09-08)


### Bug Fixes

* **pfsense:** tolerate slow LAN snort2c telemetry ([#222](https://github.com/AlbanAndrieu/fastapi-sample/issues/222)) ([3c2d26c](https://github.com/AlbanAndrieu/fastapi-sample/commit/3c2d26c280ca7337584a6b4dad2c6522ab239af0))

## [1.13.4](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.13.3...1.13.4) (2026-09-08)


### Bug Fixes

* **ci:** converge post-220 quality gate ([#221](https://github.com/AlbanAndrieu/fastapi-sample/issues/221)) ([2e0f1a2](https://github.com/AlbanAndrieu/fastapi-sample/commit/2e0f1a29873abb898e7adfa5baa3e594d3faa513))

## [1.13.3](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.13.2...1.13.3) (2026-09-08)


### Bug Fixes

* **ui:** reconcile health board, Garage catalog and CI ([#220](https://github.com/AlbanAndrieu/fastapi-sample/issues/220)) ([fbf322b](https://github.com/AlbanAndrieu/fastapi-sample/commit/fbf322bd12fbdd9f9876b3abd8e798c7977aec97))

## [1.13.2](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.13.1...1.13.2) (2026-09-08)


### Bug Fixes

* **ui:** restore health-board grouping behind diagnostics protection ([#218](https://github.com/AlbanAndrieu/fastapi-sample/issues/218)) ([2b57a6a](https://github.com/AlbanAndrieu/fastapi-sample/commit/2b57a6af799ea8df516b27ab349de4fe3e3c722c))

## [1.13.1](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.13.0...1.13.1) (2026-09-08)


### Bug Fixes

* **ci:** converge agent preflight and reduce CI churn ([#215](https://github.com/AlbanAndrieu/fastapi-sample/issues/215)) ([d87abdc](https://github.com/AlbanAndrieu/fastapi-sample/commit/d87abdc2e2bdc11ec60034fef15bf24383b68630))

# [1.13.0](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.12.1...1.13.0) (2026-09-08)


### Features

* **ui:** prioritize critical core platform health ([#217](https://github.com/AlbanAndrieu/fastapi-sample/issues/217)) ([4164ca2](https://github.com/AlbanAndrieu/fastapi-sample/commit/4164ca23261de7e38bb544b63b717f295a0c36cf))

## [1.12.1](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.12.0...1.12.1) (2026-09-08)


### Bug Fixes

* **health:** preserve stale and stopped runtime semantics ([#214](https://github.com/AlbanAndrieu/fastapi-sample/issues/214)) ([c4b4b64](https://github.com/AlbanAndrieu/fastapi-sample/commit/c4b4b64e341af078e4f065a1f3e0b387b11b6acf))

# [1.12.0](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.11.5...1.12.0) (2026-09-08)


### Features

* **ci:** add critical Unbound and agent pre-build gate ([#213](https://github.com/AlbanAndrieu/fastapi-sample/issues/213)) ([e6565b3](https://github.com/AlbanAndrieu/fastapi-sample/commit/e6565b3cf7c8bd1ead5e5d4ac1a18efae3f1295a))

## [1.11.5](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.11.4...1.11.5) (2026-09-07)


### Bug Fixes

* **health:** make homelab downtime authoritative ([#212](https://github.com/AlbanAndrieu/fastapi-sample/issues/212)) ([339816a](https://github.com/AlbanAndrieu/fastapi-sample/commit/339816a4418973e5f1a2fa9942ab7e0f5c74ec14))

## [1.11.4](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.11.3...1.11.4) (2026-09-07)


### Bug Fixes

* **pyroscope:** profile production FastAPI workers ([#211](https://github.com/AlbanAndrieu/fastapi-sample/issues/211)) ([bf729e1](https://github.com/AlbanAndrieu/fastapi-sample/commit/bf729e1769de6a4f88ef6c1e9f1daa6c2aba53a5))

## [1.11.3](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.11.2...1.11.3) (2026-09-07)


### Bug Fixes

* **health:** treat trusted LAN pfSense access as legitimate ([#210](https://github.com/AlbanAndrieu/fastapi-sample/issues/210)) ([c0cd8c7](https://github.com/AlbanAndrieu/fastapi-sample/commit/c0cd8c7ea3751b05bddbd34995d4c8a142d665ac))

## [1.11.2](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.11.1...1.11.2) (2026-09-07)


### Bug Fixes

* **sentry:** connect homelab runtime and MCP to self-hosted Sentry ([#209](https://github.com/AlbanAndrieu/fastapi-sample/issues/209)) ([67355c4](https://github.com/AlbanAndrieu/fastapi-sample/commit/67355c4986f9dbbbdf2c7b1d15ff58d1922d002a))

## [1.11.1](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.11.0...1.11.1) (2026-09-06)


### Bug Fixes

* **truenas:** preserve beta 2 observer security contract ([#207](https://github.com/AlbanAndrieu/fastapi-sample/issues/207)) ([d67990f](https://github.com/AlbanAndrieu/fastapi-sample/commit/d67990f5813ce7de16fb093db23718ed25d35e70))

# [1.11.0](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.10.0...1.11.0) (2026-09-06)


### Features

* **runtime:** model TrueNAS as homelab production ([#206](https://github.com/AlbanAndrieu/fastapi-sample/issues/206)) ([c3c8670](https://github.com/AlbanAndrieu/fastapi-sample/commit/c3c8670da2c269fbf0eb570068f2b9350a2e3bfa))

# [1.10.0](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.9.1...1.10.0) (2026-09-06)


### Features

* **ui:** expose NIST CSF 2.0 security functions ([#205](https://github.com/AlbanAndrieu/fastapi-sample/issues/205)) ([dbeb232](https://github.com/AlbanAndrieu/fastapi-sample/commit/dbeb2324db081645bf3af8d29b0c7058aefa40e6))

## [1.9.1](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.9.0...1.9.1) (2026-09-06)


### Bug Fixes

* **catalog:** preserve declared security metadata ([#199](https://github.com/AlbanAndrieu/fastapi-sample/issues/199)) ([5b5e3b6](https://github.com/AlbanAndrieu/fastapi-sample/commit/5b5e3b6d2a91ef4b5a4e6a5af931b3061941fc93))
* **deps-dev:** bump @typescript-eslint/parser from 8.68.0 to 8.69.0 ([#202](https://github.com/AlbanAndrieu/fastapi-sample/issues/202)) ([6c92303](https://github.com/AlbanAndrieu/fastapi-sample/commit/6c923032fd7c824b45f6f92a6a01762b2fa6e548))
* **deps:** bump @ai-sdk/openai-compatible from 2.0.15 to 3.0.43 ([#203](https://github.com/AlbanAndrieu/fastapi-sample/issues/203)) ([9c60673](https://github.com/AlbanAndrieu/fastapi-sample/commit/9c60673f02982d1b081896f6d59eca595098007c))
* **deps:** bump @dotenvx/dotenvx from 1.51.2 to 2.23.0 ([#200](https://github.com/AlbanAndrieu/fastapi-sample/issues/200)) ([f1e6de0](https://github.com/AlbanAndrieu/fastapi-sample/commit/f1e6de0d73a8dc7cde8cdf5dd951634c95904355))

# [1.9.0](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.8.0...1.9.0) (2026-09-06)


### Features

* **observability:** add bounded core metrics overview ([#197](https://github.com/AlbanAndrieu/fastapi-sample/issues/197)) ([9d8a42c](https://github.com/AlbanAndrieu/fastapi-sample/commit/9d8a42cd571192e2290fd2ff8708f95af97f8751))

# [1.8.0](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.7.2...1.8.0) (2026-09-06)


### Features

* **ui:** make homelab health service-first ([#196](https://github.com/AlbanAndrieu/fastapi-sample/issues/196)) ([9f8cc42](https://github.com/AlbanAndrieu/fastapi-sample/commit/9f8cc42ec5d9b2a7c84c5b13e5b26c12253948ed))

## [1.7.2](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.7.1...1.7.2) (2026-09-05)


### Bug Fixes

* **ci:** finish post-login-demo cleanup ([#194](https://github.com/AlbanAndrieu/fastapi-sample/issues/194)) ([54b61d8](https://github.com/AlbanAndrieu/fastapi-sample/commit/54b61d88fd78225244282c052fd628c5104913e0))

## [1.7.1](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.7.0...1.7.1) (2026-09-05)


### Bug Fixes

* **security:** harden local runtime and pfSense probes ([#191](https://github.com/AlbanAndrieu/fastapi-sample/issues/191)) ([39beccf](https://github.com/AlbanAndrieu/fastapi-sample/commit/39beccfd28a3cf7e46aee0355bae95c7b069a2f8))

# [1.7.0](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.6.5...1.7.0) (2026-09-05)


### Features

* **ui:** improve /api mobile responsiveness ([#190](https://github.com/AlbanAndrieu/fastapi-sample/issues/190)) ([7d439d2](https://github.com/AlbanAndrieu/fastapi-sample/commit/7d439d218bcc7ad9e357b1fe69af9d5b4bc89642))

## [1.6.5](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.6.4...1.6.5) (2026-09-05)


### Bug Fixes

* **runtime:** detect FastAPI Cloud and expose Redis usage ([#189](https://github.com/AlbanAndrieu/fastapi-sample/issues/189)) ([c8e0bd7](https://github.com/AlbanAndrieu/fastapi-sample/commit/c8e0bd7a5fc5e934682d309f8b46c7b3e8a117fd))

## [1.6.4](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.6.3...1.6.4) (2026-09-05)


### Bug Fixes

* **observability:** isolate runtime telemetry and clean access logs ([#186](https://github.com/AlbanAndrieu/fastapi-sample/issues/186)) ([184fe5c](https://github.com/AlbanAndrieu/fastapi-sample/commit/184fe5c32ab11744d1f5595e3a62b04f5cabf770))

## [1.6.3](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.6.2...1.6.3) (2026-09-05)


### Bug Fixes

* **ui:** distinguish local runtime and reduce log noise ([#185](https://github.com/AlbanAndrieu/fastapi-sample/issues/185)) ([2e066bd](https://github.com/AlbanAndrieu/fastapi-sample/commit/2e066bdb651652d79c552d31026b39102aa0ce84))

## [1.6.2](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.6.1...1.6.2) (2026-09-04)


### Performance Improvements

* **cache:** bound provider origin refresh rates ([#183](https://github.com/AlbanAndrieu/fastapi-sample/issues/183)) ([189335a](https://github.com/AlbanAndrieu/fastapi-sample/commit/189335a759268e565250d792d45fed4f88124d66))

## [1.6.1](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.6.0...1.6.1) (2026-09-03)


### Performance Improvements

* **health:** bound aggregate diagnostic fan-out ([#178](https://github.com/AlbanAndrieu/fastapi-sample/issues/178)) ([3b490a3](https://github.com/AlbanAndrieu/fastapi-sample/commit/3b490a335e52f6b0c37ef970f5dfab82bcbcc9ed))

# [1.6.0](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.5.10...1.6.0) (2026-09-03)


### Features

* **topology:** accept hostedBy placement relations ([#177](https://github.com/AlbanAndrieu/fastapi-sample/issues/177)) ([e38d79b](https://github.com/AlbanAndrieu/fastapi-sample/commit/e38d79b1fb1efe4f6f6d0251775ca6469b05ad79))

## [1.5.10](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.5.9...1.5.10) (2026-09-03)


### Bug Fixes

* **health:** stabilize TrueNAS and pfSense probes ([#176](https://github.com/AlbanAndrieu/fastapi-sample/issues/176)) ([b728f0b](https://github.com/AlbanAndrieu/fastapi-sample/commit/b728f0b23a8a840e6f99beff2de39b8b9fde2a91))

## [1.5.9](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.5.8...1.5.9) (2026-09-03)


### Performance Improvements

* **cache:** prevent local probe stampedes ([#175](https://github.com/AlbanAndrieu/fastapi-sample/issues/175)) ([eee8730](https://github.com/AlbanAndrieu/fastapi-sample/commit/eee8730c74dd1b121e485dc9b361f67000c8c2c3))

## [1.5.8](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.5.7...1.5.8) (2026-09-03)

This release consolidates the changes that were temporarily published as `1.6.0` and `1.7.0` after those GitHub Releases were removed. Git history is unchanged; `1.5.8` becomes the maintained release baseline.

### Features

* **health:** expose edge evidence and resilient production diagnostics ([#170](https://github.com/AlbanAndrieu/fastapi-sample/issues/170)) ([d69b3cf](https://github.com/AlbanAndrieu/fastapi-sample/commit/d69b3cf728e8f2bf91ebc6a524376cf7543aea01))
* **cache:** share external probe results across replicas ([#171](https://github.com/AlbanAndrieu/fastapi-sample/issues/171)) ([edc66db](https://github.com/AlbanAndrieu/fastapi-sample/commit/edc66db28df5d709bd62bbcf0bbb66e6d5eefa83))

### Bug Fixes

* **cache:** harden shared probe stale validation ([#172](https://github.com/AlbanAndrieu/fastapi-sample/issues/172)) ([dcc6e71](https://github.com/AlbanAndrieu/fastapi-sample/commit/dcc6e714136735381daf548d05df2a02499e155b))

## [1.5.7](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.5.6...1.5.7) (2026-09-02)


### Bug Fixes

* **health:** expose runtime topology and stabilize security telemetry ([#169](https://github.com/AlbanAndrieu/fastapi-sample/issues/169)) ([1bda3ba](https://github.com/AlbanAndrieu/fastapi-sample/commit/1bda3ba01aeaae80f2f53d5ad18bdb974ed575b8))

## [1.5.6](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.5.5...1.5.6) (2026-09-02)


### Performance Improvements

* **health:** stabilize production diagnostics ([#168](https://github.com/AlbanAndrieu/fastapi-sample/issues/168)) ([50be4a5](https://github.com/AlbanAndrieu/fastapi-sample/commit/50be4a50ed398d984e927fd5015ef3d452f510fb))

## [1.5.5](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.5.4...1.5.5) (2026-09-02)


### Bug Fixes

* **pfsense:** reconcile source-aware exposure policy ([#167](https://github.com/AlbanAndrieu/fastapi-sample/issues/167)) ([3001e3d](https://github.com/AlbanAndrieu/fastapi-sample/commit/3001e3da7c265341cec1314724fd55255b83e23b))

## [1.5.4](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.5.3...1.5.4) (2026-09-02)


### Bug Fixes

* **pfsense:** stabilize posture and Snort observability ([#166](https://github.com/AlbanAndrieu/fastapi-sample/issues/166)) ([08663d4](https://github.com/AlbanAndrieu/fastapi-sample/commit/08663d4bf24b42eac12e0def5eeb04da328448fb))

## [1.5.3](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.5.2...1.5.3) (2026-09-02)


### Bug Fixes

* **pfsense:** use dedicated security API key ([#165](https://github.com/AlbanAndrieu/fastapi-sample/issues/165)) ([dafbf91](https://github.com/AlbanAndrieu/fastapi-sample/commit/dafbf91d15a7eab0eeb0decf7aca187f8110000b))

## [1.5.2](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.5.1...1.5.2) (2026-09-02)


### Performance Improvements

* **health:** parallelize probes and model trusted pfSense access ([#164](https://github.com/AlbanAndrieu/fastapi-sample/issues/164)) ([f132a19](https://github.com/AlbanAndrieu/fastapi-sample/commit/f132a19c4c580474b13db011cc0e1b9f33ae9306))

## [1.5.1](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.5.0...1.5.1) (2026-09-02)


### Bug Fixes

* **deps-dev:** bump @humanfs/node ([#162](https://github.com/AlbanAndrieu/fastapi-sample/issues/162)) ([27faaf0](https://github.com/AlbanAndrieu/fastapi-sample/commit/27faaf0ee7dd478df1df86e4c0466800fcfdb386))
* **deps-dev:** bump @humanfs/node ([#163](https://github.com/AlbanAndrieu/fastapi-sample/issues/163)) ([8273f53](https://github.com/AlbanAndrieu/fastapi-sample/commit/8273f53dd3e9d52af373ab87d11ef9f6cebd5738))

# [1.5.0](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.4.13...1.5.0) (2026-09-02)


### Features

* **health:** attribute Snort PF ingress blocks ([#161](https://github.com/AlbanAndrieu/fastapi-sample/issues/161)) ([0f28638](https://github.com/AlbanAndrieu/fastapi-sample/commit/0f286384b2e5d4a322c7e2df1253bca582718749))

## [1.4.13](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.4.12...1.4.13) (2026-09-01)


### Bug Fixes

* **health:** separate TrueNAS TCP and TLS diagnostics ([#160](https://github.com/AlbanAndrieu/fastapi-sample/issues/160)) ([00dd9ce](https://github.com/AlbanAndrieu/fastapi-sample/commit/00dd9ce2a579236551af8a45e441708b3b56fb5f))

## [1.4.12](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.4.11...1.4.12) (2026-09-01)


### Bug Fixes

* **ci:** align pfSense roadmap indentation ([#159](https://github.com/AlbanAndrieu/fastapi-sample/issues/159)) ([fd3ee28](https://github.com/AlbanAndrieu/fastapi-sample/commit/fd3ee28b2222e536b35ffa54d84c512fcaa80346))

## [1.4.11](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.4.10...1.4.11) (2026-09-01)


### Bug Fixes

* **health:** reduce network probe fan-out ([#158](https://github.com/AlbanAndrieu/fastapi-sample/issues/158)) ([f58ab37](https://github.com/AlbanAndrieu/fastapi-sample/commit/f58ab37dabd63c1ffeaf8e43544e959d8873492b))

## [1.4.10](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.4.9...1.4.10) (2026-09-01)


### Bug Fixes

* **deps-dev:** bump @biomejs/biome from 2.2.6 to 2.5.11 ([#151](https://github.com/AlbanAndrieu/fastapi-sample/issues/151)) ([e26d723](https://github.com/AlbanAndrieu/fastapi-sample/commit/e26d723fd231f552b58a61133c8d01ff7d9af0a5))
* **deps-dev:** bump typescript-eslint from 8.50.0 to 8.68.0 ([#150](https://github.com/AlbanAndrieu/fastapi-sample/issues/150)) ([da08e52](https://github.com/AlbanAndrieu/fastapi-sample/commit/da08e524094808a9a2b9601d21f5bd9f0a457cf9))
* **deps:** bump docker/login-action from 3.7.0 to 4.6.0 ([#155](https://github.com/AlbanAndrieu/fastapi-sample/issues/155)) ([8651c25](https://github.com/AlbanAndrieu/fastapi-sample/commit/8651c252b89bcf9bc9eb7a5b83b7e90f9b32de80))
* **deps:** bump docker/setup-buildx-action from 4.2.0 to 4.3.0 ([#152](https://github.com/AlbanAndrieu/fastapi-sample/issues/152)) ([c6b869aa0837031b1509e52ab3951f33d58b3572))
* **deps:** bump renovatebot/github-action from 46.2.1 to 46.2.4 ([#154](https://github.com/AlbanAndrieu/fastapi-sample/issues/154)) ([84bf1eb](https://github.com/AlbanAndrieu/fastapi-sample/commit/84bf1eb86e14b74a7cfdd5934f52e24d977da22c))
* **deps:** bump trunk-io/analytics-uploader from 1.15.0 to 2.1.2 ([#153](https://github.com/AlbanAndrieu/fastapi-sample/issues/153)) ([7f19e95](https://github.com/AlbanAndrieu/fastapi-sample/commit/7f19e95a44282c0a153100e5a05298022943dd27))

## [1.4.9](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.4.8...1.4.9) (2026-09-01)


### Bug Fixes

* **deps-dev:** bump @nuxt/eslint-config from 0.3.13 to 1.17.0 ([#147](https://github.com/AlbanAndrieu/fastapi-sample/issues/147)) ([2bc4335](https://github.com/AlbanAndrieu/fastapi-sample/commit/2bc4335a1a993d8bce83ed8efc4651fbb3d90cc9))
* **deps:** bump astral-sh/setup-uv from 9.0.0 to 10.0.1 ([#157](https://github.com/AlbanAndrieu/fastapi-sample/issues/157)) ([ceaedc2](https://github.com/AlbanAndrieu/fastapi-sample/commit/ceaedc2645901d0000370a328b86e78bb996949d))

## [1.4.8](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.4.7...1.4.8) (2026-09-01)


### Bug Fixes

* **ci:** complete CodeQL v4 migration and harden quality gate ([#143](https://github.com/AlbanAndrieu/fastapi-sample/issues/143)) ([ac5c293](https://github.com/AlbanAndrieu/fastapi-sample/commit/ac5c293a86560e1c2a48d361e34ad4066eab8d26))

## [1.4.7](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.4.6...1.4.7) (2026-09-01)


### Bug Fixes

* **health:** expose stale dependency and cycle evidence ([#136](https://github.com/AlbanAndrieu/fastapi-sample/issues/136)) ([c1468c3](https://github.com/AlbanAndrieu/fastapi-sample/commit/c1468c317ad8fa54b60fce29e68904bba41dc2e7))

## [1.4.6](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.4.5...1.4.6) (2026-08-29)


### Bug Fixes

* **ci:** bound production smoke browser cost ([#135](https://github.com/AlbanAndrieu/fastapi-sample/issues/135)) ([dfa7c1b](https://github.com/AlbanAndrieu/fastapi-sample/commit/dfa7c1b3fb422b8b40df1b86fd030e7ddb3cf1b7))

## [1.4.5](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.4.4...1.4.5) (2026-08-29)


### Bug Fixes

* **ci:** harden Dockerfile linting ([#134](https://github.com/AlbanAndrieu/fastapi-sample/issues/134)) ([6ae9b00](https://github.com/AlbanAndrieu/fastapi-sample/commit/6ae9b00559532375a53c8cf09f170097304043a8))

## [1.4.4](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.4.3...1.4.4) (2026-08-29)


### Bug Fixes

* **release:** respect private package policy ([#132](https://github.com/AlbanAndrieu/fastapi-sample/issues/132)) ([c9fe18b](https://github.com/AlbanAndrieu/fastapi-sample/commit/c9fe18b6b4384ade021dad793e1239948b892ae6))

## [1.4.3](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.4.2...1.4.3) (2026-08-29)


### Bug Fixes

* **release:** align trusted publisher OIDC claims ([#133](https://github.com/AlbanAndrieu/fastapi-sample/issues/133)) ([55e88ec](https://github.com/AlbanAndrieu/fastapi-sample/commit/55e88ecc40d5865ae629e329bef27c489f924e0a))

## [1.4.2](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.4.1...1.4.2) (2026-08-28)


### Bug Fixes

* **release:** harden post-1.4.1 publishing ([#131](https://github.com/AlbanAndrieu/fastapi-sample/issues/131)) ([4bd9737](https://github.com/AlbanAndrieu/fastapi-sample/commit/4bd9737a2efdad048a2bcf512b55a57bf0be1f7c))

# Changelog

## 1.4.1 — homelab diagnostics and release recovery (2026-08-29)

### Health, security and observability

- Add ordered TrueNAS DNS, TCP, TLS, HTTPS, WebSocket, authentication and API diagnostics with explicit required-dependency failures.
- Reconcile service availability and exposure policy using the authoritative `nabla-compose` catalog with validated last-known-good/bootstrap fallback behavior.
- Expose only sanitized provider credential-presence state and improve pfSense/Cloudflare/TrueNAS diagnostics without leaking secret material.
- Group the API health board by topology/blast radius and preserve service metadata, icons and policy-aware Sickz behavior.
- Encapsulate homelab catalog cache state and serialize expired-cache refreshes so concurrent health/UI requests share one authoritative-source request.

### CI, release and deployment

- Reuse an outside-in production smoke workflow after immutable-tag FastAPI Cloud deployments.
- Keep Python 3.13, version-consistency, Docker/Trivy, MegaLinter and code-scanning gates in the release path.
- Replace the incompatible local `1.4.0` retagging workaround with a deterministic, retryable `1.4.1` recovery that never rewrites the historical remote tag.
- Synchronize explicit recovery versions across npm, Python, uv and Docker metadata with exact-match assertions before publishing.
- Return to normal Conventional Commit semantic-release progression after `1.4.1` establishes the new immutable release baseline.

## 1.4.0 — consolidated release (2026-08-27)

This release intentionally consolidates the work that was temporarily published under versions greater than `1.4.0`. Those GitHub releases were removed and the project is being realigned on `1.4.0` as the release baseline.

### Runtime, deployment and packaging

- Standardize supported runtime and CI on Python 3.13, including FastAPI Cloud and Docker.
- Harden FastAPI Cloud deployment metadata, runtime detection, health endpoints and production entrypoints.
- Keep Docker runtime minimal and align application version metadata across Python, npm and OCI images.
- Align local/MCP serving ports and deployment configuration, including the 8091 local MCP compatibility work.
- Reduce Vercel deployment scope and improve runtime/route handling.
- Harden semantic-release, release-baseline validation, GitHub release publication and version synchronization.
- Improve dependency, Renovate, CodeQL, MegaLinter, pre-commit and repository quality workflows.

### Homelab catalog and topology

- Introduce the typed homelab service catalog and validated topology APIs.
- Preserve service IDs, icons, internal endpoints, external exposure intent and security metadata.
- Make FastAPI the authoritative exposure-policy source and add explicit exposure overrides where required.
- Reconcile declared services with TrueNAS runtime/application inventory.
- Add application lifecycle observations and cached TrueNAS runtime snapshots.
- Add public homelab health APIs and split internal versus external observations.

### TrueNAS

- Add the TrueNAS dependency health signal and the read-only TrueNAS 26 API client integration.
- Consolidate TrueNAS URL handling around `TRUENAS_URL` with `https://truenas.albandrieu.com:7000` as the default.
- Add runtime/application inventory checks, caching and stale-result handling.
- Make TrueNAS required infrastructure in the production health board while distinguishing public ingress, optional internal TCP and authenticated API evidence.
- Add explicit INFO logging of the effective `TRUENAS_URL` to diagnose FastAPI Cloud connectivity.

### Exposure security, Sickz and Cloudflare

- Split Sickz from generic availability health and turn it into exposure-policy validation.
- Verify declared `external` and `tunnelSecure` intent against HTTP reachability, TLS trust and Cloudflare evidence.
- Add the read-only Cloudflare Tunnel observer and reconcile tunnel observations with declared service posture.
- Detect private services that unexpectedly become externally reachable or gain Cloudflare ingress.
- Verify Cloudflare-protected public services and report uncertain observer states separately.
- Preserve explicit direct `.int.albandrieu.com` exposure as a security warning rather than silently treating it as secure.
- Add protocol-aware pfSense/public-port policy checks, including SSH, LiteLLM and TrueNAS exposure expectations.
- Correct the LiteLLM public-policy port from 4100 to 4000.
- Detect application-level failure payloads even when an endpoint returns an HTTP success status.

### Health board and UI

- Refactor the health subsystem into focused platform, integration, observability, homelab and Sickz modules.
- Add reconciled service-health evidence and distinguish availability health from security-policy compliance.
- Improve refresh diagnostics, stale-state handling and required-infrastructure reporting.
- Split API JavaScript and CSS assets by responsibility and simplify the API page implementation.
- Improve Sickz status rendering, TLS indicators, Cloudflare evidence and pfSense port-policy presentation.
- Add OpenGraph/runtime presentation improvements and preserve service icons in the topology UI.

### Observability and robustness

- Simplify Logfire/FastAPI Cloud integration and keep observability integrations optional when disabled.
- Isolate Datadog runtime lifecycle and make it optional for FastAPI Cloud.
- Improve Sentry, Redis and optional integration health handling.
- Harden logging formatters and stream handlers against malformed records.
- Refactor Redis async lifecycle and failure handling.
- Improve notes persistence/queue error isolation and application startup/shutdown robustness.

### Architecture and maintainability

- Split oversized health, UI, configuration and integration modules into focused components.
- Introduce reusable FastAPI, homelab-service-contract and Redis lifecycle skills/rules for coding agents.
- Add feature flags, access-control helpers and environment/runtime abstractions.
- Consolidate engineering roadmap and health/environment documentation.
- Preserve the project line-count quality contract rather than relaxing oversized-module thresholds.

### Included post-1.4.0 work

The consolidation includes the changes previously represented by the temporary `1.4.1`, `1.5.x`, `1.6.x`, `1.7.x` and `1.8.x` release history, notably PRs #45–#101 and their follow-up fixes/refactors. The Git commit history remains the authoritative detailed audit trail.

---

## Historical releases before 1.4.0

Detailed pre-1.4.0 release history remains available in Git history and the tags `1.0.0` through `1.3.8`. The consolidated `1.4.0` entry above is now the maintained release baseline.
