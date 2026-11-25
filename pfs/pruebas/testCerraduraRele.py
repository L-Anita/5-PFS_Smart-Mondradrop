import time
from gpiozero import OutputDevice

#GPIO 18 p/ controlar el rele
rele = OutputDevice(18, active_high=True, initial_value=False)

print("=" * 50)
print("   PRUEBA DE ACTUADOR / CERRADURA (GPIO 18)")
print("=" * 50)

try:
    while True:
        comando = input("\nEscribir 'abrir' para activar la cerradura (o 'q' para salir): ").strip().lower()
        
        if comando == 'abrir':
            print("-> [RELÉ ACTIVADO] Abriendo solenoide durante 5 segundos...")
            rele.on()
            time.sleep(5)  #tiempo de apertura del locker
            rele.off()
            print("-> [RELÉ DESACTIVADO] Solenoide reenganchado.")
        
        elif comando == 'q':
            print("\nSaliendo del programa...")
            break
        else:
            print("Comando no reconocido! Escribe 'abrir' o 'q'.")

except KeyboardInterrupt:
    print("\nPrueba interrumpida.")

finally:
    rele.off()  #asegura que el rele quede desactivado al salir
    print("Prueba de cerradura finalizada.")
