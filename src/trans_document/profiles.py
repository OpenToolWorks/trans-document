"""Local API connection metadata. API keys are deliberately never persisted."""

import json
import os
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


@dataclass(frozen=True)
class ProviderProfile:
    id: str
    name: str
    provider: str
    base_url: str
    model: str
    key_slot: str


@dataclass(frozen=True)
class ProfileCatalog:
    profiles: tuple[ProviderProfile, ...]
    default_id: str | None


def profile_store_path():
    app_data = os.environ.get("LOCALAPPDATA")
    root = Path(app_data) / "TransDocument" if app_data else Path.home() / ".transdocument"
    return root / "profiles.json"


def validate_base_url(value):
    url = urlsplit(value.strip())
    try:
        valid_port = url.port is None or 1 <= url.port <= 65535
    except ValueError:
        valid_port = False
    if (url.scheme not in {"http", "https"} or not url.hostname or not valid_port
            or url.username or url.password or url.query or url.fragment):
        raise ValueError("Base URL phải là HTTP/HTTPS hợp lệ, không chứa key, query hoặc fragment.")


class ProfileStore:
    def __init__(self, path):
        self.path = Path(path)
        self._lock = threading.RLock()

    def read(self):
        with self._lock:
            if not self.path.exists():
                catalog = ProfileCatalog((
                    ProviderProfile(uuid.uuid4().hex, "Gemini cá nhân", "gemini",
                                    "https://generativelanguage.googleapis.com/v1beta/openai/",
                                    "gemini-3.1-flash-lite", uuid.uuid4().hex),
                    ProviderProfile(uuid.uuid4().hex, "OpenAI", "openai",
                                    "https://api.openai.com/v1/", "gpt-4.1-mini", uuid.uuid4().hex),
                ), None)
                catalog = ProfileCatalog(catalog.profiles, catalog.profiles[0].id)
                self._write(catalog)
                return catalog
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if data.get("version") != 1 or not isinstance(data.get("profiles"), list):
                    raise ValueError
                profiles = tuple(ProviderProfile(**item) for item in data["profiles"])
                ids = [profile.id for profile in profiles]
                key_slots = [profile.key_slot for profile in profiles]
                if (len(ids) != len(set(ids)) or len(key_slots) != len(set(key_slots)) or not all(
                    isinstance(value, str) for profile in profiles
                    for value in (profile.id, profile.name, profile.provider, profile.base_url,
                                  profile.model, profile.key_slot)
                )):
                    raise ValueError
                default_id = data.get("default_id")
                if default_id is not None and default_id not in ids:
                    raise ValueError
                for profile in profiles:
                    if profile.provider not in {"gemini", "openai", "custom"}:
                        raise ValueError
                    validate_base_url(profile.base_url)
                    if not profile.name.strip() or not profile.model.strip():
                        raise ValueError
                return ProfileCatalog(profiles, default_id)
            except (OSError, TypeError, KeyError, AttributeError, json.JSONDecodeError, ValueError):
                raise ValueError(f"Không đọc được cấu hình API tại {self.path}. Hãy khôi phục hoặc đổi tên file này.") from None

    def save(self, *, profile_id, name, provider, base_url, model):
        with self._lock:
            catalog = self.read()
            if not isinstance(name, str) or not name.strip() or not isinstance(model, str) or not model.strip():
                raise ValueError("Nhập tên kết nối và model.")
            if provider not in {"gemini", "openai", "custom"}:
                raise ValueError("Dịch vụ API không hợp lệ.")
            validate_base_url(base_url)
            existing = next((profile for profile in catalog.profiles if profile.id == profile_id), None)
            if profile_id is not None and existing is None:
                raise ValueError("Kết nối đã thay đổi trong tab khác. Tải lại danh sách rồi thử lại.")
            profile = ProviderProfile(
                existing.id if existing else uuid.uuid4().hex, name.strip(), provider,
                base_url.strip(), model.strip(),
                uuid.uuid4().hex if existing is None or existing.base_url != base_url.strip()
                else existing.key_slot,
            )
            profiles = tuple(profile if item.id == profile.id else item for item in catalog.profiles)
            if existing is None:
                profiles += (profile,)
            self._write(ProfileCatalog(profiles, catalog.default_id or profile.id))
            return profile

    def set_default(self, profile_id):
        with self._lock:
            catalog = self.read()
            if not any(profile.id == profile_id for profile in catalog.profiles):
                raise ValueError("Kết nối đã bị xóa. Tải lại danh sách rồi thử lại.")
            self._write(ProfileCatalog(catalog.profiles, profile_id))

    def delete(self, profile_id):
        with self._lock:
            catalog = self.read()
            profiles = tuple(profile for profile in catalog.profiles if profile.id != profile_id)
            if len(profiles) == len(catalog.profiles):
                raise ValueError("Kết nối đã bị xóa. Tải lại danh sách rồi thử lại.")
            default_id = catalog.default_id
            if default_id == profile_id:
                default_id = profiles[0].id if profiles else None
            self._write(ProfileCatalog(profiles, default_id))

    def _write(self, catalog):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f"{self.path.name}.{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_text(json.dumps({
                "version": 1,
                "default_id": catalog.default_id,
                "profiles": [profile.__dict__ for profile in catalog.profiles],
            }, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)
