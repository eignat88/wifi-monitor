#!/usr/bin/env python3
"""Wi-Fi monitoring script for Windows 10/11.

Collects Wi-Fi and connectivity metrics every interval and writes CSV/JSONL logs.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import locale
import subprocess
import unicodedata
import sys
import time
import socket
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_CONFIG: dict[str, Any] = {
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
}

PING_LOSS_PATTERNS = (
    re.compile(r"\((\d+)%\s*loss\)", re.IGNORECASE),
    re.compile(r"\((\d+)%\s*потерь\)", re.IGNORECASE),
    re.compile(r"lost\s*=\s*\d+\s*\((\d+)%\)", re.IGNORECASE),
    re.compile(r"потеряно\s*=\s*\d+\s*\((\d+)%\)", re.IGNORECASE),
)

PING_TIME_PATTERNS = (
    re.compile(r"time[=<]\s*(\d+)\s*ms", re.IGNORECASE),
    re.compile(r"time[=<]\s*(\d+)\s*мс", re.IGNORECASE),
    re.compile(r"время[=<]\s*(\d+)\s*мс", re.IGNORECASE),
)

IPV4_PATTERNS = (
    re.compile(r"(?:IPv4 Address|IPv4-адрес)[^:]*:\s*([\d.]+)", re.IGNORECASE),
)

DEFAULT_GATEWAY_PATTERNS = (
    re.compile(r"default gateway[ .:]*?(\d{1,3}(?:\.\d{1,3}){3})", re.IGNORECASE),
    re.compile(r"основной шлюз[ .:]*?(\d{1,3}(?:\.\d{1,3}){3})", re.IGNORECASE),
)




DIAGNOSTIC_FIELDS = [
    "timestamp",
    "gateway",
    "gateway_ping_status",
    "gateway_latency_ms",
    "gateway_packet_loss",
    "gateway_jitter_ms",
    "gateway_latency_min_ms",
    "gateway_latency_max_ms",
    "internet_ping_status",
    "internet_target",
    "internet_latency_ms",
    "internet_packet_loss",
    "dns_status",
    "dns_resolution_ms",
    "resolved_ip",
    "previous_bssid",
    "current_bssid",
    "roaming_detected",
    "previous_channel",
    "current_channel",
    "channel_changed",
    "classification",
    "consecutive_failures",
]

CSV_FIELDS = [
    "timestamp",
    "ssid",
    "bssid",
    "connection_status",
    "is_connected",
    "ip_address",
    "signal_percent",
    "signal_dbm",
    "signal_quality",
    "radio_type",
    "channel",
    "rx_rate_mbps",
    "tx_rate_mbps",
    "ping_status",
    "latency_ms",
    "packet_loss_percent",
    "target",
    "is_internet_available",
    "network_status",
    "error_count",
    "event",
    "error",
    "comment",
]


@dataclass
class MonitorState:
    previous_connected: bool | None = None
    previous_ssid: str = ""
    previous_bssid: str = ""
    previous_internet: bool | None = None
    previous_channel: str = ""
    previous_gateway_latency: int | None = None
    outage_active: bool = False
    consecutive_failures: int = 0


@dataclass
class Logger:
    log_path: Path
    log_format: str
    csv_fields: list[str] = field(default_factory=lambda: CSV_FIELDS.copy())
    _csv_initialized: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, row: dict[str, Any]) -> None:
        if self.log_format == "jsonl":
            self._write_jsonl(row)
        else:
            self._write_csv(row)

    def _write_csv(self, row: dict[str, Any]) -> None:
        try:
            exists = self.log_path.exists()
            with self.log_path.open("a", newline="", encoding="utf-8") as file_obj:
                writer = csv.DictWriter(file_obj, fieldnames=self.csv_fields)
                if not exists:
                    writer.writeheader()
                writer.writerow({k: row.get(k, "") for k in self.csv_fields})
            self._csv_initialized = True
        except Exception as exc:  # noqa: BLE001
            print(f"[ERROR] Failed to write CSV log: {exc}", file=sys.stderr)

    def _write_jsonl(self, row: dict[str, Any]) -> None:
        try:
            with self.log_path.open("a", encoding="utf-8") as file_obj:
                file_obj.write(json.dumps(row, ensure_ascii=False) + "\n")
        except Exception as exc:  # noqa: BLE001
            print(f"[ERROR] Failed to write JSONL log: {exc}", file=sys.stderr)


@dataclass
class SummaryStats:
    ping_values: list[int] = field(default_factory=list)
    signal_values: list[int] = field(default_factory=list)
    samples: int = 0
    ping_fail_samples: int = 0
    disconnect_samples: int = 0

    def add_row(self, row: dict[str, Any]) -> None:
        self.samples += 1
        latency = row.get("latency_ms")
        if isinstance(latency, int):
            self.ping_values.append(latency)
        if row.get("ping_status") != "OK":
            self.ping_fail_samples += 1

        signal_dbm = row.get("signal_dbm")
        if isinstance(signal_dbm, int):
            self.signal_values.append(signal_dbm)

        if not row.get("is_connected"):
            self.disconnect_samples += 1

    def to_summary_rows(self, timestamp: str) -> list[dict[str, Any]]:
        avg_ping = round(sum(self.ping_values) / len(self.ping_values)) if self.ping_values else ""
        max_ping = max(self.ping_values) if self.ping_values else ""
        avg_signal = round(sum(self.signal_values) / len(self.signal_values)) if self.signal_values else ""
        packet_loss = math.floor((self.ping_fail_samples / self.samples) * 100) if self.samples else 0

        return [
            {"timestamp": timestamp, "metric": "Avg ping", "value": f"{avg_ping} ms" if avg_ping != "" else ""},
            {"timestamp": timestamp, "metric": "Max ping", "value": f"{max_ping} ms" if max_ping != "" else ""},
            {"timestamp": timestamp, "metric": "Avg signal", "value": f"{avg_signal} dBm" if avg_signal != "" else ""},
            {"timestamp": timestamp, "metric": "Packet loss", "value": f"{packet_loss}%"},
            {"timestamp": timestamp, "metric": "Disconnects", "value": self.disconnect_samples},
        ]


def _decode_output(raw: bytes) -> str:
    encodings = [
        locale.getpreferredencoding(False),
        "utf-8",
        "cp866",
        "cp1251",
    ]
    for encoding in encodings:
        if not encoding:
            continue
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def run_command(command: list[str], timeout: int = 5) -> tuple[bool, str, str]:
    try:
        result = subprocess.run(command, capture_output=True, text=False, timeout=timeout, shell=False)
        stdout = _decode_output(result.stdout)
        stderr = _decode_output(result.stderr)
        return result.returncode == 0, stdout, stderr
    except subprocess.TimeoutExpired as exc:
        cmd_str = " ".join(command)
        return False, "", f"command_timeout command='{cmd_str}' timeout={timeout}s error={exc}"
    except FileNotFoundError as exc:
        cmd_str = " ".join(command)
        return False, "", f"command_not_found command='{cmd_str}' timeout={timeout}s error={exc}"




def normalize_key(text: str) -> str:
    lowered = unicodedata.normalize("NFKC", text.strip().lower())
    return re.sub(r"\s+", " ", lowered)


FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "state": ("state", "состояние"),
    "ssid": ("ssid",),
    "bssid": ("bssid",),
    "signal": ("signal", "сигнал"),
    "radio_type": ("radio type", "тип радио"),
    "channel": ("channel", "канал"),
    "rx_rate": ("receive rate", "receive rate (mbps)", "скорость приема"),
    "tx_rate": ("transmit rate", "transmit rate (mbps)", "скорость передачи"),
}


def resolve_field(data: dict[str, str], logical_name: str) -> str:
    for alias in FIELD_ALIASES.get(logical_name, (logical_name,)):
        value = data.get(normalize_key(alias))
        if value is not None:
            return value
    return ""


def parse_signal_percent(value: str) -> int | None:
    m = re.search(r"(\d+)", value or "")
    return int(m.group(1)) if m else None


def signal_quality_from_dbm(dbm: int | None) -> str:
    if dbm is None:
        return ""
    if dbm >= -60:
        return "Отличный"
    if dbm >= -67:
        return "Хороший"
    if dbm >= -75:
        return "Слабый"
    return "Плохой"


def parse_windows_key_value_block(raw_text: str | None) -> dict[str, str]:
    parsed: dict[str, str] = {}
    if not raw_text:
        return parsed

    for line in raw_text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        parsed[normalize_key(key)] = value.strip()
    return parsed


def collect_wifi_metrics() -> tuple[dict[str, Any], str | None]:
    ok, out, err = run_command(["netsh", "wlan", "show", "interfaces"])
    Path("raw_netsh.txt").write_text(out or err or "", encoding="utf-8")
    if not ok:
        return {
            "is_connected": False,
            "connection_status": "DISCONNECTED",
            "ssid": "",
            "bssid": "",
            "signal_percent": "",
            "signal_dbm": "",
            "signal_quality": "",
            "radio_type": "",
            "channel": "",
            "rx_rate_mbps": "",
            "tx_rate_mbps": "",
            "ip_address": "",
            "network_status": "Ошибка анализа",
            "comment": "",
        }, f"netsh_error: {err or 'unknown error'}"

    data = parse_windows_key_value_block(out)
    state = resolve_field(data, "state").strip().lower()
    ssid = resolve_field(data, "ssid")
    bssid = resolve_field(data, "bssid")
    signal_percent = parse_signal_percent(resolve_field(data, "signal"))
    signal_dbm = int(signal_percent / 2 - 100) if signal_percent is not None else None

    return {
        "ssid": ssid,
        "bssid": bssid,
        "signal_percent": signal_percent if signal_percent is not None else "",
        "signal_dbm": signal_dbm if signal_dbm is not None else "",
        "signal_quality": signal_quality_from_dbm(signal_dbm),
        "radio_type": resolve_field(data, "radio_type"),
        "channel": resolve_field(data, "channel"),
        "rx_rate_mbps": parse_signal_percent(resolve_field(data, "rx_rate")) or resolve_field(data, "rx_rate"),
        "tx_rate_mbps": parse_signal_percent(resolve_field(data, "tx_rate")) or resolve_field(data, "tx_rate"),
        "state_raw": state,
    }, None


def parse_default_gateway() -> str | None:
    ok, out, _ = run_command(["ipconfig"])
    if not ok:
        return None
    return parse_default_gateway_from_text(out)


def parse_default_gateway_from_text(output: str) -> str | None:
    lines = output.splitlines()
    for idx, line in enumerate(lines):
        for pattern in DEFAULT_GATEWAY_PATTERNS:
            match = pattern.search(line)
            if match:
                return match.group(1)

            normalized = line.strip().lower()
            if ("default gateway" in normalized or "основной шлюз" in normalized) and idx + 1 < len(lines):
                next_line = lines[idx + 1].strip()
                ip_match = re.search(r"(\d{1,3}(?:\.\d{1,3}){3})", next_line)
                if ip_match:
                    return ip_match.group(1)
    return None


def parse_ping_loss_from_text(output: str) -> int | None:
    for pattern in PING_LOSS_PATTERNS:
        match = pattern.search(output)
        if match:
            return int(match.group(1))
    return None


def parse_ping_time_from_text(output: str) -> int | None:
    for pattern in PING_TIME_PATTERNS:
        match = pattern.search(output)
        if match:
            return int(match.group(1))
    return None


def ping_target(target: str) -> dict[str, Any]:
    ok, out, err = run_command(["ping", "-n", "1", "-w", "900", target], timeout=3)
    if not ok and not out:
        return {
            "target": target,
            "ping_status": "FAIL",
            "latency_ms": "",
            "packet_loss_percent": 100,
            "error": f"ping_error: {err or 'unknown error'}",
        }

    packet_loss = parse_ping_loss_from_text(out)
    latency_ms = parse_ping_time_from_text(out)
    success = "TTL=" in out.upper() and "unreachable" not in out.lower()

    return {
        "target": target,
        "ping_status": "OK" if success else "FAIL",
        "latency_ms": latency_ms if latency_ms is not None else "",
        "packet_loss_percent": packet_loss if packet_loss is not None else "",
        "error": "" if success else (err.strip() or "ping_failed"),
    }


def ping_target_series(target: str, count: int = 5) -> dict[str, Any]:
    latencies: list[int] = []
    losses: list[int] = []
    status = "OK"
    error = ""
    for _ in range(max(1, count)):
        result = ping_target(target)
        if isinstance(result.get("latency_ms"), int):
            latencies.append(result["latency_ms"])
        if isinstance(result.get("packet_loss_percent"), int):
            losses.append(result["packet_loss_percent"])
        if result.get("ping_status") != "OK":
            status = "FAIL"
            if not error:
                error = str(result.get("error", "ping_failed"))

    latency_avg = round(sum(latencies) / len(latencies)) if latencies else ""
    latency_min = min(latencies) if latencies else ""
    latency_max = max(latencies) if latencies else ""
    jitter = (latency_max - latency_min) if latencies else ""
    packet_loss = round(sum(losses) / len(losses)) if losses else (100 if status == "FAIL" else "")

    return {
        "target": target,
        "ping_status": status,
        "latency_ms": latency_avg,
        "latency_min_ms": latency_min,
        "latency_max_ms": latency_max,
        "jitter_ms": jitter,
        "packet_loss_percent": packet_loss,
        "error": error if status != "OK" else "",
    }


def resolve_dns(hostname: str = "google.com") -> dict[str, Any]:
    started = time.time()
    try:
        resolved_ip = socket.gethostbyname(hostname)
        elapsed_ms = round((time.time() - started) * 1000)
        return {"dns_status": "OK", "dns_resolution_ms": elapsed_ms, "resolved_ip": resolved_ip}
    except socket.gaierror as exc:
        elapsed_ms = round((time.time() - started) * 1000)
        return {
            "dns_status": "FAIL",
            "dns_resolution_ms": elapsed_ms,
            "resolved_ip": "",
            "dns_error": f"dns_resolution_failed hostname='{hostname}' error={exc}",
        }


def classify_network_issue(row: dict[str, Any], diag: dict[str, Any]) -> str:
    gateway = str(diag.get("gateway", "") or "").strip()
    gateway_status = str(diag.get("gateway_ping_status", "") or "")
    internet_status = str(diag.get("internet_ping_status", "") or "")
    dns_status = str(diag.get("dns_status", "") or "")

    if diag.get("roaming_detected"):
        return "HOTSPOT_RESTART"

    if not gateway:
        if internet_status == "OK" and dns_status == "OK":
            return "NORMAL_WITH_GATEWAY_UNKNOWN"
        if internet_status == "OK":
            return "GATEWAY_UNKNOWN"
        return "DIAGNOSTIC_INCOMPLETE"

    if gateway_status == "FAIL" and internet_status == "FAIL" and row.get("is_connected"):
        return "HOTSPOT_FROZEN"
    if gateway_status == "OK" and internet_status == "FAIL":
        return "MOBILE_NETWORK"
    if gateway_status == "OK" and internet_status == "OK" and dns_status == "FAIL":
        return "DNS_ISSUE"

    packet_loss = diag.get("gateway_packet_loss")
    jitter = diag.get("gateway_jitter_ms")
    if gateway_status == "OK" and internet_status == "OK":
        if (isinstance(jitter, int) and jitter > 250) or (isinstance(packet_loss, int) and packet_loss >= 40):
            return "NETWORK_CONGESTION"
        return "NORMAL"

    return "DIAGNOSTIC_INCOMPLETE"


def choose_ping_result(targets: list[str]) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    for target in targets:
        result = ping_target(target)
        if result["ping_status"] == "OK":
            return result
        failures.append(result)
    return failures[0] if failures else {"target": "", "ping_status": "FAIL", "latency_ms": "", "packet_loss_percent": "", "error": "no_targets"}


def detect_event(state: MonitorState, row: dict[str, Any], failures_before_outage: int, latency_threshold_ms: int) -> str:
    events: list[str] = []
    connected = bool(row["is_connected"])
    internet = bool(row["is_internet_available"])

    if state.previous_connected is False and connected:
        events.append("WIFI_CONNECTED")
    if state.previous_connected is True and not connected:
        events.append("WIFI_DISCONNECTED")

    if connected and state.previous_ssid and row["ssid"] and state.previous_ssid != row["ssid"]:
        events.append("SSID_CHANGED")
    if connected and state.previous_bssid and row["bssid"] and state.previous_bssid != row["bssid"]:
        events.append("BSSID_CHANGED")

    if row["ping_status"] == "FAIL":
        events.append("PING_FAIL")
    latency = row.get("latency_ms")
    if isinstance(latency, int) and latency > latency_threshold_ms:
        events.append("HIGH_LATENCY")

    if state.previous_internet is False and internet:
        events.append("INTERNET_RESTORED")

    outage_condition = (not connected and not internet) or (row["ping_status"] == "FAIL" and state.consecutive_failures >= failures_before_outage)
    if not state.outage_active and outage_condition and row["ping_status"] != "OK":
        state.outage_active = True
        events.append("OUTAGE_STARTED")
    elif state.outage_active and state.consecutive_failures == 0:
        state.outage_active = False
        events.append("OUTAGE_ENDED")

    return "|".join(events)


def load_config(path: Path | None) -> dict[str, Any]:
    config = DEFAULT_CONFIG.copy()
    if path is None:
        return config
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open(encoding="utf-8") as file_obj:
        loaded = json.load(file_obj)
    if not isinstance(loaded, dict):
        raise ValueError("Config must be a JSON object")
    config.update(loaded)
    return config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Windows Wi-Fi monitor script")
    parser.add_argument("--config", type=Path, help="Path to config.json")
    parser.add_argument("--log", type=Path, help="Override log file path")
    parser.add_argument("--interval", type=float, help="Override check interval in seconds")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        config = load_config(args.config)
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] Failed to load config: {exc}", file=sys.stderr)
        return 1

    if args.log:
        config["log_file"] = str(args.log)
    if args.interval is not None:
        config["check_interval_sec"] = args.interval

    interval = float(config.get("check_interval_sec", 1))
    latency_threshold_ms = int(config.get("latency_threshold_ms", 1000))
    failures_before_outage = int(config.get("failures_before_outage", 3))
    log_format = str(config.get("log_format", "csv")).lower()
    log_file = Path(str(config.get("log_file", "wifi_monitor_log.csv")))
    summary_interval = int(config.get("summary_interval_sec", 300))
    summary_log_file = Path(str(config.get("summary_log_file", "wifi_monitor_summary.csv")))
    diagnostic_log_file = Path(str(config.get("diagnostic_log_file", "wifi_monitor_diagnostics.csv")))
    ping_series_count = int(config.get("ping_series_count", 5))

    if log_format not in {"csv", "jsonl"}:
        print("[WARN] Unknown log_format, falling back to csv", file=sys.stderr)
        log_format = "csv"

    targets = list(config.get("ping_targets", []))
    gateway = parse_default_gateway()
    if gateway and gateway not in targets:
        targets.append(gateway)
    if not targets:
        targets = ["8.8.8.8"]

    logger = Logger(log_file, log_format)
    summary_logger = Logger(summary_log_file, "csv", csv_fields=["timestamp", "metric", "value"])
    diagnostics_logger = Logger(diagnostic_log_file, "csv", csv_fields=DIAGNOSTIC_FIELDS.copy())
    state = MonitorState()
    summary_stats = SummaryStats()
    next_summary_at = time.time() + summary_interval

    print(f"Starting Wi-Fi monitor. Interval={interval}s, log={log_file}, format={log_format}")

    while True:
        loop_started = time.time()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        row: dict[str, Any] = {
            "timestamp": timestamp,
            "ssid": "",
            "bssid": "",
            "signal_percent": "",
            "signal_dbm": "",
            "signal_quality": "",
            "radio_type": "",
            "channel": "",
            "rx_rate_mbps": "",
            "tx_rate_mbps": "",
            "ip_address": "",
            "network_status": "Ошибка анализа",
            "comment": "",
            "connection_status": "DISCONNECTED",
            "is_connected": False,
            "ping_status": "FAIL",
            "latency_ms": "",
            "packet_loss_percent": "",
            "target": "",
            "is_internet_available": False,
            "error_count": 0,
            "event": "",
            "error": "",
        }

        try:
            wifi_metrics, wifi_error = collect_wifi_metrics()
            row.update(wifi_metrics)
            if wifi_error:
                row["error"] = wifi_error

            ping_result = choose_ping_result(targets)
            row.update(ping_result)

            gateway_ping = ping_target_series(gateway, count=ping_series_count) if gateway else {"target": "", "ping_status": "UNKNOWN", "latency_ms": "", "latency_min_ms": "", "latency_max_ms": "", "jitter_ms": "", "packet_loss_percent": "", "error": "gateway_not_found"}
            dns_result = resolve_dns("google.com")

            internet_ok = row["ping_status"] == "OK"
            row["is_internet_available"] = internet_ok
            ok_ip, ip_out, _ = run_command(["ipconfig"])
            ipv4 = None
            if ok_ip:
                for pattern in IPV4_PATTERNS:
                    ipv4 = pattern.search(ip_out)
                    if ipv4:
                        break
            row["ip_address"] = ipv4.group(1) if ipv4 else ""
            st = str(row.get("state_raw", "")).lower()
            row["is_connected"] = st in {"connected", "подключено"} or (bool(row["ssid"]) and bool(row["bssid"]) and bool(row["ip_address"])) or (bool(row["ssid"]) and bool(row["bssid"]) and row["ping_status"] == "OK")
            row["connection_status"] = "CONNECTED" if row["is_connected"] else "DISCONNECTED"

            failed = (not row["is_connected"]) or (not internet_ok)
            latency = row.get("latency_ms")
            if isinstance(latency, int) and latency > latency_threshold_ms:
                failed = True

            state.consecutive_failures = state.consecutive_failures + 1 if failed else 0
            row["error_count"] = state.consecutive_failures

            inconsistent = (row["connection_status"] == "DISCONNECTED" and row["ping_status"] == "OK") or ((not row["is_connected"]) and row["is_internet_available"])
            if inconsistent:
                row["network_status"] = "Ошибка анализа"
                row["event"] = "INCONSISTENT_STATE"
                row["error"] = "Интернет доступен, но Wi-Fi отмечен как отключенный"
                row["comment"] = "Обнаружено противоречивое состояние"
            else:
                row["network_status"] = "Нормально" if row["is_connected"] and row["is_internet_available"] else "Проблемы с сетью"
                row["event"] = detect_event(state, row, failures_before_outage, latency_threshold_ms)
                if row["event"] == "":
                    row["comment"] = "Сеть работает стабильно" if row["network_status"] == "Нормально" else "Требуется диагностика подключения"

            roaming_detected = bool(state.previous_bssid and row.get("bssid") and state.previous_bssid != row.get("bssid"))
            channel_changed = bool(state.previous_channel and row.get("channel") and state.previous_channel != row.get("channel"))
            diag_row = {
                "timestamp": timestamp,
                "gateway": gateway or "",
                "gateway_ping_status": gateway_ping.get("ping_status", ""),
                "gateway_latency_ms": gateway_ping.get("latency_ms", ""),
                "gateway_packet_loss": gateway_ping.get("packet_loss_percent", ""),
                "gateway_jitter_ms": gateway_ping.get("jitter_ms", ""),
                "gateway_latency_min_ms": gateway_ping.get("latency_min_ms", ""),
                "gateway_latency_max_ms": gateway_ping.get("latency_max_ms", ""),
                "internet_ping_status": row.get("ping_status", ""),
                "internet_target": row.get("target", ""),
                "internet_latency_ms": row.get("latency_ms", ""),
                "internet_packet_loss": row.get("packet_loss_percent", ""),
                "dns_status": dns_result.get("dns_status", ""),
                "dns_resolution_ms": dns_result.get("dns_resolution_ms", ""),
                "resolved_ip": dns_result.get("resolved_ip", ""),
                "previous_bssid": state.previous_bssid,
                "current_bssid": row.get("bssid", ""),
                "roaming_detected": roaming_detected,
                "previous_channel": state.previous_channel,
                "current_channel": row.get("channel", ""),
                "channel_changed": channel_changed,
                "classification": "",
                "consecutive_failures": state.consecutive_failures,
            }
            diag_row["classification"] = classify_network_issue(row, diag_row)
            diagnostics_logger.log(diag_row)

            state.previous_connected = bool(row.get("is_connected"))
            state.previous_ssid = str(row.get("ssid", "") or "")
            state.previous_bssid = str(row.get("bssid", "") or "")
            state.previous_internet = bool(row.get("is_internet_available"))
            state.previous_channel = str(row.get("channel", "") or "")

        except Exception as exc:  # noqa: BLE001
            state.consecutive_failures += 1
            row["error_count"] = state.consecutive_failures
            row["event"] = "MONITOR_ERROR"
            row["error"] = f"monitor_loop_error type={type(exc).__name__} target={row.get('target', '')} error={exc}"

        logger.log(row)
        summary_stats.add_row(row)

        now = time.time()
        if now >= next_summary_at:
            for summary_row in summary_stats.to_summary_rows(timestamp):
                summary_logger.log(summary_row)
            summary_stats = SummaryStats()
            next_summary_at = now + summary_interval

        elapsed = time.time() - loop_started
        time.sleep(max(0.0, interval - elapsed))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Stopped by user")
        raise SystemExit(0)
