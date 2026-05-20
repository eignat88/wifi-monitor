from wifi_monitor import (
    parse_default_gateway_from_text,
    parse_ping_loss_from_text,
    parse_ping_time_from_text,
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
