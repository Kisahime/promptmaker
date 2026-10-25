"""Gallery: images saved as PNG with a JSON sidecar of metadata under data/gallery."""
import json
import os
import time


class Gallery:
    def __init__(self, root):
        self.root = root
        os.makedirs(root, exist_ok=True)

    def save(self, image_bytes, meta):
        stamp = time.strftime("%Y%m%d-%H%M%S")
        base = f"{stamp}_{meta.get('seed', 0)}"
        n = 1
        while os.path.exists(os.path.join(self.root, base + ".png")):
            n += 1
            base = f"{stamp}_{meta.get('seed', 0)}_{n}"
        path = os.path.join(self.root, base + ".png")
        with open(path, "wb") as f:
            f.write(image_bytes)
        meta = dict(meta, file=os.path.basename(path), saved=time.time())
        with open(path[:-4] + ".json", "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=1, ensure_ascii=False)
        return path

    def items(self):
        out = []
        for fn in sorted(os.listdir(self.root), reverse=True):
            if fn.lower().endswith(".png"):
                p = os.path.join(self.root, fn)
                meta = {}
                try:
                    with open(p[:-4] + ".json", encoding="utf-8") as f:
                        meta = json.load(f)
                except (OSError, ValueError):
                    pass
                out.append((p, meta))
        return out

    def delete(self, path):
        for p in (path, path[:-4] + ".json"):
            if os.path.exists(p):
                os.remove(p)
