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

# ==============================================================================
# 1. CONFIGURACIÓN DE TELEGRAM Y DIRECTORIO DE USUARIOS (CAMPUS)
# ==============================================================================
TELEGRAM_TOKEN = "TU_TOKEN_AQUI"
MI_CHAT_ID = "9192586632"

DIRECTORIO_USUARIOS = {
    "2021001": {
        "nombre": "Ana (Tarjeta Blanca)",
        "uid": 594224296549,
        "chat_id": MI_CHAT_ID,
    },
    "2021002": {
        "nombre": "Carlos (Llavero Azul)",
        "uid": 835502292650,
        "chat_id": MI_CHAT_ID,
    },
}

# ==============================================================================
# 2. CONFIGURACIÓN DE HARDWARE (RASPBERRY PI 5)
# ==============================================================================
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
filas_out = [OutputDevice(p, initial_value=True) for p in FILAS]
cols_in = [DigitalInputDevice(p, pull_up=True) for p in COLUMNAS]

try:
    lcd = CharLCD(i2c_expander="PCF8574", address=0x27, port=1, cols=16, rows=2)
except Exception as e:
    print(f"[ADVERTENCIA] LCD no detectada: {e}")
    lcd = None

lector_rfid = SimpleMFRC522()

# ==============================================================================
# 3. ESTADO GLOBAL DEL SISTEMA Y SEGURIDAD (THREAD-SAFE)
# ==============================================================================
lock_sistema = threading.Lock()

estado_lockers = {
    1: {"ocupado": False, "pin": None, "uid": None, "usuario": None, "chat_id": None, "ultimo_aviso": 0.0},
    2: {"ocupado": False, "pin": None, "uid": None, "usuario": None, "chat_id": None, "ultimo_aviso": 0.0},
    3: {"ocupado": False, "pin": None, "uid": None, "usuario": None, "chat_id": None, "ultimo_aviso": 0.0},
}

intentos_fallidos = 0
bloqueado_hasta = 0.0
ultimo_texto_lcd = ("", "")
abriendo_puerta = False

# Configuración del PIN Maestro Dinámico (24 horas = 86400 segundos)
SEGUNDOS_24H = 86400
pin_maestro_actual = ""
pin_maestro_expira = 0.0

# Intervalo de recordatorios de retiro (15 minutos = 900 segundos)
INTERVALO_RECORDATORIO = 15 * 60


# ==============================================================================
# 4. FUNCIONES DE CONTROL FÍSICO Y NOTIFICACIONES
# ==============================================================================
def escribir_lcd(linea1: str, linea2: str = ""):
    """Actualiza la pantalla LCD solo si el texto cambió."""
    global ultimo_texto_lcd
    l1 = linea1[:16].ljust(16)
    l2 = linea2[:16].ljust(16)

    if (l1, l2) != ultimo_texto_lcd:
        ultimo_texto_lcd = (l1, l2)
        if lcd:
            try:
                lcd.cursor_pos = (0, 0)
                lcd.write_string(l1)
                lcd.cursor_pos = (1, 0)
                lcd.write_string(l2)
            except Exception as e:
                print(f"[Error I2C LCD]: {e}")
        print(f"[LCD] {linea1} | {linea2}")


def enviar_telegram(chat_id: str, mensaje: str):
    """Envía notificación por Telegram."""
    if not TELEGRAM_TOKEN or "TU_BOT" in TELEGRAM_TOKEN:
        print(f"[Telegram Simulado -> {chat_id}]: {mensaje}")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": chat_id, "text": mensaje}, timeout=5)
    except Exception as e:
        print(f"[Error Telegram]: {e}")


def generar_pin_unico() -> str:
    """Genera un PIN de 4 dígitos que no esté en uso ni coincida con el PIN maestro."""
    pines_activos = {
        info["pin"] for info in estado_lockers.values() if info["ocupado"]
    }
    if pin_maestro_actual:
        pines_activos.add(pin_maestro_actual)
    while True:
        nuevo = str(random.randint(1000, 9999))
        if nuevo not in pines_activos:
            return nuevo


