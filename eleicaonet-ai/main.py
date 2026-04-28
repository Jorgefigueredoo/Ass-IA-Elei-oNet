from fastapi import FastAPI, Depends
from pydantic import BaseModel
import requests
import time
import datetime
import hashlib

from sqlalchemy.orm import Session
from sqlalchemy import func

import models
from database import engine, SessionLocal

from sqlalchemy import func, or_ 

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

TIMEOUT_SESSAO_MINUTOS = 10


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class RequisicaoCadastro(BaseModel):
    nome: str
    login: str
    senha: str
    cpf: str


class RequisicaoLogin(BaseModel):
    login: str
    senha: str


class RequisicaoPergunta(BaseModel):
    login: str
    senha: str
    pergunta: str


PROMPT_SISTEMA = """
Você é o assistente virtual oficial de atendimento do EleiçãoNet.

Responda de forma objetiva, curta e útil.

NUNCA altere dados cadastrais.
NUNCA vote pelo eleitor.
NUNCA invente informações.

Se houver erro de cadastro:
oriente procurar a Comissão Eleitoral.

Fluxos:
- Login com usuário e senha
- Recuperação de senha
- Votação
- Confirmação
- Comprovante
"""


def gerar_hash_senha(senha):
    return hashlib.sha256(
        senha.encode()
    ).hexdigest()


def validar_senha(senha_digitada, senha_hash):
    senha_convertida = hashlib.sha256(
        senha_digitada.encode()
    ).hexdigest()

    return senha_convertida == senha_hash


def autenticar_usuario(identificador, senha, db):
    # O identificador agora pode ser tanto o login quanto o CPF
    usuario = db.query(models.Usuario).filter(
        or_(
            models.Usuario.login == identificador,
            models.Usuario.cpf == identificador
        )
    ).first()

    if not usuario:
        return None

    if not validar_senha(senha, usuario.senha):
        return None

    return usuario


def obter_ou_criar_sessao(cpf, db):
    agora = datetime.datetime.utcnow()

    limite = agora - datetime.timedelta(
        minutes=TIMEOUT_SESSAO_MINUTOS
    )

    sessao = db.query(models.SessaoAtendimento).filter(
        models.SessaoAtendimento.cpf_eleitor == cpf,
        models.SessaoAtendimento.encerrada == False,
        models.SessaoAtendimento.ultimo_acesso >= limite
    ).first()

    if sessao:
        sessao.ultimo_acesso = agora
        db.commit()
    else:
        sessao = models.SessaoAtendimento(
            cpf_eleitor=cpf
        )
        db.add(sessao)
        db.commit()
        db.refresh(sessao)

    return sessao


@app.get("/status")
def status_api():
    return {
        "api": "online",
        "banco": "online",
        "ia": "online"
    }


@app.post("/cadastro")
def cadastrar_usuario(
    requisicao: RequisicaoCadastro,
    db: Session = Depends(get_db)
):
    existe = db.query(models.Usuario).filter(
        models.Usuario.login == requisicao.login
    ).first()

    if existe:
        return {"erro": "Login já existe."}

    usuario = models.Usuario(
        nome=requisicao.nome,
        login=requisicao.login,
        senha=gerar_hash_senha(requisicao.senha),
        cpf=requisicao.cpf
    )

    db.add(usuario)
    db.commit()

    return {
        "mensagem": "Usuário cadastrado com sucesso."
    }


@app.post("/login")
def login(
    requisicao: RequisicaoLogin,
    db: Session = Depends(get_db)
):
    usuario = autenticar_usuario(
        requisicao.login,
        requisicao.senha,
        db
    )

    if not usuario:
        return {
            "erro": "Login ou senha inválidos."
        }

    return {
        "mensagem": "Login realizado com sucesso.",
        "usuario": usuario.nome
    }


