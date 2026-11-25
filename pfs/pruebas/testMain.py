import os
from pathlib import Path
import random
import requests
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse


def cargarEnv():
    for ruta in [Path(__file__).parent / ".env", Path(__file__).resolve().parents[1] / "final" / ".env"]:
        if ruta.exists():
            for linea in ruta.read_text().splitlines():
                linea = linea.strip()
                if linea and not linea.startswith("#") and "=" in linea:
                    clave, valor = linea.split("=", 1)
                    os.environ[clave.strip()] = valor.strip()
            break


cargarEnv()

app = FastAPI()

BOT_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID = os.getenv("MI_CHAT_ID", "")


def enviarTelegram(casillero: int, pin: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    mensaje = f"📦 *LOCKER #{casillero}*\nTu PIN de retiro es: `{pin}`"
    requests.post(url, data={"chat_id": CHAT_ID, "text": mensaje, "parse_mode": "Markdown"})


@app.get("/deposito", response_class=HTMLResponse)
def formularioDeposito():
    # Formulario HTML simple que ve el repartidor en su celular
    return """
    <html>
        <body style="font-family: Arial; padding: 20px;">
            <h2>Módulo Repartidor - Smart Campus Locker</h2>
            <form action="/api/v1/deposito" method="post">
                <label>Selecciona Casillero:</label><br>
                <select name="lockerId">
                    <option value="1">Locker 1</option>
                    <option value="2">Locker 2</option>
                </select><br><br>
                <button type="submit" style="padding: 10px 20px; background: #007bff; color: white; border: none;">Confirmar Depósito</button>
            </form>
        </body>
    </html>
    """


@app.post("/api/v1/deposito")
def procesarDeposito(lockerId: int = Form(...)):
    # 1. Generar PIN aleatorio
    pinGenerado = str(random.randint(1000, 9999))

    # 2. Enviar notificación por Telegram
    enviarTelegram(lockerId, pinGenerado)

    return {"status": "OK", "mensaje": f"Depósito en Locker {lockerId} exitoso. Notificación enviada."}