def generar_pin_maestro() -> str:
    """Genera un PIN maestro de 4 caracteres con al menos una letra (A-D)."""
    caracteres = [
        random.choice("ABCD"),
        random.choice("0123456789"),
        random.choice("0123456789"),
        random.choice("0123456789"),
    ]
    random.shuffle(caracteres)
    return "".join(caracteres)


def verificar_rotacion_pin_maestro():
    """Genera o renueva el PIN maestro cada 24 horas y notifica al administrador."""
    global pin_maestro_actual, pin_maestro_expira
    ahora = time.time()
    if ahora >= pin_maestro_expira or not pin_maestro_actual:
        with lock_sistema:
            nuevo_maestro = generar_pin_maestro()
            pin_maestro_actual = nuevo_maestro
            pin_maestro_expira = ahora + SEGUNDOS_24H

        print(f"[SEGURIDAD] PIN Maestro activo (valido 24h): {pin_maestro_actual}")
        enviar_telegram(
            MI_CHAT_ID,
            f"🛡️ Smart Campus Locker - PIN Maestro\n"
            f"Nuevo código maestro (válido por 24 horas): {pin_maestro_actual}\n"
            f"Abre los 3 casilleros secuencialmente para mantenimiento.",
        )


def verificar_recordatorios():
    """Envía un recordatorio por Telegram cada 15 min si el paquete sigue sin retirarse."""
    ahora = time.time()
    avisos_pendientes = []

    with lock_sistema:
        for num, info in estado_lockers.items():
            if info["ocupado"] and (ahora - info["ultimo_aviso"]) >= INTERVALO_RECORDATORIO:
                info["ultimo_aviso"] = ahora
                avisos_pendientes.append(
                    (num, info["usuario"], info["pin"], info["chat_id"])
                )

    for num, usuario, pin, chat_id in avisos_pendientes:
        if chat_id:
            texto = (
                f"⏰ Recordatorio - Smart Mondradrop\n"
                f"Hola {usuario}, tu paquete sigue esperando en el Casillero #{num}.\n"
                f"🔑 PIN de retiro: {pin}\n"
                f"💳 También puedes abrirlo con tu credencial RFID."
            )
            threading.Thread(
                target=enviar_telegram, args=(chat_id, texto), daemon=True
            ).start()
            print(f"[RECORDATORIO] Enviado a {usuario} (Locker #{num})")


def abrir_casillero(locker_id: int, metodo: str):
    """Activa el solenoide correspondiente durante 10 segundos."""
    global abriendo_puerta
    abriendo_puerta = True
    try:
        escribir_lcd(f"Acceso {metodo}", f"Abriendo L-{locker_id}")
        reles[locker_id].on()
        time.sleep(10)
        reles[locker_id].off()
        escribir_lcd(f"Locker {locker_id} Listo", "Cierre la puerta")
        time.sleep(2)
    finally:
        abriendo_puerta = False


def abrir_todos_casilleros():
    """Abre los 3 casilleros uno tras otro (10s c/u) para no sobrecargar la fuente de 3A."""
    global abriendo_puerta
    abriendo_puerta = True
    try:
        for num in sorted(reles.keys()):
            escribir_lcd("PIN MAESTRO OK", f"Abriendo L-{num}")
            reles[num].on()
            time.sleep(10)
            reles[num].off()
        escribir_lcd("Revision Lista", "Cierre puertas")
        time.sleep(2)
    finally:
        abriendo_puerta = False


def leer_tecla():
    """Escanea la matriz 4x4 sin bloquear el hilo."""
    for r_idx, f_out in enumerate(filas_out):
        f_out.off()
        for c_idx, c_in in enumerate(cols_in):
            if c_in.is_active:
                time.sleep(0.04)
                while c_in.is_active:
                    time.sleep(0.01)
                f_out.on()
                return TECLAS[r_idx][c_idx]
        f_out.on()
    return None


