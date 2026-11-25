import os
from pathlib import Path
import random
import threading
import time
import requests
import uvicorn
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse
from gpiozero import DigitalInputDevice, OutputDevice
from mfrc522 import SimpleMFRC522
from RPLCD.i2c import CharLCD


def cargarEnv():
    envPath = Path(__file__).parent / ".env"
    if envPath.exists():
        for linea in envPath.read_text().splitlines():
            linea = linea.strip()
            if linea and not linea.startswith("#") and "=" in linea:
                clave, valor = linea.split("=", 1)
                os.environ[clave.strip()] = valor.strip()


cargarEnv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
MI_CHAT_ID = os.getenv("MI_CHAT_ID", "")

DIRECTORIO_USUARIOS = {
    "202410643": {
        "nombre": "Ana (Tarjeta blanca)",
        "uid": int(os.getenv("UID_ANA", "0")),
        "chatId": MI_CHAT_ID,
    },
    "202410839": {
        "nombre": "Carlos (Llavero azul)",
        "uid": int(os.getenv("UID_CARLOS", "0")),
        "chatId": MI_CHAT_ID,
    },
}

#reles activos en LOW
PINES_RELES = {
    1: 18,
    2: 23,
    3: 24,
}
reles = {
    num: OutputDevice(pin, active_high=False, initial_value=False)
    for num, pin in PINES_RELES.items()
}

FILAS = [12, 16, 20, 21]
COLUMNAS = [5, 6, 13, 19]
TECLAS = [
    ["1", "2", "3", "A"],
    ["4", "5", "6", "B"],
    ["7", "8", "9", "C"],
    ["*", "0", "#", "D"],
]
filasOut = [OutputDevice(p, initial_value=True) for p in FILAS]
colsIn = [DigitalInputDevice(p, pull_up=True) for p in COLUMNAS]

#lcd direccion 0x27
try:
    lcd = CharLCD(i2c_expander="PCF8574", address=0x27, port=1, cols=16, rows=2)
except Exception as e:
    print(f"[ADVERTENCIA] LCD no detectada: {e}")
    lcd = None

lectorRfid = SimpleMFRC522()

lockSistema = threading.Lock()

estadoLockers = {
    1: {"ocupado": False, "pin": None, "uid": None, "usuario": None},
    2: {"ocupado": False, "pin": None, "uid": None, "usuario": None},
    3: {"ocupado": False, "pin": None, "uid": None, "usuario": None},
}

intentosFallidos = 0
bloqueadoHasta = 0.0
ultimoTextoLcd = ("", "")
abriendoPuerta = False

SEGUNDOS_24H = 86400
pinMaestroActual = ""
pinMaestroExpira = 0.0


def escribirLcd(linea1: str, linea2: str = ""):
    global ultimoTextoLcd
    l1 = linea1[:16].ljust(16)
    l2 = linea2[:16].ljust(16)

    #solo actualiza si cambio el texto
    if (l1, l2) != ultimoTextoLcd:
        ultimoTextoLcd = (l1, l2)
        if lcd:
            try:
                lcd.cursor_pos = (0, 0)
                lcd.write_string(l1)
                lcd.cursor_pos = (1, 0)
                lcd.write_string(l2)
            except Exception as e:
                print(f"[Error I2C LCD]: {e}")
        print(f"[LCD] {linea1} | {linea2}")


def enviarTelegram(chatId: str, mensaje: str):
    if not TELEGRAM_TOKEN or "TU_BOT" in TELEGRAM_TOKEN:
        print(f"[Telegram Simulado -> {chatId}]: {mensaje}")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": chatId, "text": mensaje}, timeout=5)
    except Exception as e:
        print(f"[Error Telegram]: {e}")


def generarPinUnico() -> str:
    pinesActivos = {
        info["pin"] for info in estadoLockers.values() if info["ocupado"]
    }
    if pinMaestroActual:
        pinesActivos.add(pinMaestroActual)
    while True:
        nuevo = str(random.randint(1000, 9999))
        if nuevo not in pinesActivos:
            return nuevo


def verificarRotacionPinMaestro():
    #renueva pin maestro cada 24h
    global pinMaestroActual, pinMaestroExpira
    ahora = time.time()
    if ahora >= pinMaestroExpira or not pinMaestroActual:
        with lockSistema:
            nuevoMaestro = generarPinUnico()
            pinMaestroActual = nuevoMaestro
            pinMaestroExpira = ahora + SEGUNDOS_24H

        print(f"[SEGURIDAD] PIN Maestro activo (valido 24h): {pinMaestroActual}")
        enviarTelegram(
            MI_CHAT_ID,
            f"🛡️ Smart Campus Locker - PIN Maestro\n"
            f"Nuevo código maestro (válido por 24 horas): {pinMaestroActual}\n"
            f"Abre los 3 casilleros secuencialmente para mantenimiento.",
        )


