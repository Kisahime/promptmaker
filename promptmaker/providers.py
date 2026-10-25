"""AI provider abstraction: Ollama, OpenAI-compatible local servers, and optional cloud APIs.

Every provider exposes list_models(), stream_chat(...) and vision_models(). Messages use the
common {"role", "content", optional "images": [base64 PNG/JPEG]} shape and are converted per API.
"""
import json
import urllib.error
import urllib.request

from .ollama import INSTALL_HINT, OllamaError

VISION_HINTS = ("llava", "vision", "-vl", "vl:", "qwen2.5vl", "qwen2.5-vl", "qwen3-vl", "gemma3", "minicpm-v",
                "moondream", "bakllava", "pixtral", "llama4", "mistral-small3", "granite3.2-vision", "gpt-4o",
                "gpt-4.1", "gpt-5", "claude", "gemini", "internvl")

PRESETS = {
    "ollama": {"label": "Ollama (local)", "kind": "ollama", "base_url": "http://localhost:11434", "key": False},
    "lmstudio": {"label": "LM Studio (local)", "kind": "openai", "base_url": "http://localhost:1234/v1", "key": False},
    "llamacpp": {"label": "llama.cpp server (local)", "kind": "openai", "base_url": "http://localhost:8080/v1", "key": False},
    "koboldcpp": {"label": "KoboldCpp (local)", "kind": "openai", "base_url": "http://localhost:5001/v1", "key": False},
    "vllm": {"label": "vLLM (local)", "kind": "openai", "base_url": "http://localhost:8000/v1", "key": False},
    "openai_compat": {"label": "Other OpenAI-compatible", "kind": "openai", "base_url": "http://localhost:8000/v1", "key": "optional"},
    "openai": {"label": "OpenAI (cloud)", "kind": "openai", "base_url": "https://api.openai.com/v1", "key": True},
    "openrouter": {"label": "OpenRouter (cloud)", "kind": "openai", "base_url": "https://openrouter.ai/api/v1", "key": True},
    "anthropic": {"label": "Anthropic Claude (cloud)", "kind": "anthropic", "base_url": "https://api.anthropic.com/v1", "key": True},
    "gemini": {"label": "Google Gemini (cloud)", "kind": "gemini", "base_url": "https://generativelanguage.googleapis.com/v1beta", "key": True},
}


class ProviderError(OllamaError):
    pass


def _req(url, data=None, headers=None, timeout=600, method=None):
    h = {"Content-Type": "application/json", "User-Agent": "PromptMaker"}
    h.update(headers or {})
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers=h, method=method)
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="ignore")[:400]
        raise ProviderError(f"HTTP {e.code} from {url.split('?')[0]}: {detail}") from e
    except (urllib.error.URLError, OSError) as e:
        raise ProviderError(f"Can't reach {url.split('?')[0]} – is the server running? ({e})") from e


def _sse(resp, stop_flag=None):
    """Yield parsed JSON payloads from a server-sent-events stream."""
    for raw in resp:
        if stop_flag and stop_flag():
            break
        line = raw.decode("utf-8", "ignore").strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            break
        try:
            yield json.loads(payload)
        except ValueError:
            continue


def looks_vision(name):
    n = name.lower()
    return any(h in n for h in VISION_HINTS)


class Provider:
    kind = "base"

    def __init__(self, base_url, api_key="", pid=""):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or ""
        self.pid = pid

    def list_models(self):
        raise NotImplementedError

    def vision_models(self):
        return [m for m in self.list_models() if looks_vision(m)]

    def stream_chat(self, model, messages, temperature=0.7, json_mode=False, stop_flag=None):
        raise NotImplementedError

    def test(self):
        models = self.list_models()
        return f"Connected – {len(models)} model(s)"


class OllamaProvider(Provider):
    kind = "ollama"

    def list_models(self):
        try:
            with _req(self.base_url + "/api/tags", timeout=4) as r:
                return [m["name"] for m in json.load(r).get("models", [])]
        except ProviderError as e:
            raise ProviderError(INSTALL_HINT) from e

    def vision_models(self):
        out = []
        for m in self.list_models():
            caps = []
            try:
                with _req(self.base_url + "/api/show", {"model": m}, timeout=5) as r:
                    caps = json.load(r).get("capabilities") or []
            except (ProviderError, ValueError):
                pass
            if "vision" in caps or (not caps and looks_vision(m)):
                out.append(m)
        return out

    def stream_chat(self, model, messages, temperature=0.7, json_mode=False, stop_flag=None):
        payload = {"model": model, "messages": messages, "stream": True, "options": {"temperature": temperature}}
        if json_mode:
            payload["format"] = "json"
        with _req(self.base_url + "/api/chat", payload) as resp:
            for line in resp:
                if stop_flag and stop_flag():
                    break
                if not line.strip():
                    continue
                d = json.loads(line)
                if d.get("error"):
                    raise ProviderError(d["error"])
                yield d.get("message", {}).get("content", "")
                if d.get("done"):
                    break


