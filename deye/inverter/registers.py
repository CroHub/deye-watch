"""Карта регістрів Deye SUN-5K-SG03LP1 і перетворення їх у Reading."""
from collections.abc import Iterator
from typing import Protocol

from deye.model import Reading

_BLOCK_A = (59, 33)  # регістри 59..91
_BLOCK_B = (150, 45)  # регістри 150..194
_DUMP_CHUNK = 40  # більше за раз логер не віддає надійно


class ModbusClient(Protocol):
    """Те, що нам потрібно від PySolarmanV5 (і що легко підмінити в тестах)."""

    def read_holding_registers(self, register_addr: int, quantity: int) -> list[int]: ...

    def disconnect(self) -> None: ...


def s16(v: int) -> int:
    """Беззнакове 16-бітне значення регістра → знакове."""
    return v - 65536 if v > 32767 else v


def temperature(v: int) -> float:
    """Температура в регістрах Deye зберігається як (°C × 10) + 1000."""
    return (v - 1000) / 10


class _Block:
    def __init__(self, client: ModbusClient, start: int, count: int) -> None:
        self._start = start
        self._values = client.read_holding_registers(start, count)

    def __getitem__(self, register: int) -> int:
        return self._values[register - self._start]


def read_reading(client: ModbusClient) -> Reading:
    a = _Block(client, *_BLOCK_A)
    b = _Block(client, *_BLOCK_B)
    return Reading(
        state=a[59],
        grid_on=b[194] == 1,
        grid_v=b[150] / 10,
        grid_hz=b[192] / 100,
        grid_w=b[169],
        grid_a=b[160] / 100,
        load_w=b[178],
        load_v=b[157] / 10,
        inv_w=s16(b[175]),
        soc=b[184],
        batt_v=b[183] / 100,
        batt_a=s16(b[191]) / 100,
        batt_w=s16(b[190]),
        batt_t=temperature(b[182]),
        t_heat=temperature(a[91]),
        t_trans=temperature(a[90]),
        day_chg=a[70] / 10,
        day_dis=a[71] / 10,
        day_buy=a[76] / 10,
        day_load=a[84] / 10,
    )


def dump_registers(client: ModbusClient, start: int, end: int) -> Iterator[tuple[int, int]]:
    """Сирі регістри start..end включно як пари (адреса, значення)."""
    for base in range(start, end + 1, _DUMP_CHUNK):
        values = client.read_holding_registers(base, min(_DUMP_CHUNK, end - base + 1))
        yield from enumerate(values, start=base)
