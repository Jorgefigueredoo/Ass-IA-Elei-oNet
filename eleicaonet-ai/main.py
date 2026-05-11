# main.py

from fastapi import FastAPI, Depends, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
import time
import datetime
import hashlib
import csv
import io

from sqlalchemy.orm import Session
from sqlalchemy import func

import models
from database import engine, SessionLocal
from auth import criar_token, obter_usuario_autenticado

models.Base.metadata.create_all(bind=engine)

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
TIMEOUT_SESSAO_MINUTOS = 10


# -------------------------------------------------------------------
# Dependência de banco
# -------------------------------------------------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# -------------------------------------------------------------------
# Schemas
# -------------------------------------------------------------------
class RequisicaoCadastro(BaseModel):
    nome: str
    cpf: str
    senha: str


class RequisicaoLogin(BaseModel):
    cpf: str
    senha: str


class RequisicaoPergunta(BaseModel):
    pergunta: str


# -------------------------------------------------------------------
# Prompt do assistente
# -------------------------------------------------------------------
PROMPT_SISTEMA = """
Você é o assistente virtual oficial de atendimento do EleiçãoNet.

Responda de forma objetiva, curta e útil.

NUNCA altere dados cadastrais.
NUNCA vote pelo eleitor.
NUNCA invente informações.

Se houver erro de cadastro:
oriente procurar a Comissão Eleitoral.

Fluxos:
- Login com CPF e senha
- Recuperação de senha
- Votação
- Confirmação
- Comprovante
"""


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------
def gerar_hash_senha(senha: str) -> str:
    return hashlib.sha256(senha.encode()).hexdigest()


def validar_senha(senha_digitada: str, senha_hash: str) -> bool:
    return hashlib.sha256(senha_digitada.encode()).hexdigest() == senha_hash


def obter_ou_criar_sessao(cpf: str, db: Session):
    agora = datetime.datetime.utcnow()
    limite = agora - datetime.timedelta(minutes=TIMEOUT_SESSAO_MINUTOS)

    sessao = db.query(models.SessaoAtendimento).filter(
        models.SessaoAtendimento.cpf_eleitor == cpf,
        models.SessaoAtendimento.encerrada == False,
        models.SessaoAtendimento.ultimo_acesso >= limite
    ).first()

    if sessao:
        sessao.ultimo_acesso = agora
        db.commit()
    else:
        sessao = models.SessaoAtendimento(cpf_eleitor=cpf)
        db.add(sessao)
        db.commit()
        db.refresh(sessao)

    return sessao

@app.get("/popular-chapas")
def popular_chapas(db: Session = Depends(get_db)):
    # Evitar duplicação se já tiverem sido criadas
    if db.query(models.Chapa).first():
        return {"mensagem": "As chapas já existem na base de dados!"}

    chapas_iniciais = [
        models.Chapa(numero="C1", nome="CHAPA 1 - INOVAÇÃO E GESTÃO"),
        models.Chapa(numero="C2", nome="CHAPA 2 - UNIÃO E TRANSPARÊNCIA"),
        models.Chapa(numero="C3", nome="CHAPA 3 - MOVIMENTO RENOVA"),
        models.Chapa(numero="C4", nome="CHAPA 4 - ÉTICA E EXPERIÊNCIA")
    ]
    
    db.add_all(chapas_iniciais)
    db.commit()
    
    return {"mensagem": "Sucesso! Cédula inicializada com as 4 chapas."}

# -------------------------------------------------------------------
# Rotas públicas
# -------------------------------------------------------------------
@app.get("/status")
def status_api():
    return {"api": "online", "banco": "online", "ia": "online"}


@app.post("/cadastro")
def cadastrar_usuario(
    requisicao: RequisicaoCadastro,
    db: Session = Depends(get_db)
):
    existe = db.query(models.Usuario).filter(
        models.Usuario.cpf == requisicao.cpf
    ).first()

    if existe:
        raise HTTPException(status_code=400, detail="CPF já cadastrado.")

    usuario = models.Usuario(
        nome=requisicao.nome,
        login=requisicao.cpf,   # login passa a ser o próprio CPF
        senha=gerar_hash_senha(requisicao.senha),
        cpf=requisicao.cpf
    )
    db.add(usuario)
    db.commit()

    return {"mensagem": "Usuário cadastrado com sucesso."}


