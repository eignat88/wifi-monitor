# Wi-Fi Monitor

Скрипт для мониторинга качества Wi-Fi подключения в Windows.

## Назначение

Скрипт помогает диагностировать:
- состояние Wi‑Fi подключения;
- качество сигнала;
- доступность интернета;
- задержки и потери ping;
- проблемы DNS;
- смену BSSID и канала Wi‑Fi.

## Пример `config.json`

```json
{
  "check_interval_sec": 1,
  "ping_targets": ["8.8.8.8", "1.1.1.1"],
  "latency_threshold_ms": 1000,
  "failures_before_outage": 3,
  "log_format": "csv",
  "log_file": "wifi_monitor_log.csv",
  "summary_interval_sec": 300,
  "summary_log_file": "wifi_monitor_summary.csv",
  "diagnostic_log_file": "wifi_monitor_diagnostics.csv",
  "ping_series_count": 5,
  "write_raw_netsh": false,
  "raw_netsh_rotation_dir": "netsh_dumps",
  "raw_netsh_rotation_keep": 10
}
```

## Параметры debug-дампа `netsh`

- `write_raw_netsh` (по умолчанию `false`) — постоянная запись `raw_netsh.txt`.
- `raw_netsh_rotation_dir` — каталог для таймстемп-дампов при ошибке `netsh`.
- `raw_netsh_rotation_keep` — сколько последних таймстемп-дампов хранить (ротация по количеству файлов).

Поведение:
- `raw_netsh.txt` пишется только если `write_raw_netsh=true` **или** если `netsh` завершился с ошибкой.
- При ошибке `netsh` дополнительно создаётся таймстемп-файл вида `raw_netsh_YYYYMMDD_HHMMSS.txt` в `raw_netsh_rotation_dir`, после чего выполняется ротация старых файлов.