def abrirCasillero(lockerId: int, metodo: str):
    #activa solenoide 5 seg
    escribirLcd(f"Acceso {metodo}", f"Abriendo L-{lockerId}")
    reles[lockerId].on()
    time.sleep(5)
    reles[lockerId].off()
    escribirLcd(f"Locker {lockerId} Libre", "Cierre la puerta")
    time.sleep(2)


def leerTecla():
    for rIdx, fOut in enumerate(filasOut):
        fOut.off()
        for cIdx, cIn in enumerate(colsIn):
            if cIn.is_active:
                #antirrebote
                time.sleep(0.04)
                while cIn.is_active:
                    time.sleep(0.01)
                fOut.on()
                return TECLAS[rIdx][cIdx]
        fOut.on()
    return None


def bucleHmiFisico():
    global intentosFallidos, bloqueadoHasta
    bufferPin = ""

    while True:
        ahora = time.time()

        #bloqueo por 3 intentos fallidos
        if ahora < bloqueadoHasta:
            restante = int(bloqueadoHasta - ahora) + 1
            escribirLcd("SISTEMA BLOQUEADO", f"Espere {restante} seg...")
            time.sleep(0.25)
            continue

        if bufferPin == "":
            escribirLcd("Smart Locker UNI", "Tarjeta o PIN:")
        else:
            escribirLcd("Ingrese PIN + #", f"PIN: {'*' * len(bufferPin)}")

        #lectura rfid sin bloquear
        uidLeido, _ = lectorRfid.read_no_block()
        if uidLeido:
            lockerAutorizado = None
            with lockSistema:
                for num, info in estadoLockers.items():
                    if info["ocupado"] and info["uid"] == uidLeido:
                        lockerAutorizado = num
                        #un solo uso
                        info["ocupado"] = False
                        info["pin"] = None
                        info["uid"] = None
                        info["usuario"] = None
                        break

            if lockerAutorizado:
                intentosFallidos = 0
                bufferPin = ""
                abrirCasillero(lockerAutorizado, "RFID OK")
            else:
                escribirLcd("Tarjeta Invalida", "Sin paquete")
                time.sleep(2)
            continue

        #lectura teclado 4x4
        tecla = leerTecla()
        if tecla:
            if tecla == "*":
                bufferPin = ""
            elif tecla == "#":
                if len(bufferPin) == 4:
                    lockerAutorizado = None
                    with lockSistema:
                        for num, info in estadoLockers.items():
                            if info["ocupado"] and info["pin"] == bufferPin:
                                lockerAutorizado = num
                                #un solo uso
                                info["ocupado"] = False
                                info["pin"] = None
                                info["uid"] = None
                                info["usuario"] = None
                                break

                    if lockerAutorizado:
                        intentosFallidos = 0
                        bufferPin = ""
                        abrirCasillero(lockerAutorizado, "PIN OK")
                    else:
                        intentosFallidos += 1
                        bufferPin = ""
                        if intentosFallidos >= 3:
                            bloqueadoHasta = time.time() + 30
                            intentosFallidos = 0
                            escribirLcd("3 Intentos Fail", "Bloqueado 30s")
                            time.sleep(1.5)
                        else:
                            escribirLcd("PIN Incorrecto", f"Intento {intentosFallidos}/3")
                            time.sleep(2)
                else:
                    escribirLcd("PIN Incompleto", "Use 4 digitos")
                    time.sleep(1.5)
            elif tecla.isdigit() and len(bufferPin) < 4:
                bufferPin += tecla

        time.sleep(0.02)


app = FastAPI(title="Smart Campus Locker - 3 Casilleros")