# ==============================================================================
# 5. BUCLE DE HARDWARE EN SEGUNDO PLANO (TECLADO + RFID + SEGURIDAD)
# ==============================================================================
def bucle_hmi_fisico():
    global intentos_fallidos, bloqueado_hasta
    buffer_pin = ""

    while True:
        # Verificar rotación del PIN maestro (24h) y recordatorios de retiro (15 min)
        verificar_rotacion_pin_maestro()
        verificar_recordatorios()

        # Si una puerta se está abriendo (por web, PIN o RFID), pausar refresco de reposo en LCD
        if abriendo_puerta:
            time.sleep(0.1)
            continue

        ahora = time.time()

        # A. Bloqueo de seguridad por 3 intentos fallidos
        if ahora < bloqueado_hasta:
            restante = int(bloqueado_hasta - ahora) + 1
            escribir_lcd("SISTEMA BLOQUEADO", f"Espere {restante} seg...")
            time.sleep(0.25)
            continue

        # B. Pantalla de reposo o progreso de PIN
        if buffer_pin == "":
            escribir_lcd("Smart Locker UNI", "Tarjeta o PIN:")
        else:
            escribir_lcd("Ingrese PIN + #", f"PIN: {'*' * len(buffer_pin)}")

        # C. Lectura dinámica de RFID
        uid_leido, _ = lector_rfid.read_no_block()
        if uid_leido:
            locker_autorizado = None
            with lock_sistema:
                for num, info in estado_lockers.items():
                    if info["ocupado"] and info["uid"] == uid_leido:
                        locker_autorizado = num
                        info["ocupado"] = False
                        info["pin"] = None
                        info["uid"] = None
                        info["usuario"] = None
                        info["chat_id"] = None
                        info["ultimo_aviso"] = 0.0
                        break

            if locker_autorizado:
                intentos_fallidos = 0
                buffer_pin = ""
                abrir_casillero(locker_autorizado, "RFID OK")
            else:
                escribir_lcd("Tarjeta Invalida", "Sin paquete")
                time.sleep(2)
            continue

        # D. Lectura de Teclado Matricial 4x4
        tecla = leer_tecla()
        if tecla:
            if tecla == "*":
                buffer_pin = ""
            elif tecla == "#":
                if len(buffer_pin) == 4:
                    # 1. Validar si es el PIN Maestro de 24h
                    if buffer_pin == pin_maestro_actual:
                        intentos_fallidos = 0
                        buffer_pin = ""
                        abrir_todos_casilleros()
                        continue

                    # 2. Validar si corresponde a algún casillero ocupado
                    locker_autorizado = None
                    with lock_sistema:
                        for num, info in estado_lockers.items():
                            if info["ocupado"] and info["pin"] == buffer_pin:
                                locker_autorizado = num
                                info["ocupado"] = False
                                info["pin"] = None
                                info["uid"] = None
                                info["usuario"] = None
                                info["chat_id"] = None
                                info["ultimo_aviso"] = 0.0
                                break

                    if locker_autorizado:
                        intentos_fallidos = 0
                        buffer_pin = ""
                        abrir_casillero(locker_autorizado, "PIN OK")
                    else:
                        intentos_fallidos += 1
                        buffer_pin = ""
                        if intentos_fallidos >= 3:
                            bloqueado_hasta = time.time() + 30
                            intentos_fallidos = 0
                            escribir_lcd("3 Intentos Fail", "Bloqueado 30s")
                            time.sleep(1.5)
                        else:
                            escribir_lcd("PIN Incorrecto", f"Intento {intentos_fallidos}/3")
                            time.sleep(2)
                else:
                    escribir_lcd("PIN Incompleto", "Use 4 digitos")
                    time.sleep(1.5)
            elif tecla in "0123456789ABCD" and len(buffer_pin) < 4:
                buffer_pin += tecla

        time.sleep(0.02)


# ==============================================================================
# 6. SERVIDOR WEB FASTAPI (MÓDULO REPARTIDOR Y MONITOR DE ESTADO)
# ==============================================================================
app = FastAPI(title="Smart Campus Locker - 3 Casilleros")


