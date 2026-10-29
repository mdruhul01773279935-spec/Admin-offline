"""Tiny JSON-file state store (no database needed)."""
import json
import time
from pathlib import Path


class State:
    """Persistent state: owner binding, connections, per-chat memory."""

    def __init__(self, path: Path, max_history: int = 12) -> None:
        self.path = Path(path)
        self.max_history = max_history
        self.data = {
            "owner_id": 0,
            "away_enabled": True,
            "last_heartbeat": 0.0,
            "connections": {},
            "chats": {},
        }
        if self.path.exists():
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                self.data.update(loaded)
            except (json.JSONDecodeError, OSError):
                # Corrupted state: keep a backup and start fresh.
                backup = self.path.with_suffix(".json.bak")
                try:
                    self.path.replace(backup)
                except OSError:
                    pass

    # ---- owner -------------------------------------------------------
    @property
    def owner_id(self) -> int:
        return int(self.data.get("owner_id", 0))

    @owner_id.setter
    def owner_id(self, value: int) -> None:
        self.data["owner_id"] = int(value)

    # ---- per-chat memory --------------------------------------------
    def chat(self, chat_id) -> dict:
        chats = self.data.setdefault("chats", {})
        key = str(chat_id)
        if key not in chats:
            chats[key] = {"last_owner_msg": 0.0, "last_auto_reply": 0.0, "history": []}
        return chats[key]

    def add_history(self, chat_id, role: str, text: str) -> None:
        entry = self.chat(chat_id).setdefault("history", [])
        entry.append([role, (text or "")[:400]])
        if len(entry) > self.max_history:
            del entry[: len(entry) - self.max_history]

    def history(self, chat_id):
        return list(self.chat(chat_id).get("history", []))

    def note_owner_msg(self, chat_id, ts: float = None) -> None:
        self.chat(chat_id)["last_owner_msg"] = ts or time.time()

    def note_auto_reply(self, chat_id, ts: float = None) -> None:
        self.chat(chat_id)["last_auto_reply"] = ts or time.time()

    def note_heartbeat(self, ts: float = None) -> None:
        """Record that the phone (and its internet) was alive at `ts`."""
        self.data["last_heartbeat"] = float(ts or time.time())

    # ---- persistence -------------------------------------------------
    def save(self) -> None:
        tmp = self.path.with_suffix(".json.tmp")
        try:
            tmp.write_text(
                json.dumps(self.data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp.replace(self.path)
        except OSError:
            pass
