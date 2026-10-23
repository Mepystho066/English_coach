# english-coach backend

Backend para un coach de inglés conversacional. Dos canales comparten un mismo
`Agent` de [pydantic-ai]:

- **Chat** — `POST /api/v1/chat`, contrato estándar **AG-UI** (SSE).
- **Voz** — `WS /api/v1/voice/{thread_id}`, streaming bidireccional con
  **AssemblyAI** (STT) y **ElevenLabs** (TTS).

Todo el pipeline es *streaming*: el audio entra por WebSocket, la transcripción
llega en parciales, el LLM emite deltas de texto y el TTS devuelve audio PCM que
se reenvía al cliente sin esperar al final del turno.

```
                 ┌───────────────────────────────────────────┐
  Chat texto ───►│ POST /api/v1/chat   (AG-UI estándar/SSE)  │
                 └───────────────────────────────────────────┘
                                   │
                            mismo Agent + SessionStore
                                   │
  ┌────────────────────────────────┴────────────────────────────────┐
  │ WS /api/v1/voice/{thread_id}   (eventos AG-UI + audio binario)  │
  │                                                                 │
  │  mic ─PCM16─► AssemblyAI v3 ──Turn──► turnos / barge-in         │
  │                                              │                  │
  │                                              ▼                  │
  │                       Agent.run_stream_events ──deltas──► TTS   │
  │                                              │        ElevenLabs│
  │                              eventos AG-UI ◄─┘                  │
  │                              audio PCM ◄─────────────────────── │
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
- Página de prueba de voz: <http://127.0.0.1:8000/static/test.html>
- Tests: `uv run pytest`

## Variables de entorno

Todas las secciones usan prefijos y están documentadas en `env-example.txt`.

| Sección | Prefijo | Claves |
|---|---|---|
| LLM | `LLM_` | `PROVIDER`, `BASE_URL`, `BASE_MODEL`, `API_KEY`, `TEMPERATURE` |
| OpenRouter | `OPEN_ROUTER_` | `API_KEY` (o `OPEN_ROUTER`), `URL`, `MODEL`, `APP_TITLE`, `APP_URL` |
| AssemblyAI | `ASSEMBLYAI_` | `API_KEY`, `SPEECH_MODEL`, `SAMPLE_RATE`, `ENCODING`, `MIN_TURN_SILENCE`, `MAX_TURN_SILENCE`, `END_OF_TURN_CONFIDENCE_THRESHOLD` |
| ElevenLabs | `ELEVENLABS_` | `API_KEY`, `VOICE_ID`, `MODEL_ID`, `OUTPUT_FORMAT`, `CHUNK_SCHEDULE` |
| Voz | `VOICE_` | `MAX_SESSION_SECONDS`, `INPUT_SAMPLE_RATE`, `OUTPUT_SAMPLE_RATE`, `BARGE_IN`, `TURN_GRACE_MS` |
| Sesiones | `SESSION_` | `TTL_SECONDS`, `MAX_TURNS` |
| App | `APP_` | `ENV`, `LOG_LEVEL`, `CORS_ORIGINS` |

`.env` está en `.gitignore`. **Nunca** subas claves al repositorio; si una se
filtró, rótala en el panel del proveedor.

### Proveedores del LLM

`LLM_PROVIDER` decide quién responde:

| Valor | Comportamiento |
|---|---|
| `fallback` (por defecto) | Servidor local primero; OpenRouter solo si la petición falla **antes del primer token** (servidor apagado, timeout, 4xx/5xx). |
| `local` | Solo el servidor OpenAI-compatible de `LLM_BASE_URL`. |
| `openrouter` | Solo OpenRouter; si faltan credenciales falla al arrancar, no en el primer turno. |

Mientras el servidor local responde, **no se envía nada a OpenRouter**. Si
`LLM_PROVIDER=fallback` y no hay credenciales, arranca solo con el local y deja
un aviso en el log.

`OPEN_ROUTER_URL` se valida contra el endpoint fijo de OpenRouter
(`https://openrouter.ai/api/v1`): el proveedor de pydantic-ai no permite otro, así
que una URL distinta es un error de arranque en vez de un ajuste ignorado. La
clave se lee de `OPEN_ROUTER_API_KEY` o, por compatibilidad, de `OPEN_ROUTER`.

> **Tier gratis**: los modelos acabados en `:free` están limitados a 20
> peticiones/minuto y 50/día (1000/día con ≥10 créditos comprados). Una sesión de
> voz larga los agota. Un 429 **a mitad de stream** no se puede reintentar en el
> modelo local: ese turno termina con `agent_error`.

## Endpoints

### `POST /api/v1/chat`

Cuerpo `RunAgentInput` de AG-UI; respuesta `text/event-stream` de eventos AG-UI.
El historial se guarda en el servidor por `threadId` (el historial que envíe el
cliente tiene prioridad en ese turno).

### `WS /api/v1/voice/{thread_id}`

**Cliente → servidor**

| Frame | Contenido |
|---|---|
| binario | PCM16 mono, `INPUT_SAMPLE_RATE` (16 kHz por defecto) |
| `{"type":"session.start","sampleRate":16000}` | Inicia la sesión de STT |
| `{"type":"text","text":"..."}` | Ejercita el pipeline sin micrófono |
| `{"type":"response.interrupt"}` | Corta la respuesta en curso |
| `{"type":"session.stop"}` | Cierra la sesión |

**Servidor → cliente**

