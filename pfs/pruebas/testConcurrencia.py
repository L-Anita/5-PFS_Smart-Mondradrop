import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "http://127.0.0.1:8000/api/v1/deposito"
NUM_PETICIONES = 10

resultados = {"exitos": 0, "errores": 0}
lockResultados = threading.Lock()


def enviarDepositoSimultaneo(clienteId: int):
    # Envía 'lockerId' como formulario (application/x-www-form-urlencoded)
    datos = urllib.parse.urlencode({"lockerId": 1}).encode("utf-8")
    req = urllib.request.Request(
        BASE_URL,
        data=datos,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    tiempoInicio = time.time()
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            duracion = round((time.time() - tiempoInicio) * 1000, 2)
            data = json.loads(response.read().decode())
            with lockResultados:
                resultados["exitos"] += 1
            print(
                f"[Cliente {clienteId:02d}] ✅ 200 OK ({duracion}ms) -> {data['mensaje']}"
            )

    except urllib.error.HTTPError as e:
        duracion = round((time.time() - tiempoInicio) * 1000, 2)
        detalle = e.read().decode("utf-8", errors="ignore")
        with lockResultados:
            resultados["errores"] += 1
        print(
            f"[Cliente {clienteId:02d}] ❌ HTTP {e.code} ({duracion}ms) -> {detalle}"
        )
    except Exception as e:
        duracion = round((time.time() - tiempoInicio) * 1000, 2)
        with lockResultados:
            resultados["errores"] += 1
        print(f"[Cliente {clienteId:02d}] ❌ Error: {e} ({duracion}ms)")


def ejecutarPruebaConcurrencia():
    print(
        f"=== INICIANDO PRUEBA DE CONCURRENCIA ({NUM_PETICIONES} Hilos Simultáneos) ==="
    )
    hilos = []
    tiempoTotalInicio = time.time()

    for i in range(1, NUM_PETICIONES + 1):
        hilo = threading.Thread(target=enviarDepositoSimultaneo, args=(i,))
        hilos.append(hilo)
        hilo.start()

    for hilo in hilos:
        hilo.join()

    tiempoTotal = round(time.time() - tiempoTotalInicio, 3)

    print("\n" + "=" * 50)
    print("RESUMEN DE LA PRUEBA:")
    print(f"• Peticiones totales:   {NUM_PETICIONES}")
    print(f"• Solicitudes exitosas: {resultados['exitos']}")
    print(f"• Solicitudes fallidas: {resultados['errores']}")
    print(f"• Tiempo total:         {tiempoTotal} segundos")
    print("=" * 50)


if __name__ == "__main__":
    ejecutarPruebaConcurrencia()
