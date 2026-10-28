# english-coach backend

Backend para un coach de inglés conversacional con dos canales que comparten
historial por `thread_id`:

- **Chat** — `POST /api/v1/chat`, contrato estándar **AG-UI** (SSE) con un
  `Agent` de [pydantic-ai].
- **Voz** — `WS /api/v1/voice/{thread_id}`, pipeline de **[Pipecat]** con
  **AssemblyAI** (STT), **ElevenLabs** (TTS) y **Silero VAD + Local Smart Turn
  v3** para la detección de turno.

Todo el pipeline es *streaming*: el audio entra por WebSocket, la transcripción
llega en parciales, el LLM emite deltas y el TTS devuelve PCM que se reenvía al
cliente sin esperar al final del turno. El navegador usa
[`@pipecat-ai/client-js`] sobre el transporte WebSocket con protobuf.

```
                 ┌───────────────────────────────────────────┐
  Chat texto ───►│ POST /api/v1/chat   (AG-UI estándar/SSE)  │
                 └───────────────────────────────────────────┘
                                   │
                          mismo SessionStore
                                   │
  ┌────────────────────────────────┴────────────────────────────────┐
  │ WS /api/v1/voice/{thread_id}   (RTVI + protobuf)                │
  │                                                                 │
  │  mic ─PCM16─► FastAPIWebsocketTransport                         │
  │                 ├─ Silero VAD + Smart Turn v3                   │
  │                 ├─ AssemblyAI STT                               │
  │                 ├─ LLM (LM Studio / OpenRouter)                 │
  │                 └─ ElevenLabs TTS ──► PCM16 ──► navegador       │
  └─────────────────────────────────────────────────────────────────┘
```

## Requisitos