@app.get("/", response_class=HTMLResponse)
@app.get("/deposito", response_class=HTMLResponse)
def vistaDeposito(mensaje: str = "", error: str = ""):
    with lockSistema:
        filasEstado = ""
        opcionesLocker = ""
        for num, info in estadoLockers.items():
            badge = (
                "<span style='color:#dc3545;font-weight:bold;'>OCUPADO</span>"
                if info["ocupado"]
                else "<span style='color:#28a745;font-weight:bold;'>DISPONIBLE</span>"
            )
            dest = info["usuario"] if info["ocupado"] else "—"
            filasEstado += f"<tr><td>Locker {num}</td><td>{badge}</td><td>{dest}</td></tr>"
            if not info["ocupado"]:
                opcionesLocker += f"<option value='{num}'>Casillero {num} (Libre)</option>"

    if not opcionesLocker:
        opcionesLocker = "<option value='' disabled selected>Todos los casilleros ocupados</option>"

    opcionesUsuarios = "".join(
        f"<option value='{mat}'>{mat} - {datos['nombre']}</option>"
        for mat, datos in DIRECTORIO_USUARIOS.items()
    )

    alertaHtml = ""
    if mensaje:
        alertaHtml = f"<div style='background:#d4edda;color:#155724;padding:12px;border-radius:6px;margin-bottom:15px;'>✅ {mensaje}</div>"
    elif error:
        alertaHtml = f"<div style='background:#f8d7da;color:#721c24;padding:12px;border-radius:6px;margin-bottom:15px;'>⚠️ {error}</div>"

    return f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Smart Campus Locker</title>
        <style>
            body {{ font-family: Arial, sans-serif; max-width: 520px; margin: 25px auto; padding: 15px; background: #f4f6f9; }}
            .card {{ background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); margin-bottom: 20px; }}
            h2 {{ margin-top: 0; color: #1f2937; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
            th, td {{ padding: 10px; border-bottom: 1px solid #e5e7eb; text-align: left; }}
            label {{ font-weight: bold; display: block; margin-top: 12px; }}
            select, button {{ width: 100%; padding: 10px; margin-top: 6px; border-radius: 6px; border: 1px solid #cbd5e1; font-size: 15px; }}
            button {{ background: #0066cc; color: white; border: none; font-weight: bold; cursor: pointer; margin-top: 18px; }}
            button:hover {{ background: #0052a3; }}
        </style>
    </head>
    <body>
        <div class="card">
            <h2>📦 Smart Campus Locker</h2>
            {alertaHtml}
            <form action="/api/v1/deposito" method="post">
                <label>1. Selecciona Casillero Disponible:</label>
                <select name="lockerId" required>{opcionesLocker}</select>

                <label>2. Destinatario (Alumno / Personal):</label>
                <select name="matricula" required>{opcionesUsuarios}</select>

                <button type="submit">Confirmar Depósito y Notificar</button>
            </form>
        </div>

        <div class="card">
            <h3>Estado en Tiempo Real</h3>
            <table>
                <tr><th>Casillero</th><th>Estado</th><th>Asignado a</th></tr>
                {filasEstado}
            </table>
        </div>
    </body>
    </html>
    """


@app.post("/api/v1/deposito", response_class=HTMLResponse)
def procesarDeposito(lockerId: int = Form(...), matricula: str = Form(...)):
    if matricula not in DIRECTORIO_USUARIOS:
        return vistaDeposito(error="Matrícula no registrada en el sistema.")

    usuario = DIRECTORIO_USUARIOS[matricula]

    with lockSistema:
        if lockerId not in estadoLockers:
            return vistaDeposito(error="Número de casillero inválido.")
        if estadoLockers[lockerId]["ocupado"]:
            return vistaDeposito(
                error=f"El Casillero {lockerId} ya fue ocupado por otra solicitud."
            )

        pinNuevo = generarPinUnico()
        estadoLockers[lockerId] = {
            "ocupado": True,
            "pin": pinNuevo,
            "uid": usuario["uid"],
            "usuario": usuario["nombre"],
        }

    textoTg = (
        f"📦 Smart Campus Locker\n"
        f"Hola {usuario['nombre']}, tienes un paquete en el Casillero #{lockerId}.\n"
        f"🔑 PIN de retiro: {pinNuevo}\n"
        f"💳 También puedes abrirlo acercando tu credencial RFID al lector."
    )
    enviarTelegram(usuario["chatId"], textoTg)

    return vistaDeposito(
        mensaje=f"Paquete guardado en Locker {lockerId} para {usuario['nombre']}. Notificación enviada."
    )


@app.get("/api/v1/estado")
def obtenerEstadoJson():
    with lockSistema:
        return estadoLockers


if __name__ == "__main__":
    print("=== INICIANDO SMART CAMPUS LOCKER (3 CASILLEROS) ===")
    hiloHardware = threading.Thread(target=bucleHmiFisico, daemon=True)
    hiloHardware.start()

    try:
        uvicorn.run(app, host="0.0.0.0", port=8000)
    finally:
        #apaga reles y limpia lcd al salir
        for r in reles.values():
            r.off()
        if lcd:
            lcd.clear()
        print("\nSistema apagado y relés liberados de forma segura.")
