# Wi-Fi Monitor

Скрипт для мониторинга качества Wi-Fi подключения в Windows.

Проект предназначен для диагностики:
- состояния Wi-Fi подключения;
- качества сигнала;
- доступности интернета;
- задержек ping;
- потерь пакетов;
- проблем DNS;
- проблем hotspot / мобильного интернета;
- смены BSSID и канала Wi-Fi.

## Состав проекта

```text
wi-fi_
├── wifi_monitor.py
├── config.json
├── README.md
├── .gitignore
├── raw_netsh.txt
├── wifi_monitor_log.csv
├── wifi_monitor_diagnostics.csv
└── wifi_monitor_summary.csv