"""Збереження стану на диску (DATA_DIR): користувачі бота і стан мережі."""
import json
import logging
from collections.abc import Iterator
from contextlib import suppress
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


def write_json_atomic(path: Path, data: Any) -> None:
    """Атомарний запис: файл не зіпсується, якщо процес впаде посеред запису."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    tmp.replace(path)


class UserStore:
    """Користувачі бота: chat_id → ім'я."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._names: dict[str, str] = json.loads(path.read_text()) if path.exists() else {}

    def __contains__(self, chat_id: object) -> bool:
        return chat_id in self._names

    def __len__(self) -> int:
        return len(self._names)

    def __iter__(self) -> Iterator[tuple[str, str]]:
        """Пари (chat_id, ім'я); знімок — безпечно змінювати сховище під час ітерації."""
        return iter(list(self._names.items()))

    def name(self, chat_id: str, default: str = "") -> str:
        return self._names.get(chat_id, default)

    def add(self, chat_id: str, name: str) -> None:
        self._names[chat_id] = name
        self._save()

    def remove(self, chat_id: str) -> str | None:
        name = self._names.pop(chat_id, None)
        self._save()
        return name

    def _save(self) -> None:
        write_json_atomic(self._path, self._names)


@dataclass(frozen=True)
class GridState:
    grid_on: bool
    since: float  # unix-час, з якого мережа в цьому стані


class GridStateStore:
    """Останній відомий стан мережі — щоб після перезапуску знати, як довго він триває."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> GridState | None:
        with suppress(OSError, ValueError, KeyError, TypeError):
            data = json.loads(self._path.read_text())
            return GridState(grid_on=bool(data["grid_on"]), since=float(data["since"]))
        return None

    def save(self, state: GridState) -> None:
        try:
            write_json_atomic(self._path, asdict(state))
        except OSError as e:
            log.warning("! не вдалося зберегти стан мережі: %s", e)
