import requests

TOKEN = "TOKEN_AQUI"
CHAT_ID = "CHAT_ID_AQUI"

def enviarTelegram(casilleroN: int, pinCode: str):
    mensaje = (
        f"*Smart locker*\n\n"
        f"Tu paquete está en el *Locker #{casilleroN}*\n"
        f"PIN de apertura: `{pinCode}`"
    )
    
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": mensaje,
        "parse_mode": "Markdown"
    }
    
    respuesta = requests.post(url, data=payload)
    if respuesta.status_code == 200:
        print("Notificación enviada por Telegram exitosamente! Yay.")
    else:
        print(f"[!] Error: {respuesta.text}")

if __name__ == "__main__":
    enviarTelegram(casilleroN=1, pinCode="8492")