def _openai_messages(messages):
    out = []
    for m in messages:
        if m.get("images"):
            parts = [{"type": "text", "text": m["content"]}]
            parts += [{"type": "image_url", "image_url": {"url": "data:image/png;base64," + b}} for b in m["images"]]
            out.append({"role": m["role"], "content": parts})
        else:
            out.append({"role": m["role"], "content": m["content"]})
    return out


class OpenAIProvider(Provider):
    kind = "openai"

    def _headers(self):
        h = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        if "openrouter.ai" in self.base_url:
            h.update({"HTTP-Referer": "https://github.com/Kisahime/promptmaker", "X-Title": "PromptMaker"})
        return h

    def list_models(self):
        with _req(self.base_url + "/models", headers=self._headers(), timeout=8) as r:
            data = json.load(r)
        return sorted(m.get("id", "") for m in data.get("data", []) if m.get("id"))

    def stream_chat(self, model, messages, temperature=0.7, json_mode=False, stop_flag=None):
        payload = {"model": model, "messages": _openai_messages(messages), "stream": True, "temperature": temperature}
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        with _req(self.base_url + "/chat/completions", payload, self._headers()) as resp:
            for d in _sse(resp, stop_flag):
                if d.get("error"):
                    raise ProviderError(str(d["error"]))
                for ch in d.get("choices", []):
                    txt = (ch.get("delta") or {}).get("content")
                    if txt:
                        yield txt


class AnthropicProvider(Provider):
    kind = "anthropic"

    def _headers(self):
        return {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"}

    def list_models(self):
        with _req(self.base_url + "/models", headers=self._headers(), timeout=8) as r:
            return [m["id"] for m in json.load(r).get("data", [])]

    @staticmethod
    def convert(messages, json_mode=False):
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        if json_mode:
            system += "\n\nRespond with a single JSON object only."
        msgs = []
        for m in messages:
            if m["role"] == "system":
                continue
            if m.get("images"):
                content = [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b}}
                           for b in m["images"]] + [{"type": "text", "text": m["content"]}]
            else:
                content = m["content"]
            msgs.append({"role": m["role"], "content": content})
        return system, msgs

    def stream_chat(self, model, messages, temperature=0.7, json_mode=False, stop_flag=None):
        system, msgs = self.convert(messages, json_mode)
        payload = {"model": model, "max_tokens": 2048, "messages": msgs, "stream": True,
                   "temperature": min(1.0, temperature)}
        if system:
            payload["system"] = system
        with _req(self.base_url + "/messages", payload, self._headers()) as resp:
            for d in _sse(resp, stop_flag):
                if d.get("type") == "error":
                    raise ProviderError(str(d.get("error")))
                if d.get("type") == "content_block_delta":
                    txt = (d.get("delta") or {}).get("text")
                    if txt:
                        yield txt


class GeminiProvider(Provider):
    kind = "gemini"

    def _headers(self):
        return {"x-goog-api-key": self.api_key}

    def list_models(self):
        with _req(self.base_url + "/models", headers=self._headers(), timeout=8) as r:
            data = json.load(r)
        return [m["name"].split("/", 1)[-1] for m in data.get("models", [])
                if "generateContent" in m.get("supportedGenerationMethods", [])]

    @staticmethod
    def convert(messages):
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        contents = []
        for m in messages:
            if m["role"] == "system":
                continue
            parts = [{"inline_data": {"mime_type": "image/png", "data": b}} for b in m.get("images", [])]
            parts.append({"text": m["content"]})
            contents.append({"role": "model" if m["role"] == "assistant" else "user", "parts": parts})
        return system, contents

    def stream_chat(self, model, messages, temperature=0.7, json_mode=False, stop_flag=None):
        system, contents = self.convert(messages)
        payload = {"contents": contents, "generationConfig": {"temperature": temperature}}
        if json_mode:
            payload["generationConfig"]["responseMimeType"] = "application/json"
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        url = f"{self.base_url}/models/{model}:streamGenerateContent?alt=sse"
        with _req(url, payload, self._headers()) as resp:
            for d in _sse(resp, stop_flag):
                for c in d.get("candidates", []):
                    for p in (c.get("content") or {}).get("parts", []):
                        if p.get("text"):
                            yield p["text"]


KINDS = {"ollama": OllamaProvider, "openai": OpenAIProvider, "anthropic": AnthropicProvider, "gemini": GeminiProvider}


def make(pid, base_url=None, api_key=""):
    preset = PRESETS.get(pid, PRESETS["ollama"])
    return KINDS[preset["kind"]](base_url or preset["base_url"], api_key, pid)
