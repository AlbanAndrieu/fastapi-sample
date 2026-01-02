## Usage

You can run the Worker defined by your new project by executing `wrangler dev` in this
directory. This will start up an HTTP server and will allow you to iterate on your
Worker without having to restart `wrangler`.

### Types and autocomplete

This project also includes a pyproject.toml and uv.lock file with some requirements which
set up autocomplete and type hints for this Python Workers project.

To get these installed you'll need `uv`, which you can install by following
https://docs.astral.sh/uv/getting-started/installation/.

Once `uv` is installed, you can run the following:

```
uv tool install workers-py
# uv tool install workers-runtime-sdk
uv run pywrangler init

uv init

uv venv
uv sync
uv run pywrangler dev
```

Then point your editor's Python plugin at the `.venv` directory. You should then have working
autocomplete and type information in your editor.

[examples](https://developers.cloudflare.com/workers/languages/python/examples/)

[python-workers-examples](https://github.com/cloudflare/python-workers-examples)

[cloudflare-workers-and-pages](https://github.com/apps/cloudflare-workers-and-pages)

# Turnstile demo

## Setup

https://github.com/cloudflare/turnstile-demo-workers

```
npm install
npx wrangler dev
# npm run dev
```
