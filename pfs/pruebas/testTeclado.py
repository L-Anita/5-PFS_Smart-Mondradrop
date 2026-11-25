import time
from gpiozero import DigitalOutputDevice, DigitalInputDevice

#Filas (R1 - R4)
FILAS_PINS = [12, 16, 20, 21]

#Columnas (C1 - C4) 
COLS_PINS = [5, 6, 13, 19]

# Configuración de E/S
filas = [DigitalOutputDevice(pin, active_high=True, initial_value=False) for pin in FILAS_PINS]
columnas = [DigitalInputDevice(pin, pullUp=False) for pin in COLS_PINS]

#mapa de teclas del teclado
TECLADO = [
    ['1', '2', '3', 'A'],
    ['4', '5', '6', 'B'],
    ['7', '8', '9', 'C'],
    ['*', '0', '#', 'D']
]

def leerTecla():
    for i, fila in enumerate(filas):
        fila.on()  #activar la fila
        for j, col in enumerate(columnas):
            if col.is_active:  #si la columna recibe pulso
                time.sleep(0.05)  #debounce
                while col.is_Active:  # Esperar a que se suelte la tecla
                    pass
                fila.off()
                return TECLADO[i][j]
        fila.off()
    return None

print("=" * 45)
print("   PRUEBA DE TECLADO MATRICIAL")
print("   Presionar cualquier tecla...")
print("   Salir: Ctrl + C")
print("=" * 45)

try:
    while True:
        tecla = leerTecla()
        if tecla:
            print(f"-> Tecla detectada: [{tecla}]")
        time.sleep(0.02)
except KeyboardInterrupt:
    print("\n\nPrueba finalizada.")
