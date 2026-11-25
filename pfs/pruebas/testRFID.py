import time
import sys
from mfrc522 import SimpleMFRC522

lector = SimpleMFRC522()

print("--- PRUEBA DE LECTOR RFID-RC522 ---")
print("Acercar credencial universitaria o el llavero azul al lector...")
print("(Ctrl + C para salir)\n")

try:
    while True:
        #read_no_block() evita que el programa se congele esperando tarjeta
        uid, texto = lector.read_no_block()
        if uid:
            print(f"Tarjeta detectada! :D")
            print(f"   • UID numérico: {uid}")
            print(f"   • UID Hex:      {hex(uid)}")
            print("-" * 40)
            time.sleep(1.5)  #eita lecturas repetidas en el mismo segundo
        time.sleep(0.1)

except KeyboardInterrupt:
    print("\nPrueba RFID finalizada.")
    sys.exit(0)
    
    
