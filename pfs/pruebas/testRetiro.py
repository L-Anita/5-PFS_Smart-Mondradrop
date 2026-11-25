import sys
import time
from gpiozero import DigitalInputDevice, OutputDevice
from RPLCD.i2c import CharLCD

#pines y LCD
RELAY_PIN = 18
relay = OutputDevice(RELAY_PIN, active_high=False, initial_value=False)

#teclado
FILAS = [12, 16, 20, 21]
COLUMNAS = [5, 6, 13, 19]

teclas = [
    ['1', '2', '3', 'A'],
    ['4', '5', '6', 'B'],
    ['7', '8', '9', 'C'],
    ['*', '0', '#', 'D'],
]

filasOut = [OutputDevice(p, initial_value=True) for p in FILAS]
colsIn = [DigitalInputDevice(p, pull_up=True) for p in COLUMNAS]

#inicializacion de LCD 
try:
    lcd = CharLCD(
        i2c_expander='PCF8574', address=0x27, port=1, cols=16, rows=2
    )
except Exception as e:
    print(f'Error LCD: {e}')
    lcd = None


def escribirLcd(linea1: str, linea2: str = ''):
    if lcd:
        lcd.clear()
        lcd.cursor_pos = (0, 0)
        lcd.write_string(linea1[:16])
        if linea2:
            lcd.cursor_pos = (1, 0)
            lcd.write_string(linea2[:16])
    print(f'[LCD] L1: {linea1} | L2: {linea2}')


def leerTecla():
    for rIdx, fOut in enumerate(filasOut):
        fOut.off()
        for cIdx, cIn in enumerate(colsIn):
            if cIn.is_active:
                time.sleep(0.05)  # Antirrebote
                while cIn.is_active:
                    time.sleep(0.01)
                fOut.on()
                return teclas[rIdx][cIdx]
        fOut.on()
    return None


def abrirCasillero():
    escribirLcd('¡PIN Correcto!', 'Abriendo Locker')
    relay.on()  # Activa solenoide
    time.sleep(5)
    relay.off()  # Desactiva solenoide
    escribirLcd('Casillero Libre', 'Esperando Paquete')


def procesoRetiro(pinCorrecto: str):
    bufferPin = ''
    escribirLcd('Ingrese PIN:', 'PIN: ')

    while True:
        tecla = leerTecla()
        if tecla:
            print(f'Tecla presionada: {tecla}')
            if tecla == '*':
                bufferPin = ''
                escribirLcd('Ingrese PIN:', 'PIN: ')
            elif tecla == '#':
                if bufferPin == pinCorrecto:
                    abrirCasillero()
                    break
                else:
                    escribirLcd('PIN Incorrecto', 'Reintente...')
                    time.sleep(2)
                    bufferPin = ''
                    escribirLcd('Ingrese PIN:', 'PIN: ')
            elif len(bufferPin) < 4 and tecla.isdigit():
                bufferPin += tecla
                escribirLcd('Ingrese PIN:', f"PIN: {'*' * len(bufferPin)}")
        time.sleep(0.02)


if __name__ == '__main__':
    PIN_TEST = '8492'
    print('--- FASE 2: PRUEBA COMPLETA HMI ---')
    print(f'PIN de prueba: {PIN_TEST}')
    try:
        procesoRetiro(PIN_TEST)
    except KeyboardInterrupt:
        print('\nPrueba finalizada.')
        sys.exit(0)

