from fastapi import FastAPI, Depends
from pydantic import BaseModel
import requests
import time
import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func

import models
from database import engine, SessionLocal

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

TIMEOUT_SESSAO_MINUTOS = 10

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class RequisicaoPergunta(BaseModel):
    cpf: str
    pergunta: str

PROMPT_SISTEMA = """
Você é o assistente virtual oficial de atendimento do EleiçãoNet. Sua função é orientar eleitores em linguagem simples, curta e voltada à ação.

REGRAS DE NEGÓCIO E LIMITES:
- NUNCA invente informações. NUNCA altere dados cadastrais, senhas ou e-mails. NUNCA vote pelo eleitor.
- Se o eleitor relatar divergência de dados (e-mail ou celular errado/antigo), explique que você não pode alterar e oriente-o a procurar a Comissão Eleitoral.

FLUXOS DE VOTAÇÃO:
1. Autenticação básica: Exige CPF (apenas números) e senha recebida por e-mail ou SMS.
2. Recuperação de senha: Se não tiver a senha, oriente a digitar o CPF, marcar 'Não sou um robô' (reCAPTCHA) e clicar em 'RECUPERAR SENHA'.
3. Data de Nascimento: Se o sistema pedir, deve ser no formato DD/MM/AAAA. Se o erro persistir, pode haver divergência no cadastro (encaminhar à Comissão).
4. Troca de Senha: Se for o primeiro acesso, a nova senha exige no mínimo 6 caracteres, contendo apenas letras e números.
5. Votação: Pode votar em chapas, candidatos, BRANCO ou NULO. Pode corrigir o voto antes de confirmar.
6. Senha na confirmação: Em algumas eleições, a senha é pedida novamente na hora de confirmar o voto final.
7. Comprovante: É exibido na tela após votar. Para reemitir, o eleitor deve fazer um novo login.
8. Tempo: Geralmente há um limite configurado (ex: 10 minutos) para concluir o voto antes de expirar a sessão.
"""

def obter_ou_criar_sessao(cpf: str, db: Session) -> models.SessaoAtendimento:
    agora = datetime.datetime.utcnow()
    limite = agora - datetime.timedelta(minutes=TIMEOUT_SESSAO_MINUTOS)

    # Busca sessão ativa para o CPF com último acesso dentro do tempo limite
    sessao = db.query(models.SessaoAtendimento).filter(
        models.SessaoAtendimento.cpf_eleitor == cpf,
        models.SessaoAtendimento.encerrada == False,
        models.SessaoAtendimento.ultimo_acesso >= limite
    ).first()

    if sessao:
        # Atualiza o último acesso para manter a sessão viva
        sessao.ultimo_acesso = agora
        db.commit()
    else:
        # Cria nova sessão
        sessao = models.SessaoAtendimento(cpf_eleitor=cpf)
        db.add(sessao)
        db.commit()
        db.refresh(sessao)

    return sessao


@app.post("/perguntar")
async def processar_pergunta(requisicao: RequisicaoPergunta, db: Session = Depends(get_db)):

    payload = {
        "model": "llama3",
        "prompt": f"{PROMPT_SISTEMA}\n\nEleitor: {requisicao.pergunta}\nAssistente:",
        "stream": False,
        "options": {"temperature": 0.1}
    }

    try:
        sessao = obter_ou_criar_sessao(requisicao.cpf, db)

        inicio = time.time()
        response = requests.post("http://localhost:11434/api/generate", json=payload)
        tempo_ms = round((time.time() - inicio) * 1000, 2)

        resposta_ia = response.json().get("response")
        encaminhou = "comissão eleitoral" in resposta_ia.lower()

        novo_registro = models.AuditoriaAtendimento(
            sessao_id=sessao.id,
            pergunta_eleitor=requisicao.pergunta,
            resposta_ia=resposta_ia,
            precisou_encaminhar=encaminhou,
            tema_recorrente="A classificar",
            tempo_resposta_ms=tempo_ms
        )
        db.add(novo_registro)
        db.commit()
        db.refresh(novo_registro)

        return {
            "resposta": resposta_ia,
            "id_atendimento": novo_registro.id,
            "sessao_id": sessao.id,
            "tempo_resposta_ms": tempo_ms
        }

    except Exception as e:
        return {"erro": "Certifique-se de que o Ollama está em execução e o modelo llama3 está baixado."}

@app.get("/relatorio/tempo")
def relatorio_tempo(db: Session = Depends(get_db)):

    resultado = db.query(
        func.count(models.AuditoriaAtendimento.id).label("total_atendimentos"),
        func.avg(models.AuditoriaAtendimento.tempo_resposta_ms).label("media_ms"),
        func.min(models.AuditoriaAtendimento.tempo_resposta_ms).label("minimo_ms"),
        func.max(models.AuditoriaAtendimento.tempo_resposta_ms).label("maximo_ms"),
    ).first()

    if not resultado or resultado.total_atendimentos == 0:
        return {"mensagem": "Nenhum atendimento registrado ainda."}

    return {
        "total_atendimentos": resultado.total_atendimentos,
        "media_ms": round(resultado.media_ms, 2),
        "minimo_ms": round(resultado.minimo_ms, 2),
        "maximo_ms": round(resultado.maximo_ms, 2),
    }           

@app.get("/sessao/{sessao_id}")
def consultar_sessao(sessao_id: int, db: Session = Depends(get_db)):

    sessao = db.query(models.SessaoAtendimento).filter(
        models.SessaoAtendimento.id == sessao_id
    ).first()

    if not sessao:
        return {"mensagem": "Sessão não encontrada."}

    atendimentos = db.query(models.AuditoriaAtendimento).filter(
        models.AuditoriaAtendimento.sessao_id == sessao_id
    ).all()

    return {
        "sessao_id": sessao.id,
        "cpf_eleitor": sessao.cpf_eleitor,
        "iniciada_em": sessao.iniciada_em,
        "ultimo_acesso": sessao.ultimo_acesso,
        "encerrada": sessao.encerrada,
        "total_perguntas": len(atendimentos),
        "atendimentos": [
            {
                "id": a.id,
                "pergunta": a.pergunta_eleitor,
                "resposta": a.resposta_ia,
                "precisou_encaminhar": a.precisou_encaminhar,
                "tempo_resposta_ms": a.tempo_resposta_ms,
                "data_hora": a.data_hora,
            }
            for a in atendimentos
        ]
    }