| Frame | Contenido |
|---|---|
| texto | Eventos **AG-UI**: `RUN_STARTED`, `TEXT_MESSAGE_START/CONTENT/END`, `RUN_FINISHED`, `RUN_ERROR` |
| texto | `CUSTOM` con los nombres `voice.transcript`, `voice.audio.start`, `voice.audio.end`, `voice.interrupted`, `voice.listening`, `voice.session.end` |
| binario | PCM16 mono a `OUTPUT_SAMPLE_RATE` (24 kHz por defecto) |

`voice.audio.start` anuncia `format`, `sampleRate` y `channels` de los frames
binarios que vienen a continuación. El audio nunca viaja en base64.

### Detección de turno ("medias" al hablar)

AssemblyAI cierra un turno en cuanto detecta `MIN_TURN_SILENCE` ms de silencio, y
envía **solo el texto de ese turno**. Si el usuario piensa a mitad de frase, esa
frase llega troceada:

```
"I went to the"  →  "market yesterday"  →  "and bought some fruit"
```

Sin protección, cada trozo dispara su propio turno del LLM y el nuevo **cancela**
al anterior, así que el coach responde solo al último trozo y los anteriores no
llegan ni al historial. Lo mismo se veía en pantalla, porque el transcript se
reemplazaba entero.

Tres ajustes lo evitan:

| Variable | Efecto |
|---|---|
| `ASSEMBLYAI_MIN_TURN_SILENCE` | Cuánto silencio exige AssemblyAI antes de cerrar el turno. `120` ms es demasiado bajo; usa `300`–`400`. |
| `ASSEMBLYAI_MAX_TURN_SILENCE` | Techo: cierra el turno tras ese silencio aunque no haya punto. |
| `VOICE_TURN_GRACE_MS` | Tiempo extra que el pipeline sigue acumulando fragmentos antes de responder. Cada fragmento nuevo reinicia el temporizador. |

Con `350` + `500` el coach empieza a hablar tras ~850 ms de silencio real: una
pausa normal ya no parte la frase, y una pausa larga sí cierra el turno.

`voice.transcript` incluye `text` (turno actual del proveedor) y `utterance`
(todo lo acumulado desde la última respuesta). El cliente debe pintar `utterance`.

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
│       └── voice.py         # WS   /api/v1/voice/{thread_id}
├── agents/
│   ├── model.py             # build_model()  (local + OpenRouter, fallback)
│   ├── deps.py              # AgentDeps
│   └── coach.py             # build_coach_agent()
├── prompts/coach.md         # instrucciones del agente
├── schemas/voice.py         # contrato del WebSocket
├── services/
│   ├── stt/{base,assemblyai}.py
│   ├── tts/{base,elevenlabs}.py
│   └── voice/{pipeline,factory}.py
└── sessions/store.py        # SessionStore + InMemorySessionStore
```

`sessions/store.py` define un `Protocol`: cambiar a Redis o SQLite no requiere
tocar rutas ni pipeline. Igual para `StreamingSTT` / `StreamingTTS`, lo que
permite testear con dobles (ver `tests/fakes.py`).

## Notas de diseño

- **Barge-in**: cualquier `SpeechStarted` de AssemblyAI mientras el asistente
  habla cancela el turno, cierra el contexto de TTS y emite
  `voice.interrupted`. El navegador debe usar `echoCancellation: true` para no
  re-transcribir el TTS.
- **Agregación de utterance**: los `final` del STT se acumulan en
  `_pending_text` y solo se responden cuando pasa `VOICE_TURN_GRACE_MS` sin uno
  nuevo. Así una frase con pausas produce una sola respuesta en vez de varias
  que se cancelan entre sí. El barge-in descarta lo acumulado para que la frase
  interrumpida no se mezcle con la siguiente.
- **Agregación de utterance**: los `final` del STT se acumulan en
  `_pending_text` y solo se responden cuando pasa `VOICE_TURN_GRACE_MS` sin uno
  nuevo. Así una frase con pausas produce una sola respuesta en vez de varias
  que se cancelan entre sí. El barge-in descarta lo acumulado para que la frase
  interrumpida no se mezcle con la siguiente.
- **Troceo del TTS**: los deltas del LLM se acumulan y se envían a ElevenLabs en
  límites de frase, con `auto_mode` y un `chunk_length_schedule` bajo para
  minimizar el tiempo hasta el primer byte.
- **Cancelación**: cada turno vive en su propio `asyncio.Task`; interrumpir
  cancela el task y espera su limpieza antes de empezar el siguiente.
- **Persistencia en voz**: lo que dice el usuario se guarda **antes** de correr
  el LLM, así que un barge-in nunca lo borra. Si la respuesta se corta a medias,
  el texto ya emitido se guarda como respuesta parcial (`_save_partial`): el
  modelo ve que habló y puede retomar. Antes, un turno cancelado hacía `raise`
  sin llamar a `set_history`, y con varios barge-ins seguidos la conversación
  perdía el hilo por completo.

[pydantic-ai]: https://ai.pydantic.dev/


## Seleccionar LLM_Provider 

Mientras LM Studio responda, no sale nada hacia OpenRouter.Mientras LM Studio responda, no sale nada hacia OpenRouter.

|Valor| Comportamiento|
|------|--------------|
|fallback|	LM Studio primero; OpenRouter solo si la petición falla antes del primer token|
|local   |	solo LM Studio (como antes)|
|openrouter|	solo OpenRouter; sin credenciales falla al arrancar|
