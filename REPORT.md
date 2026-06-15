## 1) Hệ thống gốc (baseline)
- `solution/prompt.txt`: rất sơ sài (1 dòng) → dễ bịa tổng tiền, tính sai, gọi tool dư, dính prompt injection, lộ PII.
- `solution/config.json`: `temperature=1.6`, tắt `retry/cache`, `loop_guard=false`, `normalize_unicode=false`, `redact_pii=false`, `tool_budget=0`, có `catalog_override` → dễ lỗi và không ổn định.
- `solution/wrapper.py`: chỉ passthrough `call_next()` → chưa có telemetry/mitigation.
- `solution/findings.json`: còn `TODO`.

## 2) Đang làm được gì
- Chạy được pipeline theo repo: `selfcheck` → `observathon-sim` → `observathon-score` → tạo `run_output.json` và `score.json`.
- Có sẵn scaffold telemetry (`solution/instrument.py`, `telemetry/*`) để log latency/tokens/tools/cost/PII (nhưng wrapper chưa dùng).

## 3) Cải thiện so với baseline (kế hoạch triển khai)
- Prompt: viết lại theo hướng **tool-first + grounding + công thức tính chuẩn + giới hạn tool + chống injection + không lộ PII**.
- Config: giảm `temperature` (~0.2), bật `loop_guard`, bật `retry/cache`, bật `normalize_unicode` + `redact_pii`, đặt `tool_budget` (~4), cân nhắc xoá `catalog_override`.
- Wrapper: thêm **telemetry** (latency/tokens/tools/cost/PII), **sanitize NOTE/GHI CHÚ**, **retry** khi lỗi, **cache** khi câu hỏi trùng.
- Findings: điền `findings.json` bằng **evidence từ telemetry** (fault_class, root_cause, suggested_fix).