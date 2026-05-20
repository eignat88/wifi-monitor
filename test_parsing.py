from wifi_monitor import (
    parse_default_gateway_from_text,
    parse_ping_loss_from_text,
    parse_ping_time_from_text,
    ping_target,
)


IPCONFIG_EN_GATEWAY_NEXT_LINE = """
Windows IP Configuration

Ethernet adapter Ethernet:

   Connection-specific DNS Suffix  . :
   Link-local IPv6 Address . . . . . : fe80::1
   IPv4 Address. . . . . . . . . . . : 192.168.1.22
   Subnet Mask . . . . . . . . . . . : 255.255.255.0
   Default Gateway . . . . . . . . . :
                                       192.168.1.1
"""

IPCONFIG_RU_GATEWAY_SAME_LINE = """
Настройка протокола IP для Windows

Адаптер Ethernet Ethernet:

   DNS-суффикс подключения . . . . . :
   IPv4-адрес. . . . . . . . . . . . : 10.10.10.55
   Маска подсети . . . . . . . . . . : 255.255.255.0
   Основной шлюз. . . . . . . . . : 10.10.10.1
"""

PING_EN = """
Pinging 8.8.8.8 with 32 bytes of data:
Reply from 8.8.8.8: bytes=32 time=22ms TTL=117

Ping statistics for 8.8.8.8:
    Packets: Sent = 1, Received = 1, Lost = 0 (0% loss),
"""

PING_RU = """
Обмен пакетами с 8.8.8.8 по с 32 байтами данных:
Ответ от 8.8.8.8: число байт=32 время<1мс TTL=117

Статистика Ping для 8.8.8.8:
    Пакетов: отправлено = 1, получено = 1, потеряно = 0 (0% потерь),
"""


def test_parse_default_gateway_next_line_en() -> None:
    assert parse_default_gateway_from_text(IPCONFIG_EN_GATEWAY_NEXT_LINE) == "192.168.1.1"


def test_parse_default_gateway_same_line_ru() -> None:
    assert parse_default_gateway_from_text(IPCONFIG_RU_GATEWAY_SAME_LINE) == "10.10.10.1"


def test_parse_ping_en() -> None:
    assert parse_ping_loss_from_text(PING_EN) == 0
    assert parse_ping_time_from_text(PING_EN) == 22


def test_parse_ping_ru() -> None:
    assert parse_ping_loss_from_text(PING_RU) == 0
    assert parse_ping_time_from_text(PING_RU) == 1


PING_EN_SPACED = """
Reply from 8.8.8.8: bytes=32 time = 23 ms TTL=117
"""


PING_EN_LT = """
Reply from 8.8.8.8: bytes=32 time<1ms TTL=117
"""


PING_RU_SPACED = """
Ответ от 8.8.8.8: число байт=32 время = 7 мс TTL=117
"""


def test_parse_ping_time_variants() -> None:
    assert parse_ping_time_from_text(PING_EN_SPACED) == 23
    assert parse_ping_time_from_text(PING_EN_LT) == 1
    assert parse_ping_time_from_text(PING_RU_SPACED) == 7


def test_ping_success_without_ttl(monkeypatch) -> None:
    ping_without_ttl = """
Pinging 8.8.8.8 with 32 bytes of data:
Reply from 8.8.8.8: bytes=32 time=22ms

Ping statistics for 8.8.8.8:
    Packets: Sent = 1, Received = 1, Lost = 0 (0% loss),
"""

    def fake_run_command(command: list[str], timeout: int = 5):
        return True, ping_without_ttl, ""

    monkeypatch.setattr("wifi_monitor.run_command", fake_run_command)
    result = ping_target("8.8.8.8")

    assert result["ping_status"] == "OK"
    assert result["latency_ms"] == 22
    assert result["packet_loss_percent"] == 0
