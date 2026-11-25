import time
from RPLCD.i2c import CharLCD

#cambia 0x27 por 0x3F si i2cdetect arroja 3f
DIRECCION_I2C = 0x27 

try:
    print(f"Conectando a la LCD en la dirección {hex(DIRECCION_I2C)}...")
    lcd = CharLCD(i2c_expander='PCF8574', address=DIRECCION_I2C, port=1, cols=16, rows=2)
    
    lcd.clear()
    lcd.write_string("  SMART LOCKER  ")
    lcd.cursor_pos = (1, 0)
    lcd.write_string(" LCD FUNCIONA! ")
    
    print("Noti enviada a la pantalla. Ajustar el potenciómetro azul")
    
except Exception as e:
    print(f"[!] Error al comunicarse con la pantalla LCD: {e}")
