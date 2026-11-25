import os
from pathlib import Path
import time
import RPi.GPIO as GPIO
from mfrc522 import SimpleMFRC522


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

#pines BCM p/ los casilleros
PIN_RELE_ANA = 18     # Pin casillero 1
PIN_RELE_CARLOS = 23  # Pin casillero 2

#UIDs cargados desde archivo .env
UID_ANA = int(os.getenv("UID_ANA", "0"))
UID_CARLOS = int(os.getenv("UID_CARLOS", "0"))

#GPIO
GPIO.setmode(GPIO.BCM)  #numeración BCM
#relés se activan en LOW | estado inicial debe ser HIGH
GPIO.setup(PIN_RELE_ANA, GPIO.OUT, initial=GPIO.HIGH)
GPIO.setup(PIN_RELE_CARLOS, GPIO.OUT, initial=GPIO.HIGH)

lector = SimpleMFRC522()

print("Acerca una tarjeta al lector RFID...")

try:
    while True:
        uid, texto = lector.read()
        print(f"\nUID detectado: {uid}")

        if uid == UID_ANA:
            print("-> Tarjeta de Ana. Abriendo Casillero 1 (Pin 18)...")
            GPIO.output(PIN_RELE_ANA, GPIO.LOW)  #activa rele 
            time.sleep(3)
            GPIO.output(PIN_RELE_ANA, GPIO.HIGH)  #apaga rele
            print("Casillero 1 cerrado.")

        elif uid == UID_CARLOS:
            print("-> Llavero de Carlos. Abriendo Casillero 2 (Pin 23)...")
            GPIO.output(PIN_RELE_CARLOS, GPIO.LOW)  #activa rele
            time.sleep(3)
            GPIO.output(PIN_RELE_CARLOS, GPIO.HIGH)  #apaga rele
            print("Casillero 2 cerrado.")

        else:
            print("-> UID no registrado. No se abre nada.")

        time.sleep(1)  #pausa p/ no leer multi veces seguidas

except KeyboardInterrupt:
    print("\nSaliendo de la prueba...")
finally:
    GPIO.cleanup()
