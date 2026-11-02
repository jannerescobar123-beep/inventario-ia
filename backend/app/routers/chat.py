"""Chat con el asistente de IA local (Ollama)."""
from fastapi import APIRouter

from app.schemas import ChatRequest, ChatResponse
from app.services import llm

router = APIRouter(prefix="/api/chat", tags=["Chat IA"])


@router.post("", response_model=ChatResponse)
def chat(payload: ChatRequest):
    # TODO(Persona B, semana 3): construir contexto con cifras del negocio
    # (KPIs, alertas, top productos) y function calling con herramientas.
    return llm.responder(payload.pregunta)
