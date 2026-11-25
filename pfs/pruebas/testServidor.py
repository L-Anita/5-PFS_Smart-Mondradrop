from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import hashlib

#inicializacion de FastAPI
app = FastAPI(
    title="Smart Mondradrop API",
    description="Servidor local Edge Computing en Raspberry Pi 5"
)

# Base de datos temporal simulada en memoria
# Guarda hashes SHA-256 de los PINs "1234" y "8492"
BASE_DATOS_PINS = {
    hashlib.sha256("1234".encode()).hexdigest(): {"casillero": 1, "usado": False},
    hashlib.sha256("8492".encode()).hexdigest(): {"casillero": 2, "usado": False}
}

#esquema de datos p/ la petición HTTP
class PinRequest(BaseModel):
    pin: str

@app.get("/")
def estadoServidor():
    """Endpoint para verificar que la API esta activa localmente"""
    return {
        "status": "online",
        "sistema": "Smart Campus Locker",
        "nodo": "Raspberry Pi 5"
    }

@app.post("/api/v1/validar-pin")
def validarPin(request: PinRequest):
    #Endpoint p/ procesar e ingresar un PIN desde interfaz
    #convertir el PIN a su representación hash
    pinHash = hashlib.sha256(request.pin.encode()).hexdigest()
    
    if pinHash in BASE_DATOS_PINS:
        registro = BASE_DATOS_PINS[pinHash]
        
        if not registro["usado"]:
            #marcar PIN como usado
            registro["usado"] = True
            return {
                "acceso": True,
                "casillero": registro["casillero"],
                "mensaje": f"PIN Válido. Apertura autorizada para Locker #{registro['casillero']}"
            }
        else:
            raise HTTPException(
                statusCode = 400, 
                detail = "Acceso denegado: El PIN ya fue utilizado previamente"
            )
            
    raise HTTPException(
        statusCode = 401, 
        detail = "Acceso denegado: PIN incorrecto o no registrado"
    )
