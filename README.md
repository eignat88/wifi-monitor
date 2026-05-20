# Wi-Fi Monitor

Скрипт для непрерывного мониторинга качества Wi‑Fi подключения в Windows 10/11.

## Что делает скрипт

`wifi_monitor.py` циклически собирает метрики подключения и пишет их в CSV/JSONL-логи:
- состояние подключения Wi‑Fi (SSID/BSSID, канал, уровень сигнала, PHY-скорости);
- доступность интернета по ICMP ping;
- диагностику до шлюза и DNS;
- события (обрывы, восстановление, смена BSSID/SSID/канала, всплески задержки);
- классификацию вероятного типа проблемы (`classification`) в диагностическом логе.

---

## Требования

- **ОС:** Windows 10 или Windows 11.
- **Python:** Python 3.10+ (рекомендуется 3.11+).
- Доступ к системным утилитам Windows:
  - `netsh` (чтение параметров Wi‑Fi),
  - `ipconfig` (IP и шлюз),
  - `ping` (проверка доступности/задержки).

> Скрипт рассчитан на запуск именно в Windows-среде, так как парсит вывод Windows-команд.

---

## Быстрый запуск

1. Отредактируйте `config.json` (при необходимости).
2. Запустите мониторинг:

```bash
python wifi_monitor.py --config config.json
```

После запуска скрипт работает в бесконечном цикле до `Ctrl+C` и создаёт/обновляет логи:
- основной: `wifi_monitor_log.csv`;
- сводный: `wifi_monitor_summary.csv`;
- диагностический: `wifi_monitor_diagnostics.csv`.

---

## Аргументы CLI

Скрипт поддерживает 3 аргумента командной строки:

- `--config <path>` — путь к файлу конфигурации JSON.
- `--log <path>` — переопределяет `log_file` из конфига (только основной лог).
- `--interval <sec>` — переопределяет `check_interval_sec` из конфига.

### Примеры

Запуск с дефолтным конфигом:

```bash
python wifi_monitor.py --config config.json
```

Запись основного лога в другой файл:

```bash
python wifi_monitor.py --config config.json --log logs/session_01.csv
```

Увеличение частоты опроса (раз в 0.5 сек):

```bash
python wifi_monitor.py --config config.json --interval 0.5
```

Комбинированный пример:

```bash
python wifi_monitor.py --config profiles/home.json --log logs/home.csv --interval 1
```

---

## Конфигурация `config.json`

Ниже перечислены все ключи, которые используются скриптом.

| Ключ | Тип | По умолчанию | Назначение |
|---|---|---:|---|
| `check_interval_sec` | number | `1` | Интервал между циклами мониторинга (сек). |
| `ping_targets` | array[string] | `['8.8.8.8', '1.1.1.1']` | Список интернет-целей для проверки доступности. Скрипт выбирает первую успешную цель. |
| `latency_threshold_ms` | integer | `1000` | Порог «высокой задержки» для события `HIGH_LATENCY` и учёта деградации. |
| `failures_before_outage` | integer | `3` | Сколько подряд неуспешных итераций считать началом аварии (`OUTAGE_STARTED`). |
| `log_format` | string (`csv`/`jsonl`) | `csv` | Формат **основного** лога. При неизвестном значении — fallback в `csv`. |
| `log_file` | string | `wifi_monitor_log.csv` | Путь к основному логу (может быть переопределён `--log`). |
| `summary_interval_sec` | integer | `300` | Период записи сводной статистики в `summary_log_file` (сек). |
| `summary_log_file` | string | `wifi_monitor_summary.csv` | Путь к сводному логу. |
| `diagnostic_log_file` | string | `wifi_monitor_diagnostics.csv` | Путь к диагностическому логу с классификацией проблем. |
| `ping_series_count` | integer | `5` | Количество ping-попыток в серии до шлюза (для jitter/min/max/loss в диагностике). |
| `write_raw_netsh` | boolean | `false` | Постоянно писать последний raw-вывод `netsh` в `raw_netsh.txt`. |
| `raw_netsh_rotation_dir` | string | `netsh_dumps` | Каталог для таймстемп-дампов `raw_netsh_YYYYMMDD_HHMMSS.txt` при ошибке `netsh`. |
| `raw_netsh_rotation_keep` | integer | `10` | Сколько последних raw-дампов хранить в ротации. |

### Пример `config.json`

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

---

## Формат логов

## `wifi_monitor_log.csv` (основной лог)

