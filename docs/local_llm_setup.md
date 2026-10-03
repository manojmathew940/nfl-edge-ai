# Local LLM Setup

## Ollama

Install Ollama, download a model, and start it:

```bash
ollama run qwen2.5:7b-instruct
```

Exit the chat with `/bye`, then make sure the Ollama server is running:

```bash
ollama serve
```

Configure the app's local provider in `.env`:

```text
LOCAL_LLM_BASE_URL=http://127.0.0.1:11434/v1
LOCAL_LLM_MODEL=qwen2.5:7b-instruct
LOCAL_LLM_API_KEY=ollama
```

`LOCAL_LLM_API_KEY` is a placeholder. Ollama does not require a real API key,
but the OpenAI-compatible client expects a value.

## Context Length

The data extraction prompt includes every approved schema guide and is larger
than Ollama's default 4096-token context. Ollama silently truncates the start
of longer prompts, which drops the instructions. Raise the context before
starting the server:

```bash
OLLAMA_CONTEXT_LENGTH=16384 ollama serve
```

On Windows, set `OLLAMA_CONTEXT_LENGTH` as a user environment variable and
restart the Ollama application. Alternatively, set `PARAMETER num_ctx 16384`
in a Modelfile. The OpenAI-compatible endpoint ignores per-request `num_ctx`.
The Ollama server log warns when a prompt is truncated.

## Ollama On Windows With The App In WSL

The preferred setup is WSL mirrored networking so Windows and WSL share
`localhost`.

1. Create or edit `%UserProfile%\.wslconfig`:

   ```ini
   [wsl2]
   networkingMode=mirrored
   ```

2. Restart WSL from PowerShell:

   ```powershell
   wsl --shutdown
   ```

3. Start Ollama from Windows and use the normal local endpoint in `.env`:

   ```text
   LOCAL_LLM_BASE_URL=http://127.0.0.1:11434/v1
   LOCAL_LLM_MODEL=qwen2.5:7b-instruct
   LOCAL_LLM_API_KEY=ollama
   ```

If mirrored networking is unavailable, use WSL's default NAT mode:

1. Set this persistent Windows user environment variable:

   ```text
   OLLAMA_HOST=0.0.0.0:11434
   ```

2. Restart the Ollama Windows application.
3. Find the Windows host IP from WSL:

   ```bash
   ip route show | grep -i default | awk '{ print $3 }'
   ```

4. Use that address in `.env`, for example:

   ```text
   LOCAL_LLM_BASE_URL=http://172.30.96.1:11434/v1
   ```

The NAT-mode host IP can change after WSL restarts, so mirrored networking is
more stable when it is available.