@app.post("/perguntar")
async def processar_pergunta(
    requisicao: RequisicaoPergunta,
    db: Session = Depends(get_db)
):
    usuario = autenticar_usuario(
        requisicao.login,
        requisicao.senha,
        db
    )

    if not usuario:
        return {
            "erro": "Login ou senha inválidos."
        }

    sessao = obter_ou_criar_sessao(
        usuario.cpf,
        db
    )

    payload = {
        "model": "llama3",
        "prompt": f"{PROMPT_SISTEMA}\n\nEleitor: {requisicao.pergunta}\nAssistente:",
        "stream": False,
        "options": {
            "temperature": 0.1
        }
    }

    try:
        inicio = time.time()

        response = requests.post(
            "http://localhost:11434/api/generate",
            json=payload
        )

        tempo_ms = round(
            (time.time() - inicio) * 1000,
            2
        )

        resposta_ia = response.json().get("response")

        encaminhou = (
            "comissão eleitoral"
            in resposta_ia.lower()
        )

        auditoria = models.AuditoriaAtendimento(
            sessao_id=sessao.id,
            pergunta_eleitor=requisicao.pergunta,
            resposta_ia=resposta_ia,
            precisou_encaminhar=encaminhou,
            tema_recorrente="A classificar",
            tempo_resposta_ms=tempo_ms
        )

        db.add(auditoria)
        db.commit()

        return {
            "resposta": resposta_ia,
            "sessao_id": sessao.id,
            "tempo_resposta_ms": tempo_ms
        }

    except:
        return {
            "erro": "Verifique se o Ollama está ativo."
        }


@app.get("/relatorio/tempo")
def relatorio_tempo(
    db: Session = Depends(get_db)
):
    resultado = db.query(
        func.count(models.AuditoriaAtendimento.id),
        func.avg(models.AuditoriaAtendimento.tempo_resposta_ms),
        func.min(models.AuditoriaAtendimento.tempo_resposta_ms),
        func.max(models.AuditoriaAtendimento.tempo_resposta_ms)
    ).first()

    if resultado[0] == 0:
        return {
            "mensagem": "Nenhum atendimento registrado."
        }

    return {
        "total_atendimentos": resultado[0],
        "media_ms": round(resultado[1], 2),
        "minimo_ms": round(resultado[2], 2),
        "maximo_ms": round(resultado[3], 2)
    }


@app.get("/relatorio/perguntas")
def relatorio_perguntas(
    db: Session = Depends(get_db)
):
    perguntas = db.query(
        models.AuditoriaAtendimento.pergunta_eleitor,
        func.count(
            models.AuditoriaAtendimento.id
        ).label("total")
    ).group_by(
        models.AuditoriaAtendimento.pergunta_eleitor
    ).order_by(
        func.count(
            models.AuditoriaAtendimento.id
        ).desc()
    ).all()

    return [
        {
            "pergunta": item[0],
            "total": item[1]
        }
        for item in perguntas
    ]


@app.post("/sessao/encerrar/{sessao_id}")
def encerrar_sessao(
    sessao_id: int,
    db: Session = Depends(get_db)
):
    sessao = db.query(
        models.SessaoAtendimento
    ).filter(
        models.SessaoAtendimento.id == sessao_id
    ).first()

    if not sessao:
        return {
            "erro": "Sessão não encontrada."
        }

    sessao.encerrada = True
    db.commit()

    return {
        "mensagem": "Sessão encerrada com sucesso."
    }


@app.get("/sessao/{sessao_id}")
def consultar_sessao(
    sessao_id: int,
    db: Session = Depends(get_db)
):
    sessao = db.query(
        models.SessaoAtendimento
    ).filter(
        models.SessaoAtendimento.id == sessao_id
    ).first()

    if not sessao:
        return {
            "erro": "Sessão não encontrada."
        }

    atendimentos = db.query(
        models.AuditoriaAtendimento
    ).filter(
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
                "data_hora": a.data_hora
            }
            for a in atendimentos
        ]
    }