@app.get("/", response_class=HTMLResponse)
@app.get("/deposito", response_class=HTMLResponse)
def vista_deposito(mensaje: str = "", error: str = ""):
    with lock_sistema:
        filas_estado = ""
        opciones_locker = ""
        for num, info in estado_lockers.items():
            badge = (
                "<span style='color:#dc3545;font-weight:bold;'>OCUPADO</span>"
                if info["ocupado"]
                else "<span style='color:#28a745;font-weight:bold;'>DISPONIBLE</span>"
            )
            dest = info["usuario"] if info["ocupado"] else "—"
            filas_estado += f"<tr><td>Locker {num}</td><td>{badge}</td><td>{dest}</td></tr>"
            if not info["ocupado"]:
                opciones_locker += f"<option value='{num}'>Casillero {num} (Libre)</option>"

    if not opciones_locker:
        opciones_locker = "<option value='' disabled selected>Todos los casilleros ocupados</option>"

    opciones_usuarios = "".join(
        f"<option value='{mat}'>{mat} - {datos['nombre']}</option>"
        for mat, datos in DIRECTORIO_USUARIOS.items()
    )

    alerta_html = ""
    if mensaje:
        alerta_html = f"<div style='background:#d4edda;color:#155724;padding:12px;border-radius:6px;margin-bottom:15px;'>✅ {mensaje}</div>"
    elif error:
        alerta_html = f"<div style='background:#f8d7da;color:#721c24;padding:12px;border-radius:6px;margin-bottom:15px;'>⚠️ {error}</div>"

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
            <h2>📦 Smart Mondradrop</h2>
            {alerta_html}
            <form action="/api/v1/deposito" method="post">
                <label>1. Selecciona Casillero Disponible:</label>
                <select name="locker_id" required>{opciones_locker}</select>

                <label>2. Destinatario (Alumno / Personal):</label>
                <select name="matricula" required>{opciones_usuarios}</select>

                <button type="submit">Confirmar Depósito y Notificar</button>
            </form>
        </div>

        <div class="card">
            <h3>Estado en Tiempo Real</h3>
            <table>
                <tr><th>Casillero</th><th>Estado</th><th>Asignado a</th></tr>
                {filas_estado}
            </table>
        </div>
    </body>
    </html>
    """


@app.post("/api/v1/deposito", response_class=HTMLResponse)
def procesar_deposito(locker_id: int = Form(...), matricula: str = Form(...)):
    if matricula not in DIRECTORIO_USUARIOS:
        return vista_deposito(error="Matrícula no registrada en el sistema.")

    usuario = DIRECTORIO_USUARIOS[matricula]

    with lock_sistema:
        if locker_id not in estado_lockers:
            return vista_deposito(error="Número de casillero inválido.")
        if estado_lockers[locker_id]["ocupado"]:
            return vista_deposito(
                error=f"El Casillero {locker_id} ya fue ocupado por otra solicitud."
            )

        pin_nuevo = generar_pin_unico()
        estado_lockers[locker_id] = {
            "ocupado": True,
            "pin": pin_nuevo,
            "uid": usuario["uid"],
            "usuario": usuario["nombre"],
            "chat_id": usuario["chat_id"],
            "ultimo_aviso": time.time(),
        }

    # Abrir el casillero 10 segundos para que el repartidor ingrese el paquete
    threading.Thread(
        target=abrir_casillero, args=(locker_id, "Deposito"), daemon=True
    ).start()

    texto_tg = (
        f"📦 Smart Mondradrop\n"
        f"Hola {usuario['nombre']}, tienes un paquete en el Casillero #{locker_id}.\n"
        f"🔑 PIN de retiro: {pin_nuevo}\n"
        f"💳 También puedes abrirlo acercando tu credencial RFID al lector."
    )
    enviar_telegram(usuario["chat_id"], texto_tg)

    return vista_deposito(
        mensaje=f"Casillero {locker_id} abierto por 10s para depósito de {usuario['nombre']}. Notificación enviada."
    )


@app.get("/api/v1/estado")
def obtener_estado_json():
    with lock_sistema:
        return estado_lockers


# ==============================================================================
# 7. ARRANQUE DEL SISTEMA UNIFICADO
# ==============================================================================
if __name__ == "__main__":
    print("=== INICIANDO SMART CAMPUS LOCKER (3 CASILLEROS) ===")
    verificar_rotacion_pin_maestro()
    hilo_hardware = threading.Thread(target=bucle_hmi_fisico, daemon=True)
    hilo_hardware.start()

    try:
        uvicorn.run(app, host="0.0.0.0", port=8000)
    finally:
        for r in reles.values():
            r.off()
        if lcd:
            lcd.clear()
        print("\nSistema apagado y relés liberados de forma segura.")
