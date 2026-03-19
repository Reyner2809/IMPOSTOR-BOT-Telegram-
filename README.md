# El Impostor Bot

Bot de Telegram para jugar **El Impostor**, un juego social de deduccion estilo *Spyfall* donde los ciudadanos deben descubrir quien es el impostor entre ellos.

---

## Como funciona el juego

### Roles
- **Ciudadanos**: Reciben una **palabra secreta** (ej: "Guitarra"). Deben encontrar al impostor.
- **Impostores**: Reciben solo una **pista vaga** (ej: "Musica"). Deben pasar desapercibidos.

### Flujo de una partida

```
Lobby → Fase de Palabras → Discusion → Votacion → Resultados
                ↑                                      ↓
                └──────── Nueva ronda (si continua) ←──┘
```

1. **Lobby**: El creador arma la partida y los jugadores se unen.
2. **Fase de palabras**: Cada jugador dice por turnos una palabra relacionada con su palabra secreta. El impostor debe inventar algo convincente con solo su pista.
3. **Discusion**: Todos debaten libremente sobre quien podria ser el impostor basandose en las palabras dichas.
4. **Votacion**: Cada jugador vota por quien cree que es el impostor. Se puede cambiar el voto antes de que termine el tiempo.
5. **Resultados**: El mas votado es eliminado. Si era impostor, los ciudadanos ganan puntos. Si era ciudadano, el juego continua.

### Condiciones de victoria
- **Ciudadanos ganan**: Todos los impostores son eliminados.
- **Impostores ganan**: Los impostores igualan o superan en numero a los ciudadanos.

### Reglas importantes
- Los jugadores eliminados no pueden hablar ni votar.
- No se puede repetir una palabra que otro jugador ya dijo.
- La palabra secreta y la pista se mantienen durante toda la partida.
- Los votos son secretos pero se puede cambiar de voto.

---

## Comandos del bot

| Comando | Descripcion |
|---|---|
| `/start` | Mensaje de bienvenida y ayuda |
| `/crear_partida` | Crea una nueva partida en el grupo |
| `/unirse` | Unirse a la partida activa |
| `/salir` | Salir de la partida (solo en lobby) |
| `/iniciar` | Inicia la partida (solo el creador) |
| `/votar` | Muestra los botones de votacion |
| `/forzar_voto` | Salta la fase de palabras y va directo a votacion (solo el creador) |
| `/estado` | Ver estado actual de la partida |
| `/config` | Ver configuracion actual |
| `/config impostores <N>` | Configurar cantidad de impostores |
| `/config tiempo <segundos>` | Configurar tiempo de discusion (30-600s) |
| `/config categoria <nombre>` | Configurar categoria de palabras |
| `/cancelar` | Cancelar la partida (solo el creador) |
| `/finalizar` | Forzar fin de la partida |
| `/ayuda` | Ver ayuda |

---

## Instalacion local