- Python 3.12
- [`uv`](https://docs.astral.sh/uv/)
- Un servidor LLM compatible con OpenAI (LM Studio, Ollama, vLLM, OpenAI...)
- Opcional: una clave de [OpenRouter](https://openrouter.ai) para usar un modelo
  en la nube cuando el servidor local no responde

## Puesta en marcha

```bash
cp env-example.txt .env   # rellena las claves
uv sync
uv run python main.py     # http://127.0.0.1:8000
```

- Salud: <http://127.0.0.1:8000/health>
- UI (build de React servido por FastAPI): <http://127.0.0.1:8000/static/>
- Tests: `uv run pytest`

## Variables de entorno

Todas las secciones usan prefijos y están documentadas en `env-example.txt`.

| Sección | Prefijo | Claves |
|---|---|---|
| LLM | `LLM_` | `PROVIDER`, `BASE_URL`, `BASE_MODEL`, `API_KEY`, `TEMPERATURE`, `PROBE_TIMEOUT` |
| OpenRouter | `OPEN_ROUTER_` | `API_KEY` (o `OPEN_ROUTER`), `URL`, `MODEL`, `APP_TITLE`, `APP_URL` |
| AssemblyAI | `ASSEMBLYAI_` | `API_KEY`, `SPEECH_MODEL`, `ENCODING`, `MIN_TURN_SILENCE`, `MAX_TURN_SILENCE`, `END_OF_TURN_CONFIDENCE_THRESHOLD` |
| ElevenLabs | `ELEVENLABS_` | `API_KEY`, `VOICE_ID`, `MODEL_ID`, `OUTPUT_FORMAT`, `BASE_URL` |
| Voz | `VOICE_` | `MAX_SESSION_SECONDS`, `INPUT_SAMPLE_RATE` |
| Sesiones | `SESSION_` | `TTL_SECONDS`, `MAX_TURNS`, `DB_PATH` |
| Aprendizaje | `LEARNING_` | `ENABLED`, `TIMEOUT`, `MAX_CORRECTIONS`, `MAX_VOCABULARY` |
| App | `APP_` | `ENV`, `LOG_LEVEL`, `CORS_ORIGINS` |

`.env` está en `.gitignore`. **Nunca** subas claves al repositorio; si una se
filtró, rótala en el panel del proveedor.

### Proveedores del LLM

`LLM_PROVIDER` decide quién responde:

| Valor | Chat | Voz |
|---|---|---|
| `fallback` (por defecto) | Local primero; OpenRouter si falla **antes del primer token**. | Local si responde a una completion de prueba de 1 token; OpenRouter si no (servidor caído, sin modelo cargado o `LLM_BASE_MODEL` inexistente). |
| `local` | Solo el servidor OpenAI-compatible de `LLM_BASE_URL`. | Igual. |
| `openrouter` | Solo OpenRouter; sin credenciales falla al arrancar. | Igual. |

En voz, `fallback` no se fía de que el puerto esté abierto: antes de construir
el pipeline envía una completion de un token (`LLM_PROBE_TIMEOUT`, 4 s por
defecto). Si el servidor local no tiene un modelo cargado, `LLM_BASE_MODEL` no
existe o el modelo no responde, esa sesión usa OpenRouter. La decisión se toma
por sesión, así que cargar el modelo en LM Studio y volver a abrir la voz basta.

Mientras el servidor local responde, **no se envía nada a OpenRouter**. Si
`LLM_PROVIDER=fallback` y no hay credenciales, arranca solo con el local y deja
un aviso en el log.

`OPEN_ROUTER_URL` se valida contra el endpoint fijo de OpenRouter
(`https://openrouter.ai/api/v1`): ni pydantic-ai ni el servicio de Pipecat
aceptan otro, así que una URL distinta es un error (al arrancar el chat o al
abrir una sesión de voz) en vez de un ajuste ignorado. La clave se lee de `OPEN_ROUTER_API_KEY` o, por compatibilidad,
de `OPEN_ROUTER`.

> **Tier gratis**: los modelos acabados en `:free` están limitados a 20
> peticiones/minuto y 50/día (1000/día con ≥10 créditos comprados). Una sesión de
> voz larga los agota. En el chat, un 429 **a mitad de stream** no se puede
> reintentar en el modelo local: ese turno termina con `agent_error`.

## Correcciones, vocabulario y progreso

Cada mensaje del alumno (texto o voz) se analiza **en paralelo**, sin retrasar
la respuesta del coach, con un segundo `Agent` de pydantic-ai y salida
estructurada (`NativeOutput`). El prompt vive en `app/prompts/analyzer.md`.

- Devuelve como mucho dos correcciones y dos palabras por turno. Las
  explicaciones van en español.
- El chat emite un evento AG-UI `STATE_SNAPSHOT` antes de `RUN_FINISHED`; si el
  análisis tarda más que la espera corta del stream, el cliente consulta
  `GET /api/v1/threads/{id}/state` hasta que aparece.
- En voz, el servidor manda un mensaje RTVI `server-message` con
  `{type: "learning-state", state}` después de cada turno del asistente.
- El estado se guarda por `thread_id` en la misma base SQLite que el historial
  (tabla `learning`) y se reutiliza entre canales.
- Con `LLM_PROVIDER=fallback` el analizador usa **solo el modelo local**, para no
  gastar el cupo gratuito de OpenRouter con una llamada extra por turno.
- `LEARNING_TIMEOUT` (60 s por defecto) evita que un modelo local lento deje una
  tarea colgada. Un mensaje de una sola palabra no se analiza; el turno cuenta
  igual.

## Endpoints

### `POST /api/v1/chat`

Cuerpo `RunAgentInput` de AG-UI; respuesta `text/event-stream` de eventos AG-UI.
El historial se guarda en el servidor por `threadId` (el historial que envíe el
cliente tiene prioridad en ese turno). Antes de `RUN_FINISHED` llega un
`STATE_SNAPSHOT` con las correcciones, el vocabulario y el progreso.

### `GET /api/v1/threads/{thread_id}/messages`

Historial `[{role, content}]` guardado para el hilo, compartido por chat y voz.

### `GET /api/v1/threads/{thread_id}/state`

Correcciones, vocabulario y progreso del hilo. Devuelve un estado vacío para
hilos desconocidos.

### `DELETE /api/v1/threads/{thread_id}`

Borra historial y estado de aprendizaje (botón "Nueva" de la UI). `204`.

### `WS /api/v1/voice/{thread_id}`

Habla el protocolo **RTVI** de Pipecat sobre frames protobuf. No es un contrato
propio: lo implementa `@pipecat-ai/websocket-transport` y el servidor lo atiende
con `FastAPIWebsocketTransport` + `ProtobufFrameSerializer`.

- **Cliente → servidor**: audio PCM16 mono a `VOICE_INPUT_SAMPLE_RATE` (16 kHz),
  mensajes RTVI (`client-ready`, `client-message`, …) y el evento
  `client-message` con `type: "interrupt"` para el botón de interrupción.
- **Servidor → cliente**: audio PCM16 a la tasa de `ELEVENLABS_OUTPUT_FORMAT`
  (24 kHz con `pcm_24000`) y eventos RTVI (`user-transcript`,
  `bot-llm-text`, `bot-started-speaking`, `bot-stopped-speaking`, …), más un
  `server-message` con `{type: "learning-state", state}` tras cada turno.

El cliente fija esas dos tasas en
`frontend/src/shared/hooks/useVoiceSession.ts` (`INPUT_SAMPLE_RATE` y
`OUTPUT_SAMPLE_RATE`). Si cambias `VOICE_INPUT_SAMPLE_RATE` o
`ELEVENLABS_OUTPUT_FORMAT`, actualiza también esas constantes o el audio sonará
a la velocidad equivocada.

`PipelineWorker` instala el handshake `client-ready`/`bot-ready`
y el observer que emite las transcripciones. El audio nunca viaja en base64.

### Detección de turno ("medias" al hablar)

La detección de turno **no** la decide AssemblyAI: la decide Pipecat con
`SileroVADAnalyzer` para el inicio y `LocalSmartTurnAnalyzerV3` para el final.
El smart-turn es semántico: si el usuario hace una pausa a mitad de frase, el
turno sigue abierto y la respuesta llega entera.

`ASSEMBLYAI_MIN_TURN_SILENCE` (350 ms por defecto) se envía también como
`max_turn_silence` forzado (`vad_force_turn_endpoint=True`), para que AssemblyAI
no cierre turnos por su cuenta y compita con el smart-turn. Por eso
`ASSEMBLYAI_MAX_TURN_SILENCE` no tiene efecto en el modo por defecto; se conserva
para volver a la detección de AssemblyAI si hiciera falta.

> `ASSEMBLYAI_END_OF_TURN_CONFIDENCE_THRESHOLD` solo aplica a los modelos
> `universal-streaming-*`; con `universal-3-6-pro` se ignora.

## Estructura

```
app/
├── main.py                  # create_app(): routers, CORS, lifespan
├── core/
│   ├── config.py            # Settings anidados por proveedor
│   └── logging.py
├── api/
│   ├── deps.py
│   └── routes/
│       ├── health.py
│       ├── chat.py          # POST /api/v1/chat  (AG-UI)
│       ├── threads.py       # historial + estado de aprendizaje
│       └── voice.py         # WS   /api/v1/voice/{thread_id} (Pipecat/RTVI)
├── agents/
│   ├── model.py             # build_model()  (local + OpenRouter, fallback)
│   ├── deps.py              # AgentDeps
│   └── coach.py             # build_coach_agent()
├── learning/
│   ├── models.py            # LearningState, Correction, VocabularyItem
│   ├── analyzer.py          # segundo Agent + salida estructurada
│   ├── service.py           # analiza, fusiona y calcula el progreso
│   └── store.py             # persistencia por thread_id
├── prompts/
│   ├── coach.md             # instrucciones del agente
│   └── analyzer.md          # instrucciones del analizador
├── services/
│   └── voice/
│       ├── pipecat_pipeline.py  # transporte, servicios y PipelineTask
│       ├── llm.py               # selección local / OpenRouter / fallback
│       └── history.py           # SessionStore ⇄ contexto de Pipecat
└── sessions/store.py        # SessionStore, InMemory + SQLite
```

`sessions/store.py` y `learning/store.py` definen sendos `Protocol`: cambiar a
Redis no requiere tocar rutas ni el pipeline. El historial se comparte entre
chat y voz; los mensajes de Pipecat se convierten a `ModelMessage` al cerrar la
sesión. Con `SESSION_DB_PATH` definido, historial y aprendizaje se guardan en
SQLite (`backend/data/sessions.db` por defecto); si está vacío, en memoria.

## Notas de diseño

- **Barge-in**: lo gestiona Pipecat. La VAD detecta que el usuario empieza a
  hablar y emite un `InterruptionFrame`, que corta LLM y TTS. El botón
  "interrumpir" de la UI envía `sendClientMessage("interrupt")` y el servidor
  encola el mismo frame.
- **Contexto entre canales**: al abrir la sesión de voz se siembra el
  `LLMContext` con las instrucciones y el historial del `thread_id`; al cerrar se
  vuelve a guardar. Así una conversación puede empezar en chat y seguir por voz.
- **TTS**: `ElevenLabsDialogueTTSService` (modelos Eleven v3/v4) recibe el texto
  agregado por frases; la tasa de salida se pasa explícitamente desde
  `ELEVENLABS_OUTPUT_FORMAT` para que coincida con la que anuncia el transporte.
- **Persistencia**: el historial de voz se guarda al cerrar la sesión (o al
  alcanzar `VOICE_MAX_SESSION_SECONDS`). Los turnos son texto; las llamadas a la
  tool `get_current_datetime` no se replican porque son stateless.
- **Tool**: `get_current_datetime` está registrada tanto en el agente de chat
  (pydantic-ai) como en el servicio de voz (`llm.register_function`).

[pydantic-ai]: https://ai.pydantic.dev/
[Pipecat]: https://pipecat.ai/
[`@pipecat-ai/client-js`]: https://github.com/pipecat-ai/pipecat-client-web