| Поле | Описание |
|---|---|
| `timestamp` | Время замера (`YYYY-MM-DD HH:MM:SS`). |
| `ssid` | Имя Wi‑Fi сети. |
| `bssid` | BSSID (MAC точки доступа). |
| `connection_status` | `CONNECTED` / `DISCONNECTED`. |
| `is_connected` | Булево состояние подключения. |
| `ip_address` | IPv4-адрес хоста. |
| `signal_percent` | Уровень сигнала в процентах (`netsh`). |
| `signal_dbm` | Пересчитанный уровень сигнала в dBm. |
| `signal_quality` | Качественная оценка сигнала (`Отличный/Хороший/Слабый/Плохой`). |
| `radio_type` | Тип радио (например, 802.11ac/ax). |
| `channel` | Номер Wi‑Fi канала. |
| `rx_rate_mbps` | Скорость приёма (Mbps). |
| `tx_rate_mbps` | Скорость передачи (Mbps). |
| `ping_status` | Статус ping до внешней цели: `OK` / `FAIL`. |
| `latency_ms` | Задержка ping (ms). |
| `packet_loss_percent` | Потери ping (%). |
| `target` | Цель ping из `ping_targets` (или fallback). |
| `is_internet_available` | Булева доступность интернета по ping. |
| `network_status` | Высокоуровневый статус: `Нормально` / `Проблемы с сетью` / `Ошибка анализа`. |
| `error_count` | Текущее число подряд неуспешных итераций. |
| `event` | События (через `|`), например `PING_FAIL`, `OUTAGE_STARTED`, `INTERNET_RESTORED`. |
| `error` | Текст ошибки (если есть). |
| `comment` | Поясняющий комментарий к состоянию. |

## `wifi_monitor_diagnostics.csv` (диагностика)

| Поле | Описание |
|---|---|
| `timestamp` | Время диагностического среза. |
| `gateway` | IP шлюза по умолчанию (если найден). |
| `gateway_ping_status` | Статус серии ping до шлюза: `OK` / `FAIL` / `UNKNOWN`. |
| `gateway_latency_ms` | Средняя задержка до шлюза по серии ping. |
| `gateway_packet_loss` | Потери до шлюза в серии ping (%). |
| `gateway_jitter_ms` | Джиттер до шлюза (`max - min`). |
| `gateway_latency_min_ms` | Минимальная задержка серии до шлюза. |
| `gateway_latency_max_ms` | Максимальная задержка серии до шлюза. |
| `internet_ping_status` | Статус интернет-ping (из основного лога). |
| `internet_target` | Использованная внешняя цель ping. |
| `internet_latency_ms` | Задержка до внешней цели. |
| `internet_packet_loss` | Потери до внешней цели (%). |
| `dns_status` | Статус DNS-резолва (`OK` / `FAIL`). |
| `dns_resolution_ms` | Время DNS-резолва (ms). |
| `resolved_ip` | IP, полученный через DNS для тестового имени. |
| `previous_bssid` | Предыдущий BSSID. |
| `current_bssid` | Текущий BSSID. |
| `roaming_detected` | Флаг смены BSSID (роуминг/переключение AP). |
| `previous_channel` | Предыдущий канал. |
| `current_channel` | Текущий канал. |
| `channel_changed` | Флаг смены канала. |
| `classification` | Классификация вероятной причины проблемы. |
| `consecutive_failures` | Счётчик подряд неуспешных циклов на момент записи. |

---

## Интерпретация `classification`

Ниже — практическая трактовка значений, которые пишет скрипт:

- `NORMAL` — шлюз, интернет и DNS в норме, явных симптомов проблемы нет.
- `NETWORK_CONGESTION` — интернет доступен, но качество до шлюза плохое (высокий jitter или большие потери), вероятна перегрузка/помехи.
- `HOTSPOT_FROZEN` — устройство подключено к Wi‑Fi, но не пингуется ни шлюз, ни интернет; типично для «зависшей» точки/роутера.
- `MOBILE_NETWORK` — до шлюза всё хорошо, но внешние цели недоступны; вероятна проблема на стороне аплинка провайдера/мобильной сети.
- `DNS_ISSUE` — ping до шлюза и интернета проходит, но DNS-резолв не работает.
- `HOTSPOT_RESTART` — зафиксирована смена BSSID (роуминг/перезапуск точки/переключение между AP).
- `NORMAL_WITH_GATEWAY_UNKNOWN` — шлюз не найден, но интернет и DNS в норме.
- `GATEWAY_UNKNOWN` — шлюз не найден, интернет при этом доступен (диагностика частично ограничена).
- `DIAGNOSTIC_INCOMPLETE` — недостаточно данных для уверенной классификации.

### Короткие сценарии

- **`HOTSPOT_FROZEN`**: `is_connected=true`, `gateway_ping_status=FAIL`, `internet_ping_status=FAIL` → сначала проверьте питание/нагрузку роутера.
- **`MOBILE_NETWORK`**: `gateway_ping_status=OK`, `internet_ping_status=FAIL` → Wi‑Fi локально жив, ищите проблему на WAN/мобильном аплинке.
- **`DNS_ISSUE`**: `gateway_ping_status=OK`, `internet_ping_status=OK`, `dns_status=FAIL` → проверяйте DNS-серверы/фильтрацию/локальные политики.
- **`NETWORK_CONGESTION`**: `gateway_jitter_ms > 250` или `gateway_packet_loss >= 40` → вероятны радиопомехи, перегрузка канала, слабый сигнал.

---

## Параметры debug-дампа `netsh`

- `write_raw_netsh` — постоянная запись `raw_netsh.txt`.
- `raw_netsh_rotation_dir` — каталог для таймстемп-дампов при ошибке `netsh`.
- `raw_netsh_rotation_keep` — сколько последних таймстемп-дампов хранить.

Поведение:
- `raw_netsh.txt` пишется, если `write_raw_netsh=true` **или** `netsh` завершился с ошибкой.
- При ошибке `netsh` дополнительно создаётся `raw_netsh_YYYYMMDD_HHMMSS.txt` с ротацией старых файлов.
