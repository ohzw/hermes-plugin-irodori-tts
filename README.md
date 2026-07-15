# Hermes Irodori TTS Plugin

A standalone [Hermes Agent](https://github.com/NousResearch/hermes-agent) plugin for running [Irodori-TTS-Server](https://github.com/Aratako/Irodori-TTS-Server) as a local Japanese text-to-speech backend.

It provides:

- a native `irodori-local` Python TTS provider for Hermes
- automatic Irodori server health checks, startup, retry, and restart handling
- configurable rewrite prompts and pronunciation dictionary support
- bounded request/audio history and diagnostics
- a standalone Irodori dashboard plus a lightweight launcher in the Hermes dashboard
- `hermes irodori setup`, `status`, and `dashboard` commands

The model, voice assets, generated audio, personal dictionary, and Hermes configuration are not bundled.

## Requirements

- Hermes Agent 0.18.2 or newer with Python TTS-provider and dashboard-plugin support
- Python 3.11+
- Node.js 20+ only when rebuilding the dashboard frontend
- `uv`
- a local Irodori-TTS-Server checkout

## Install Irodori-TTS-Server

Follow the upstream instructions for your platform. A typical CPU/local setup starts with:

```bash
git clone https://github.com/Aratako/Irodori-TTS-Server.git ~/src/Irodori-TTS-Server
cd ~/src/Irodori-TTS-Server
uv sync --extra cpu
cp .env.example .env
```

Choose the backend and model configuration appropriate for your machine. Apple Silicon users should follow the current upstream instructions rather than copying CUDA options.

## Install this Hermes plugin

Once this repository is published:

```bash
hermes plugins install ohzw/hermes-plugin-irodori-tts --enable
```

For local development, clone the repository and link it into the active Hermes profile:

```bash
git clone <your-fork-url> ~/src/hermes-plugin-irodori-tts
ln -s ~/src/hermes-plugin-irodori-tts ~/.hermes/plugins/irodori-tts
hermes plugins enable irodori-tts
```

Restart Hermes after enabling a plugin.

## Configure Hermes

Activate the Python provider and record the server checkout:

```bash
hermes irodori setup \
  --server-workdir ~/src/Irodori-TTS-Server \
  --base-url http://127.0.0.1:8088/v1
```

This updates `~/.hermes/config.yaml` atomically and creates `~/.hermes/config.yaml.irodori-backup` before the first migration. If an older `type: command` Irodori provider is present, its install-specific `command` is removed while all voice, rewrite, chunking, dictionary, and history settings are preserved.

Restart Hermes, then verify:

```bash
hermes irodori status
```

A complete non-personal configuration example is available at [`examples/config.example.yaml`](examples/config.example.yaml).

### Important configuration rule

Behavioral settings belong in `~/.hermes/config.yaml`. Secrets belong in `~/.hermes/.env`. Do not commit either file.

## Dashboard

Start the standalone dashboard only when you need it:

```bash
hermes irodori dashboard
```

The command starts a background localhost server and opens `http://127.0.0.1:9120/workspace`. The standalone app owns normal browser routes, so direct navigation, reload, back, and forward work for:

```text
/workspace
/overview
/history
/dictionary
/diagnostics
```

Manage the process explicitly:

```bash
hermes irodori dashboard start
hermes irodori dashboard open
hermes irodori dashboard status
hermes irodori dashboard stop
```

The app includes:

- Workspace — editable voice settings and a synthesis playground
- Overview — health and latency metrics
- History — the 50 most recent Hermes TTS requests, including failures and saved audio for successful requests
- Dictionary — pronunciation entries and validation
- Diagnostics — safe, allowlisted configuration and server logs

Its API is same-origin under `/api/`. The dashboard binds only to loopback addresses; non-loopback hosts are rejected. Configure its local endpoint under the provider:

```yaml
dashboard:
  host: 127.0.0.1
  port: 9120
```

The **Irodori TTS** tab in Hermes is intentionally only a Start/Open/Stop launcher. The dashboard API can edit only explicitly allowlisted Irodori settings. Server commands, tokens, arbitrary prompts, and credentials remain read-only.

History excludes synthesis performed in the dashboard Playground. Retries remain part of one request record. When a 51st Hermes TTS request is recorded, the oldest request and its saved History audio are removed together; retention has no total-byte or age limit.

## Development

### Python tests

Run against the Python environment that owns Hermes dependencies:

```bash
PYTHONPATH=/path/to/hermes-agent \
  /path/to/hermes-agent/venv/bin/python -m unittest discover -s tests -v
```

### Dashboard tests and build

```bash
cd dashboard-ui
npm ci --include=dev
npm test
npm run build
```

The frontend build writes the distributable files directly to:

```text
dashboard/dist/index.js
dashboard/dist/style.css
standalone/dist/index.html
standalone/dist/assets/*
```

Commit these generated files so users do not need Node.js to install the plugin.

## Repository layout

```text
plugin.yaml                    Hermes plugin manifest
__init__.py                    TTS-provider and CLI registration
irodori_tts_*.py               synthesis, config, history, dictionary, metrics
irodori_tts_dashboard_server.py standalone server and safe process lifecycle
dashboard/manifest.json        Hermes launcher extension manifest
dashboard/plugin_api.py        launcher and shared dashboard API routes
dashboard/dist/                pre-built lightweight Hermes launcher
standalone/dist/               pre-built standalone dashboard
dashboard-ui/                  React/TypeScript source and tests
tests/                         Python behavior and integration tests
```

## Privacy and repository hygiene

The `.gitignore` excludes:

- model checkpoints and speaker embeddings
- reference and generated audio
- request/audio history
- local `.env` and config overrides
- Python caches and `node_modules`

Review `git status` before every release, especially if you use real voices or private text in local testing.

## Responsible voice use

Use only reference audio and speaker embeddings that you have the right to use, and obtain the speaker's explicit consent before cloning or imitating an identifiable person's voice. Do not use generated speech to impersonate someone, mislead others, or spread misinformation.

Generated audio is not automatically covered by this repository's MIT License. Its use may also depend on the input text, reference audio, speaker consent, model terms, and applicable law. Irodori's watermarking can depend on optional runtime assets, so this plugin does not claim that every output is watermarked.

## License

The code in this repository is released under the [MIT License](LICENSE).

This license does not cover external software, model weights, codecs, reference audio, speaker embeddings, or generated audio. They are not bundled and remain subject to their respective licenses, model cards, usage terms, and third-party rights:

- [Irodori-TTS](https://github.com/Aratako/Irodori-TTS) — upstream code and license
- [Irodori-TTS-Server](https://github.com/Aratako/Irodori-TTS-Server) — separately installed server code and license
- [Irodori-TTS-500M-v3](https://huggingface.co/Aratako/Irodori-TTS-500M-v3) — model card, license declaration, and ethical restrictions
- [Irodori-TTS-600M-v3-VoiceDesign](https://huggingface.co/Aratako/Irodori-TTS-600M-v3-VoiceDesign) — model card, license declaration, and ethical restrictions
- [Semantic-DACVAE-Japanese-32dim](https://huggingface.co/Aratako/Semantic-DACVAE-Japanese-32dim) — codec model card and license declaration

If upstream code or other third-party material is copied into a future release, preserve its copyright and license notices as required by that material's license.
