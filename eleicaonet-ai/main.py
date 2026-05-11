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

from sqlalchemy import func, or_ 

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

@app.post("/cadastro/lote")
async def cadastro_lote_csv(arquivo: UploadFile = File(...), db: Session = Depends(get_db)):
    # Só aceita arquivos .csv
    if not arquivo.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Por favor, envie um arquivo no formato .csv")

    
    conteudo = await arquivo.read()
    texto = conteudo.decode('utf-8')
    leitor_csv = csv.DictReader(io.StringIO(texto))

    cadastrados = 0
    erros = []

    # 3. Loop de cadastro
    for linha in leitor_csv:
        try:
            
            usuario_existe = db.query(models.Usuario).filter(
                (models.Usuario.cpf == linha['cpf']) | (models.Usuario.login == linha['login'])
            ).first()

            if usuario_existe:
                erros.append(f"Pulei: {linha['login']} (CPF ou Login já cadastrados)")
                continue

            
            novo_usuario = models.Usuario(
                nome=linha['nome'],
                login=linha['login'],
                senha=gerar_hash_senha(linha['senha']), # Usando a função de hash do seu amigo!
                cpf=linha['cpf']
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
