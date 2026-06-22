<!-- AUTO-GENERATED from OpenAPI — do not edit manually. Run: python scripts/generate_api_docs.py --import-app --update-nav -->

# WebSocket

Real-time notifications via WebSocket (not included in OpenAPI JSON).

## WS /ws/{client_id}

Connect to the notification stream.

**Authentication:** JWT token as query parameter `token` (required)

**URL:**

```
wss://fileguardian.com.ru/ws/{client_id}?token=YOUR_JWT
```

**Parameters:**

| Parameter | In | Type | Required | Description |
|-----------|----|------|----------|-------------|
| client_id | path | string | ✅ | Client identifier (unique per tab/session) |
| token | query | string | ✅ | JWT access token |

**Server → client events:**

| Event | Description |
|-------|-------------|
| `connected` | Connection established |
| `ping` | Heartbeat (interval: `WEBSOCKET_HEARTBEAT_INTERVAL`) |
| `pong` | Response to client `ping` action |
| `subscribed` | Subscription list updated |
| `document_parsed` | Document processing finished |
| `prediction_ready` | Prediction completed |
| `dicom_processed` | DICOM study ready |
| `error` | Error payload |

**Client → server actions:**

```json
{"action": "subscribe", "events": ["document_parsed", "prediction_ready"]}
{"action": "unsubscribe", "events": ["document_parsed"]}
{"action": "ping"}
{"action": "pong"}
```

**Example (JavaScript):**

```javascript
const token = localStorage.getItem("token");
const ws = new WebSocket(`wss://fileguardian.com.ru/ws/dashboard?token=${token}`);
ws.onmessage = (e) => console.log(JSON.parse(e.data));
ws.send(JSON.stringify({ action: "subscribe", events: ["prediction_ready"] }));
```

**Close codes:**

| Code | Meaning |
|------|---------|
| 1008 | Invalid or missing token |
| 1011 | WebSocket disabled on server |
| 1013 | Server at capacity |