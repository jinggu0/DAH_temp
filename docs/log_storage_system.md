# UAS/UTM Log Storage System

## 湲곗? 臾몄꽌 ?뺣젹

??援ы쁽? DAH 媛??UAS/UTM ?쒕퉬?ㅼ쓽 ?뺤긽 ?댁슜 濡쒓렇瑜??ㅼ쓬 怨듦컻 怨듭떇 臾몄꽌???먯튃??留욎떠 援ъ꽦?쒕떎.

- NIST SP 800-92: 濡쒓렇 ?앹꽦, ?꾩넚, ??? 遺꾩꽍, ?먭린源뚯???log management life cycle??湲곗??쇰줈 ?쇰뒗??
- NIST SP 800-53 Rev.5 AU controls: 媛먯궗 ?대깽???앹꽦, 寃?? 蹂댄샇, 蹂댁〈 ?붽뎄瑜?UAS/UTM service API濡?留ㅽ븨?쒕떎.
- OWASP Logging Cheat Sheet: 蹂댁븞 ?대깽?몄뿉 ?꾩슂??who/what/when/where/outcome ?꾨뱶? 誘쇨컧?뺣낫 ?쒖쇅 ?먯튃???곸슜?쒕떎.

????μ냼???ㅼ젣 援?泥닿퀎??鍮꾧났媛?洹쒓꺽??紐⑥궗?섏? ?딅뒗?? 怨듦컻 ?쒖???濡쒓렇 愿由?援ъ“瑜?UAS/UTM ?덈젴 ?섍꼍??留욎텣 寃껋씠??

## ???援ъ“

湲곕낯 寃쎈줈??`logs/uas_utm`?대떎.

- `audit.jsonl`: append-only 媛먯궗 ?대깽??蹂몃Ц
- `manifest.json`: ?꾩옱 濡쒓렇 ?뚯씪, profile, 留덉?留?hash, ?뺤콉 ?붿빟
- `audit-<timestamp>.jsonl`: ?ш린 湲곕컲 rotate archive

Docker Compose ?ㅽ뻾 ??`./logs:/app/logs` 蹂쇰ⅷ???ъ슜?섎?濡?而⑦뀒?대꼫 ?ъ떆???꾩뿉??audit log媛 ?좎??쒕떎.

## ?대깽???ㅽ궎留?
媛?JSONL row??`uas-utm-audit-log.v1` schema瑜??ъ슜?쒕떎.

?꾩닔 ?꾨뱶:

- `event_id`: UUID
- `event_type`: `command.requested`, `command.approved`, `mission_upload.requested`, `edge_work.acknowledged` ??- `created_at`, `timestamp_utc`: ISO-8601 UTC
- `source`: ?대깽???앹꽦 二쇱껜
- `actor`: operator, approver, edge id, source id 以??앸퀎 媛?ν븳 媛?- `object_type`, `object_id`: command, mission_upload, edge_device, telemetry ??- `outcome`: ?곹깭 ?먮뒗 泥섎━ 寃곌낵
- `severity`: info, notice, warning
- `data`: redaction???곸슜???대깽???먮Ц ?붿빟
- `integrity.previous_hash`: 吏곸쟾 ?대깽??hash
- `integrity.event_hash`: ?꾩옱 ?대깽??hash
- `control_mapping`: NIST/OWASP 湲곗? 留ㅽ븨 臾몄옄??
## 誘쇨컧?뺣낫 泥섎━

?ㅼ쓬 key token???ы븿???꾨뱶??????꾩뿉 `[REDACTED]`濡??泥댄븳??

- `password`
- `passwd`
- `token`
- `secret`
- `credential`
- `authorization`
- `api_key`
- `private_key`
- `signing_key`
- `signature`

MAVLink signing key, API token, edge credential? ?뺤긽 ?댁슜 濡쒓렇???먮Ц ??ν븯吏 ?딅뒗??

## 臾닿껐??寃利?
`JsonlAuditStore`??媛??대깽?몃? canonical JSON?쇰줈 ?뺣젹????SHA-256 hash瑜??앹꽦?쒕떎. ?ㅼ쓬 ?대깽?몃뒗 吏곸쟾 `event_hash`瑜?`previous_hash`濡???ν븳?? `/api/logs/verify`???꾩껜 JSONL???ㅼ떆 ?쎌뼱 hash chain??寃利앺븳??

寃利?API:

```bash
curl http://127.0.0.1:8080/api/logs/verify
```

?뺤긽 ?묐떟???듭떖 ?꾨뱶:

```json
{
  "valid": true,
  "checked_count": 4,
  "last_hash": "...",
  "errors": []
}
```

## 議고쉶 API

理쒓렐 audit log:

```bash
curl "http://127.0.0.1:8080/api/logs?limit=50"
```

?뱀젙 ?대깽?????

```bash
curl "http://127.0.0.1:8080/api/logs?event_type=command.approved&limit=20"
```

????곹깭:

```bash
curl http://127.0.0.1:8080/api/logs/status
```

湲곗〈 ?명솚 寃쎈줈:

```bash
curl http://127.0.0.1:8080/api/audit
```

## ?댁슜 ?덉감

1. ?쒕퉬???ㅽ뻾

```powershell
$env:PYTHONPATH="src"
python -m uas_utm_service.server --host 0.0.0.0 --port 8080 --scenario scenarios/korea_defense_uas_utm_ops.json --log-dir logs/uas_utm
```

