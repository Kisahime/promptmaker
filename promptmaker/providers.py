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
        return sort_models([m for m in self.list_models() if looks_vision(m)])

    def capabilities(self, model):
        """List of capabilities ("vision", ...) or None when the backend can't tell."""
        return None

    def has_vision(self, model):
        caps = self.capabilities(model)
        return looks_vision(model) if caps is None else "vision" in caps

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

    def version(self):
        """Ollama server version string (e.g. "0.30.1"), or "" if unknown."""
        try:
            with _req(self.base_url + "/api/version", timeout=3) as r:
                return str(json.load(r).get("version", ""))
        except (ProviderError, ValueError):
            return ""

    def capabilities(self, model):
        """Ollama /api/show capabilities, cached per model (None if unknown)."""
        cache = self.__dict__.setdefault("_caps", {})
        if model not in cache:
            try:
                with _req(self.base_url + "/api/show", {"model": model}, timeout=5) as r:
                    caps = json.load(r).get("capabilities")
            except (ProviderError, ValueError, AttributeError):
                return None  # not cached: Ollama may just be down
            cache[model] = list(caps) if isinstance(caps, list) else None
        return cache[model]

    def vision_models(self):
        """Vision-capable models, preferred first; models this Ollama can't run are listed last and
        explained in self.notes {model: reason}."""
        out, archs = [], {}
        for m in self.list_models():
            caps = []
            try:
                with _req(self.base_url + "/api/show", {"model": m}, timeout=5) as r:
                    d = json.load(r)
                caps = d.get("capabilities") or []
                self.__dict__.setdefault("_caps", {})[m] = list(caps) if d.get("capabilities") is not None else None
                archs[m] = str((d.get("model_info") or {}).get("general.architecture") or d.get("details", {}).get("family") or "")
            except (ProviderError, ValueError, AttributeError):
                pass
            if "vision" in caps or (not caps and looks_vision(m)):
                out.append(m)
        ver = self.version()
        self.notes = {m: r for m in out if (r := unsupported_reason(m, ver, archs.get(m, "")))}
        return sort_models(out, failed=self.notes)

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


# ---------------------------------------------------------------- model load failures
# Ollama (llama-server) reports models it can't run with messages such as
#   "llama-server process has terminated: exit status 1: error loading model: unknown model architecture: 'mllama'"
LOAD_FAIL_PATTERNS = ("unknown model architecture", "error loading model", "process has terminated",
                      "llama runner process has terminated", "failed to load model", "unable to load model",
                      "model architecture not supported", "unsupported model architecture")
VISION_PREFERENCE = ("qwen2.5vl", "qwen2.5-vl", "qwen3-vl", "qwen3vl", "gemma3", "llava", "minicpm-v", "llama4",
                     "mistral-small3", "granite3.2-vision", "moondream", "bakllava", "llama3.2-vision")
CHAT_PREFERENCE = ("qwen2.5", "qwen3", "llama3.2", "llama3.1", "gemma3", "mistral", "phi4")
VISION_PULL = "ollama pull qwen2.5vl"
CHAT_PULL = "ollama pull llama3.2"


def is_model_load_error(msg):
    m = str(msg).lower()
    return any(p in m for p in LOAD_FAIL_PATTERNS)


def load_error_detail(msg):
    """Short reason, e.g. "unknown model architecture: 'mllama'"."""
    m = str(msg)
    low = m.lower()
    for key in ("unknown model architecture", "error loading model", "failed to load model"):
        i = low.find(key)
        if i >= 0:
            return m[i:].split('"')[0].strip().rstrip("}").strip()[:160]
    return m[:160]


def _rank(name, prefs):
    n = name.lower()
    for i, p in enumerate(prefs):
        if p in n:
            return i
    return len(prefs)


def sort_models(models, prefs=VISION_PREFERENCE, failed=()):
    """Preferred families first, models that failed to load last; stable otherwise."""
    failed = set(failed)
    return sorted(models, key=lambda m: (m in failed, _rank(m, prefs)))


def pick_alternative(models, bad, prefs=VISION_PREFERENCE, failed=()):
    skip = set(failed) | {bad}
    for m in sort_models(models, prefs, failed):
        if m not in skip:
            return m
    return None


MLLAMA_NOTE = "Not supported on Ollama 0.30+ (llama.cpp engine has no mllama support, see ollama/ollama#16547)"


def _vtuple(v):
    import re
    nums = [int(x) for x in re.findall(r"\d+", str(v))[:3]]
    return tuple(nums + [0] * (3 - len(nums))) if nums else None


def is_mllama(model, arch=""):
    n = model.lower()
    return "mllama" in str(arch).lower() or "llama3.2-vision" in n or "llama-3.2-vision" in n


def unsupported_reason(model, ollama_version, arch=""):
    v = _vtuple(ollama_version)
    if v and v >= (0, 30, 0) and is_mllama(model, arch):
        return MLLAMA_NOTE
    return ""


def friendly_load_error(model, msg, vision=False, ollama_kind=True):
    what = "vision model" if vision else "model"
    extra = ""
    if is_mllama(model, "mllama" if "mllama" in str(msg).lower() else ""):
        extra = (" Llama 3.2 Vision (architecture 'mllama') is not supported on Ollama 0.30+ – the llama.cpp engine "
                 "has no mllama support (see ollama/ollama#16547); use qwen2.5vl or qwen3-vl instead.")
    return extra and (f"The {what} “{model}” can't run on this Ollama version ({load_error_detail(msg)}). Re-pulling won't fix this."
                      + extra) or (f"The {what} “{model}” can't run on this {'Ollama' if ollama_kind else 'server'} version "
            f"({load_error_detail(msg)}). Re-pulling won't fix this. Try another {what}"
            + (", or update Ollama from ollama.com/download." if ollama_kind else "."))


NO_VISION_MSG = "No vision model installed – images need one. Run `" + VISION_PULL + "` and try again."


def resolve_vision(provider, preferred="", failed=()):
    """Model to send images to: (model, note). Uses `preferred` when it really has the vision
    capability, else auto-picks an installed vision model; ("", NO_VISION_MSG) if there is none."""
    preferred = (preferred or "").strip()
    try:
        has = getattr(provider, "has_vision", looks_vision)
        if preferred and preferred not in failed and has(preferred):
            return preferred, ""
        vm = getattr(provider, "vision_models", None)
        models = [m for m in (vm() if vm else sort_models([m for m in provider.list_models() if looks_vision(m)]))
                  if m not in failed and m not in (getattr(provider, "notes", {}) or {})]
    except ProviderError as e:
        return "", str(e)
    if not models:
        return "", NO_VISION_MSG + (f" ({preferred} can't read images.)" if preferred else "")
    pick = models[0]
    return pick, (f"{preferred} can't read images – using {pick}" if preferred else f"Using vision model {pick}")