@app.post("/login")
def login(
    requisicao: RequisicaoLogin,
    db: Session = Depends(get_db)
):
    """
    Autentica com CPF + senha e retorna um Bearer token JWT.
    """
    usuario = db.query(models.Usuario).filter(
        models.Usuario.cpf == requisicao.cpf
    ).first()

    if not usuario or not validar_senha(requisicao.senha, usuario.senha):
        raise HTTPException(
            status_code=401,
            detail="CPF ou senha inválidos.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # O campo 'sub' do token carrega o CPF
    token = criar_token({"sub": usuario.cpf})

    return {
        "access_token": token,
        "token_type": "bearer",
        "usuario": usuario.nome
    }


# -------------------------------------------------------------------
# Rotas protegidas (exigem Bearer token)
# -------------------------------------------------------------------
@app.post("/perguntar")
async def processar_pergunta(
    requisicao: RequisicaoPergunta,
    usuario: models.Usuario = Depends(obter_usuario_autenticado),
    db: Session = Depends(get_db)
):
    sessao = obter_ou_criar_sessao(usuario.cpf, db)

    payload = {
        "model": "llama3",
        "prompt": f"{PROMPT_SISTEMA}\n\nEleitor: {requisicao.pergunta}\nAssistente:",
        "stream": False,
        "options": {"temperature": 0.1}
    }

    try:
        inicio = time.time()
        response = requests.post(
            "http://localhost:11434/api/generate",
            json=payload,
            timeout=120
        )
        response.raise_for_status()
        tempo_ms = round((time.time() - inicio) * 1000, 2)

        resposta_ia = response.json().get("response", "")
        encaminhou = "comissão eleitoral" in resposta_ia.lower()

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

    except requests.exceptions.ConnectionError:
        raise HTTPException(
            status_code=503,
            detail="Não foi possível conectar ao Ollama. Verifique se está em execução."
        )
    except requests.exceptions.Timeout:
        raise HTTPException(
            status_code=504,
            detail="O modelo de IA demorou demais para responder."
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erro interno: {str(e)}"
        )


@app.get("/relatorio/tempo")
def relatorio_tempo(
    _: models.Usuario = Depends(obter_usuario_autenticado),
    db: Session = Depends(get_db)
):
    resultado = db.query(
        func.count(models.AuditoriaAtendimento.id),
        func.avg(models.AuditoriaAtendimento.tempo_resposta_ms),
        func.min(models.AuditoriaAtendimento.tempo_resposta_ms),
        func.max(models.AuditoriaAtendimento.tempo_resposta_ms)
    ).first()

    if resultado[0] == 0:
        return {"mensagem": "Nenhum atendimento registrado."}

    return {
        "total_atendimentos": resultado[0],
        "media_ms": round(resultado[1], 2),
        "minimo_ms": round(resultado[2], 2),
        "maximo_ms": round(resultado[3], 2)
    }


@app.get("/relatorio/perguntas")
def relatorio_perguntas(
    _: models.Usuario = Depends(obter_usuario_autenticado),
    db: Session = Depends(get_db)
):
    perguntas = db.query(
        models.AuditoriaAtendimento.pergunta_eleitor,
        func.count(models.AuditoriaAtendimento.id).label("total")
    ).group_by(
        models.AuditoriaAtendimento.pergunta_eleitor
    ).order_by(
        func.count(models.AuditoriaAtendimento.id).desc()
    ).all()

    return [{"pergunta": item[0], "total": item[1]} for item in perguntas]


@app.post("/sessao/encerrar/{sessao_id}")
def encerrar_sessao(
    sessao_id: int,
    _: models.Usuario = Depends(obter_usuario_autenticado),
    db: Session = Depends(get_db)
):
    sessao = db.query(models.SessaoAtendimento).filter(
        models.SessaoAtendimento.id == sessao_id
    ).first()

    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada.")

    sessao.encerrada = True
    db.commit()

    return {"mensagem": "Sessão encerrada com sucesso."}


@app.get("/sessao/{sessao_id}")
def consultar_sessao(
    sessao_id: int,
    _: models.Usuario = Depends(obter_usuario_autenticado),
    db: Session = Depends(get_db)
):
    sessao = db.query(models.SessaoAtendimento).filter(
        models.SessaoAtendimento.id == sessao_id
    ).first()

    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada.")

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
                "data_hora": a.data_hora
            }
            for a in atendimentos
        ]
    }


@app.post("/cadastro/lote")
async def cadastro_lote_csv(
    arquivo: UploadFile = File(...),
    _: models.Usuario = Depends(obter_usuario_autenticado),
    db: Session = Depends(get_db)
):
    if not arquivo.filename.endswith(".csv"):
        raise HTTPException(
            status_code=400,
            detail="Por favor, envie um arquivo no formato .csv"
        )

    conteudo = await arquivo.read()
    texto = conteudo.decode("utf-8")
    leitor_csv = csv.DictReader(io.StringIO(texto))

    cadastrados = 0
    erros = []

    for linha in leitor_csv:
        try:
            usuario_existe = db.query(models.Usuario).filter(
                models.Usuario.cpf == linha["cpf"]
            ).first()

            if usuario_existe:
                erros.append(f"Pulei: CPF {linha['cpf']} já cadastrado.")
                continue

            novo_usuario = models.Usuario(
                nome=linha["nome"],
                login=linha["cpf"],   # login = CPF
                senha=gerar_hash_senha(linha["senha"]),
                cpf=linha["cpf"]
            )
            db.add(novo_usuario)
            cadastrados += 1

        except Exception as e:
            erros.append(f"Erro no registro {linha.get('nome')}: {str(e)}")

    db.commit()

    return {
        "status": "Sucesso",
        "novos_eleitores": cadastrados,
        "registros_ignorados": len(erros),
        "detalhes": erros

        
    }
# ...existing code...

    db.commit()

    return {
        "status": "Sucesso",
        "novos_eleitores": cadastrados,
        "registros_ignorados": len(erros),
        "detalhes": erros
    }

# Rota para listar todas as chapas
@app.get("/chapas")
def listar_chapas(db: Session = Depends(get_db)):
    return db.query(models.Chapa).all()

# Rota para registrar o voto
@app.post("/votar")
async def registrar_voto(requisicao: dict, db: Session = Depends(get_db)):
    # Aqui a gente recebe: { "usuario_id": 1, "chapa_id": 2, "tipo": "VALIDO" }
    
    # Verifica se o eleitor já votou (Segurança!)
    ja_votou = db.query(models.Voto).filter(models.Voto.usuario_id == requisicao['usuario_id']).first()
    if ja_votou:
        return {"erro": "Você já registrou seu voto anteriormente!"}

    novo_voto = models.Voto(
        usuario_id=requisicao['usuario_id'],
        chapa_id=requisicao.get('chapa_id'),
        tipo_voto=requisicao['tipo']
    )
    
    db.add(novo_voto) # Adiciona à fila
    db.commit()      # Confirma no banco
    db.refresh(novo_voto) # Atualiza o objeto com o ID gerado
    
    return {
        "mensagem": "Voto computado com sucesso!",
        "protocolo": f"ELO-2026-{novo_voto.id}"
    }
