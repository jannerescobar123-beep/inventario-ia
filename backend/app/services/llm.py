"""Cliente del LLM local (Ollama) — TODO(Persona B), semana 3.

La IA corre 100% en el PC del negocio: ninguna pregunta ni dato sale a internet.
Configurable por variables de entorno: OLLAMA_URL y OLLAMA_MODEL.
"""
import os

import httpx

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
MODELO = os.getenv("OLLAMA_MODEL", "llama3.2:3b")

PROMPT_SISTEMA = """Eres el asistente del dueño de una tienda o ferretería.
Reglas:
1. Responde SIEMPRE en español sencillo, sin jerga técnica.
2. Usa únicamente los datos del contexto entregado; no inventes cifras.
3. Cita las cifras que sustenten tu respuesta (ej. "vendiste 12 unidades esta semana").
4. Si no tienes el dato, dilo claramente y sugiere qué información falta.
5. Sé breve: el dueño quiere decisiones, no discursos."""


def responder(pregunta: str, contexto: str = "") -> dict:
    """Envía la pregunta a Ollama y devuelve la respuesta del modelo.

    Si Ollama no está disponible, devuelve un mensaje útil en lugar de fallar
    (la demo nunca se cae).
    """
    contenido_sistema = PROMPT_SISTEMA
    if contexto:
        contenido_sistema += f"\n\nContexto actual del negocio:\n{contexto}"

    mensajes = [
        {"role": "system", "content": contenido_sistema},
        {"role": "user", "content": pregunta},
    ]

    try:
        respuesta = httpx.post(
            f"{OLLAMA_URL}/api/chat",
            json={"model": MODELO, "messages": mensajes, "stream": False},
            timeout=60,
        )
        respuesta.raise_for_status()
        texto = respuesta.json()["message"]["content"]
        return {"respuesta": texto.strip(), "modelo": MODELO, "conectado": True}
    except Exception:
        return {
            "respuesta": (
                "⚠️ No pude conectar con la IA local.\n\n"
                "Verifica que Ollama esté corriendo (`ollama serve`) y que el modelo "
                f"esté descargado (`ollama pull {MODELO}`). Mientras tanto, el resto "
                "de la aplicación funciona con normalidad."
            ),
            "modelo": MODELO,
            "conectado": False,
        }
