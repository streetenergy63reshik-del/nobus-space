# C5 — локальная граница HTTP

Существующий public HTTPS → SSH relay → loopback Uvicorn → один Core. Внешний ingress не меняется; public readiness в preflight403, live window NOT RUN. Публичного нагрузочного теста и новой TLS/DNS/HSTS политики не было.

| Граница | Кандидат |
|---|---|
| Host/Origin | Exact authority/port и mutation Origin; forwarded headers не создают полномочий |
| Proxy/CORS/auth | proxy_headers=False; wildcard CORS нет; C4 bearer/signature/freshness/replay/CSRF сохранены |
| Methods/body | GET/HEAD/POST; initData4КиБ/task16КиБ, чтение5с, strict Content-Type/multipart/digest |
| Header/query/path | 64заголовка, суммарно16КиБ; raw path/query512байт; duplicate singular и CL+TE отвергаются |
| Header time | 5с до полного header, включая keep-alive; настоящий loopback socket test |
| Connections | 16connections, WebSocket off; Uvicorn concurrency16/backlog32; keepalive5с |
| App concurrency/rate | 8активных, переполнение503 без app queue; общий burst30+2/с, session10+0,5/с |
| Response | 1МиБ и2048ASGI frames, буфер до выдачи; превышение503 |
| Total | 90с async request/response; execution timeout503/UNKNOWN, не pre-admission408 |
| Headers | no-store, CSP self/Telegram, nosniff, no-referrer, Permissions-Policy; без HSTS preload/includeSubDomains |
| Readiness | Нет callback→503; health не заменяет Core/worker/store/ASR/polling/public готовность |

90с — async deadline. Синхронная операция, блокирующая event loop, контролируется внешним supervisor probe и закрытием собственной Job. Это не hard realtime гарантия синхронных операций.

tests/test_c5_ingress.py: absent readiness, wrong Host port/forwarded spoof, duplicate/oversized headers, framing, method/path/query, auth burst, concurrency без очереди, timeout, response limit, redacted exception, real slow-header socket.
Прежние auth/session/body/artifact/UNKNOWN tests включаются в финальную C5 регрессию; frontend static bytes не изменены.

WIP73PASS/1FAIL: outer guard возвращал400 вместо прежнего401 для duplicate Authorization. Исправлен guard, тестовый контракт сохранён. Затем new ingress+C4 recovery37PASS. Это WIP evidence, не final verdict.
Edge rate limit, TLS/config и активность новых budgets в старом live не заявляются; activation C6 проверяет их отдельно.