2. ??쒕낫?쒖뿉??command ?먮뒗 mission upload瑜??붿껌/?뱀씤?쒕떎.
3. Audit Timeline?먯꽌 ?대깽??諛쒖깮???뺤씤?쒕떎.
4. Log Storage ?⑤꼸?먯꽌 event count? integrity ?곹깭瑜??뺤씤?쒕떎.
5. `/api/logs/verify`瑜?DAH ?쒖텧 ??evidence濡?罹≪쿂?쒕떎.

## ?ㅼ쓬 援ы쁽 異붿쿇

1. 濡쒓렇 寃??怨좊룄?? `actor`, `object_id`, ?쒓컙 踰붿쐞 ?꾪꽣瑜?API query濡?異붽??쒕떎.
2. ?댁쁺???몄쬆 ?곕룞: dashboard action??operator session id? role claim???곌껐?쒕떎.
3. ?먭꺽 ?섏쭛湲? JSONL??syslog ?먮뒗 OpenTelemetry collector濡?forward?섎뒗 ?좏깮 ?뚮윭洹몄씤??異붽??쒕떎.
4. 蹂댁〈 ?뺤콉: scenario package export ??log archive, manifest, verify result瑜??④퍡 臾띕뒗??
5. 寃쎈낫 洹쒖튃: command reject, edge ACK timeout, log integrity failure瑜?dashboard alert濡??밴꺽?쒕떎.

## AI Agent View

怨듦꺽/諛⑹뼱 ?먯씠?꾪듃 援ъ긽???꾪빐 ?먮낯 audit row? 蹂꾨룄濡?`/api/logs/agent-view`瑜??쒓났?쒕떎. ??view???ㅼ젣 怨듦꺽 ?덉감瑜??ы븿?섏? ?딄퀬, ????쒕??덉씠?섏뿉??愿痢? 遺꾨쪟, 諛⑹뼱 ?섏궗寃곗젙???ㅺ퀎?섍린 ?꾪븳 metadata留??쒓났?쒕떎.

```bash
curl "http://127.0.0.1:8080/api/logs/agent-view?limit=50"
# heartbeat noise를 제외하고 command/mission/ACK 중심으로 보기
curl "http://127.0.0.1:8080/api/logs/agent-view?limit=50&include_heartbeat=false"
# 특정 운용 단계만 보기
curl "http://127.0.0.1:8080/api/logs/agent-view?phase=c2_command_workflow&limit=20"
```

二쇱슂 ?꾨뱶:

- `event_family`: command, mission_upload, edge_device, edge_work ???곸쐞 event domain
- `phase`: c2_command_workflow, mission_planning_workflow, edge_execution_feedback ???댁슜 ?④퀎
- `perspectives`: blue_defense, red_scenario_planning
- `subject`: actor, source, role_guess
- `object`: object type/id, asset_id, mission_id
- `risk_score`: 0.0-1.0 踰붿쐞???쒕??덉씠???꾪뿕??- `labels`: control_plane, operator_approval, gateway_dispatch_ready, edge_boundary ??紐⑤뜽 ?낅젰??tag
- `features`: boolean/numeric feature map
- `defense_questions`: 諛⑹뼱 ?먯씠?꾪듃媛 ?먮떒?댁빞 ??吏덈Ц
- `scenario_hooks`: 怨듦꺽/諛⑹뼱 ?쒕굹由ъ삤 ?ㅺ퀎??鍮꾧났寃⑹쟻 hook

?먯씠?꾪듃 ?ㅺ퀎 異붿쿇 ?낅젰:

- Blue defense agent: `risk_score`, `labels`, `defense_questions`, `features.status_rejected`, `features.edge_acknowledged`
- Red scenario planner: `scenario_hooks`, `phase`, `object.asset_id`, `features.status_approved_for_gateway`
- Referee/scoring agent: event hash chain, approval order, edge ACK presence, baseline sequence deviation

## ???湲곗큹 ?쒕쾭 ?곹빀??泥댄겕由ъ뒪??
?꾩옱 ?쒕쾭??DAH UAS/UTM ?쒕굹由ъ삤 珥덉븞怨??蹂?agent ?ㅺ퀎 湲곕컲?쇰줈???곹빀?섎떎.

異⑹”????ぉ:

- UAV/UGV asset, mission, C2, air/ground zone 紐⑤뜽 蹂댁쑀
- MAVLink telemetry ingest? command/mission upload queue 蹂댁쑀
- operator approval怨?edge ACK audit 蹂댁쑀
- Docker Compose ?ㅽ뻾 援ъ“ 蹂댁쑀
- append-only log, redaction, hash-chain verify 蹂댁쑀
- agent-view log濡?怨듦꺽/諛⑹뼱 ?쒕굹由ъ삤 遺꾨쪟 媛??
?꾩쭅 ???蹂몄슫?????꾩슂????ぉ:

- 李멸??먮퀎 ?몄쬆/沅뚰븳 遺꾨━
- scenario reset怨?seed 怨좎젙
- ?먯닔 ?곗젙 API
- agent submission interface
- ?ㅼ떆媛?event stream??backpressure/replay ?뺤콉
- 怨듦꺽 payload媛 ?꾨땶 ?덉쟾??anomaly injection API
- ?댁쁺?먯슜 admin dashboard? export package ?먮룞?