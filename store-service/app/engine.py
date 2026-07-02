import os
import threading
import time
import json
from pathlib import Path
from base64 import b64encode, b64decode

DATA_DIR = Path('data')
DATA_DIR.mkdir(parents=True, exist_ok=True)
INDEX_FILE = DATA_DIR / 'index.json'

class StoreEngine:
    def __init__(self):
        self.volumes = {
            f"V{idx+1}": DATA_DIR / f"volume_{idx+1}.dat"
            for idx in range(int(os.getenv("NUM_VOLUMES", "2")))
        }

        self.index = {}
        if INDEX_FILE.exists():
            try:
                self.index = json.loads(INDEX_FILE.read_text())
            except:
                self.index = {}

        for vpath in self.volumes.values():
            vpath.touch(exist_ok=True)

        self.cache = {}
        self.cache_lock = threading.Lock()
        self.CACHE_LIMIT = 2000

        threading.Thread(target=self._compaction_scheduler, daemon=True).start()

    def _cache_get(self, photo_id):
        with self.cache_lock:
            return self.cache.get(photo_id)

    def _cache_set(self, photo_id, data_bytes):
        with self.cache_lock:
            if len(self.cache) >= self.CACHE_LIMIT:
                oldest = next(iter(self.cache))
                self.cache.pop(oldest, None)

            self.cache[photo_id] = data_bytes

    def _cache_delete(self, photo_id):
        with self.cache_lock:
            self.cache.pop(photo_id, None)

    def _persist_index(self):
        INDEX_FILE.write_text(json.dumps(self.index))

    def write(self, payload: dict):
        photo_id = payload["photo_id"]
        volume_id = payload["volume_id"]
        data = b64decode(payload["photo_data"])

        vpath = self.volumes.get(volume_id)
        if not vpath:
            return {"status": "error", "reason": "volume not found"}

        with vpath.open("ab") as f:
            offset = f.tell()
            f.write(len(data).to_bytes(8, "big"))
            f.write(data)

        self.index[photo_id] = {
            "volume": volume_id,
            "offset": offset,
            "size": len(data),
            "deleted": False
        }
        self._persist_index()

        self._cache_set(photo_id, data)

        return {"status": "success", "offset": offset, "size": len(data)}

    def read(self, photo_id: str):
        cached = self._cache_get(photo_id)
        if cached:
            return {
                "photo_id": photo_id,
                "volume_id": "cache",
                "data": b64encode(cached).decode()
            }

        entry = self.index.get(photo_id)
        if not entry or entry.get("deleted"):
            return None

        vpath = self.volumes.get(entry["volume"])
        if not vpath:
            return None

        with vpath.open("rb") as f:
            f.seek(entry["offset"])
            size = int.from_bytes(f.read(8), "big")
            data = f.read(size)

        self._cache_set(photo_id, data)

        return {
            "photo_id": photo_id,
            "volume_id": entry["volume"],
            "data": b64encode(data).decode()
        }

    def mark_deleted(self, photo_id: str):
        if photo_id in self.index:
            self.index[photo_id]["deleted"] = True
            self._persist_index()

        self._cache_delete(photo_id)

    def compact(self):
        for vol, path in self.volumes.items():
            tmp = path.with_suffix(".tmp")

            with tmp.open("wb") as out:
                for pid, meta in self.index.items():
                    if meta["deleted"]:
                        continue
                    if meta["volume"] != vol:
                        continue

                    with path.open("rb") as fin:
                        fin.seek(meta["offset"])
                        size = int.from_bytes(fin.read(8), "big")
                        data = fin.read(size)

                        new_offset = out.tell()
                        out.write(len(data).to_bytes(8, "big"))
                        out.write(data)

                        self.index[pid]["offset"] = new_offset

            tmp.replace(path)

        self._persist_index()

    def _compaction_scheduler(self):
        while True:
            time.sleep(60)
            try:
                self.compact()
            except:
                pass