### Requisitos
- Python 3.10 o superior
- Un bot de Telegram (creado con [@BotFather](https://t.me/BotFather))

### 1. Clonar el repositorio

```bash
git clone https://github.com/TU_USUARIO/el_impostor_bot.git
cd el_impostor_bot
```

### 2. Crear entorno virtual (recomendado)

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 4. Configurar variables de entorno

Crea un archivo `.env` en la raiz del proyecto:

```
BOT_TOKEN=TU_TOKEN_AQUI
GEMINI_API_KEY=TU_API_KEY_AQUI
UPSTASH_REDIS_REST_URL=https://tu-nombre.upstash.io
UPSTASH_REDIS_REST_TOKEN=tu_token_aqui
```

#### BOT_TOKEN (obligatorio)
Token que te dio [@BotFather](https://t.me/BotFather) al crear tu bot.

#### GEMINI_API_KEY (opcional)
Permite que la IA genere las palabras y pistas automaticamente en cada partida.

1. Ve a [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
2. Haz clic en **"Create API key"** → **"Create API key in new project"**
3. Copia la key generada

Si no la configuras, el bot usa las palabras del archivo `data/words.json` como fallback sin interrumpir el juego.

> En los logs veras `[PALABRAS DE IA]` cuando Gemini funciona correctamente, y `[PALABRAS DEL SISTEMA]` cuando usa el fallback (con el motivo del fallo).

#### UPSTASH_REDIS_REST_URL y UPSTASH_REDIS_REST_TOKEN (opcional, recomendado)
Permite que las palabras generadas por la IA no se repitan entre partidas, persistiendo el historial aunque el bot se reinicie. Usa HTTPS (puerto 443) por lo que funciona en cualquier servidor sin importar restricciones de firewall.

1. Crea una cuenta gratuita en [console.upstash.com](https://console.upstash.com)
2. Crea una base de datos → **Redis** → tipo **Regional**
3. En la seccion **"REST API"** copia la URL y el token

```
UPSTASH_REDIS_REST_URL=https://tu-nombre.upstash.io
UPSTASH_REDIS_REST_TOKEN=tu_token_aqui
```

Si no lo configuras, el historial de palabras se guarda en memoria y se pierde al reiniciar el bot.

### 5. Ejecutar

```bash
python bot.py
```

El bot deberia mostrar `Bot iniciando polling...` en la consola.

### 6. Configurar el bot en Telegram

1. Agrega el bot a un grupo de Telegram.
2. Dale permisos de **administrador** para que pueda borrar mensajes.
3. Usa `/crear_partida` en el grupo para empezar.

> **Importante**: Cada jugador debe enviar `/start` al bot en privado al menos una vez para que el bot pueda enviarle mensajes directos con su palabra secreta.

---

## Instalacion en servidor (produccion)

### Opcion 1: systemd (Linux)

```bash
# Copiar archivos al servidor
scp -r . usuario@servidor:/opt/el_impostor_bot/

# En el servidor
cd /opt/el_impostor_bot
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Crear el archivo de servicio `/etc/systemd/system/impostor-bot.service`:

```ini
[Unit]
Description=El Impostor Telegram Bot
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/el_impostor_bot
EnvironmentFile=/opt/el_impostor_bot/.env
ExecStart=/opt/el_impostor_bot/venv/bin/python bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable impostor-bot
sudo systemctl start impostor-bot
sudo systemctl status impostor-bot
```

### Opcion 2: Docker

Crear un `Dockerfile`:

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "bot.py"]
```

```bash
docker build -t impostor-bot .
docker run -d --name impostor-bot --env-file .env --restart unless-stopped impostor-bot
```

---

## Estructura del proyecto

```
el_impostor_bot/
├── bot.py                  # Punto de entrada, registra handlers
├── config.py               # Configuracion y carga de .env
├── models.py               # Modelos de datos (Game, Player, etc.)
├── game_manager.py         # Logica principal del juego
├── word_manager.py         # Gestion de palabras y categorias
├── gemini_manager.py       # Integracion con Gemini AI (genera palabras y pistas)
├── database.py             # Persistencia en SQLite
├── requirements.txt        # Dependencias
├── .env                    # Token del bot (no incluido en el repo)
├── data/
│   └── words.json          # Palabras y pistas por categoria
└── handlers/
    ├── create_game.py      # /crear_partida
    ├── join_game.py        # /unirse, /salir
    ├── config_game.py      # /config
    ├── start_game.py       # /iniciar, timers de ronda
    ├── word_phase_handler.py  # Control de turnos y palabras
    ├── vote_handler.py     # Votacion y procesamiento de rondas
    └── game_status.py      # /estado, /cancelar, /finalizar
```

---

## Categorias de palabras disponibles

El archivo `data/words.json` incluye palabras en las siguientes categorias:

- Animales
- Comida
- Lugares
- Objetos
- Profesiones
- Deportes
- Tecnologia
- Peliculas

Puedes agregar mas palabras editando el archivo JSON. Cada entrada tiene el formato:

```json
{
  "word": "Guitarra",
  "hint": "Musica"
}
```

---

## Tecnologias

- **Python 3.10+**
- **python-telegram-bot 21.6** con soporte de JobQueue (APScheduler)
- **aiosqlite** para persistencia asincrona en SQLite
- **google-genai** para generacion de palabras y pistas con Gemini AI (opcional, con fallback automatico)
- **upstash-redis** para tracking persistente de palabras usadas via Upstash REST API (opcional)
