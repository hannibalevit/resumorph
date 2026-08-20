# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.4.1] - 2026-08-20

### Bug Fixes

- Structured output retry on malformed json ([`dd79446`](https://github.com/hannibalevit/resumorph/commit/dd79446253527903cb073d4df5cedd5c96f7fc15))

- *(server)* Retry structured LLM output once on malformed JSON ([`dd79446`](https://github.com/hannibalevit/resumorph/commit/dd79446253527903cb073d4df5cedd5c96f7fc15))


### Documentation

- Point Claude at CodeGraph for code navigation when indexed ([`dd79446`](https://github.com/hannibalevit/resumorph/commit/dd79446253527903cb073d4df5cedd5c96f7fc15))

## [1.4.0] - 2026-08-01

### Bug Fixes

- *(extension)* Keep the service worker alive during field-answer generation ([`5b2e5e0`](https://github.com/hannibalevit/resumorph/commit/5b2e5e0fe58fbb4c737c1e5c8747d9c63467ec11))

- *(server)* Fail the Ollama connection test when no usable model is pulled ([`60addf9`](https://github.com/hannibalevit/resumorph/commit/60addf9ecba36083912d328c5fa57fa2a369738a))

- *(sidepanel)* Surface setup failures as errors and verify Ollama before saving ([`9746c25`](https://github.com/hannibalevit/resumorph/commit/9746c25663f8c0f1f9f5aab78344b330ac5f13a1))


### Documentation

- *(extension)* Keep the service worker alive during field-answer generation ([`5b2e5e0`](https://github.com/hannibalevit/resumorph/commit/5b2e5e0fe58fbb4c737c1e5c8747d9c63467ec11))


### Features

- *(extension)* Add request timeouts and cancel for backend calls ([`5e4b6fe`](https://github.com/hannibalevit/resumorph/commit/5e4b6fe2c333ce6d8f16592fb7436a30248c2947))

## [1.3.0] - 2026-08-01

### Bug Fixes

- *(server)* Address Ollama PR review feedback ([`3fbb154`](https://github.com/hannibalevit/resumorph/commit/3fbb1549f8bdbc457bc5ad703b9961d313067bcf))

- *(server)* Harden Ollama URL validation and slim local prompts ([`1658ff1`](https://github.com/hannibalevit/resumorph/commit/1658ff194dc1a0a44560b53b069cb35fde841bd1))

- *(extension)* Harden Ollama Settings URL preview and provider tests ([`16ec4f9`](https://github.com/hannibalevit/resumorph/commit/16ec4f98825150f210e0b865e7860b3a3e501e55))

- *(extension)* Skip blank Ollama URL probe; default to qwen2.5:7b ([`939ceed`](https://github.com/hannibalevit/resumorph/commit/939ceed6c6054d9b3aa25ebda2e2c7710d20b0ab))


### Features

- *(server)* Add Ollama provider ([`0b9f87a`](https://github.com/hannibalevit/resumorph/commit/0b9f87a190254034ca8183e2d50a4624f209bcbc))

- *(extension)* Add Ollama Settings and Onboarding UI ([`6cfb81c`](https://github.com/hannibalevit/resumorph/commit/6cfb81c08902d71cefe56d594444ef09f7096b08))

- *(extension)* Add Ollama Settings and Onboarding UI (#35) ([`1e45012`](https://github.com/hannibalevit/resumorph/commit/1e45012a33c8504e7af3a8060da84bb26d9eda80))

## [1.2.0] - 2026-07-30

### Features

- *(server)* Add Ollama provider (#32) ([`8672969`](https://github.com/hannibalevit/resumorph/commit/8672969cf8e4b6deaf8bbb0998d9bf0a23c8ddcc))

## [1.1.1] - 2026-07-27

### Bug Fixes

- Inline assistant in iframes (#21) ([`83a3e04`](https://github.com/hannibalevit/resumorph/commit/83a3e04ea075979c8bff8039d138d381560994fe))

## [1.1.0] - 2026-07-24

### Features

- Prompt improvements (#19) ([`b7fdbfd`](https://github.com/hannibalevit/resumorph/commit/b7fdbfd11f1be5ce39b74830a4fc7d129c4bdeb2))

## [1.0.2] - 2026-07-23

### Bug Fixes

- *(onboarding)* Retire default Claude model, add model picker (#17) ([`aa2562e`](https://github.com/hannibalevit/resumorph/commit/aa2562e5f405dc9f2c6b453720a2e7fe38ff85a0))

## [1.0.1] - 2026-07-23

### Bug Fixes

- Fix release notes changelog (#15) ([`64b5d04`](https://github.com/hannibalevit/resumorph/commit/64b5d04c52032f6142d4d0e7d326316c5bc3de99))

## [1.0.0] - 2026-07-23

### Breaking Changes

- Prepare project to open source (#14) ([`b517995`](https://github.com/hannibalevit/resumorph/commit/b517995463b4d8e184deddace9917c26e7f987d4))

