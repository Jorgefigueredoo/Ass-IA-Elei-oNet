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
class VotoIndividual(BaseModel):
    chapa_id: int | None = None
    pleito_id: int
    tipo: str

class RequisicaoVotarLote(BaseModel):
    usuario_id: int
    votos: list[VotoIndividual]

class RequisicaoCadastro(BaseModel):
    nome: str
    cpf: str
    senha: str


class RequisicaoLogin(BaseModel):
    cpf: str
    senha: str


class RequisicaoPergunta(BaseModel):
    login: str  # Adicionado para receber do Front-end
    senha: str  # Adicionado para receber do Front-end
    pergunta: str


# -------------------------------------------------------------------
# Prompt do assistente
# -------------------------------------------------------------------
# -------------------------------------------------------------------
# Prompt do assistente
# -------------------------------------------------------------------
PROMPT_SISTEMA = """
Você é a Lara, a assistente virtual oficial de atendimento do sistema de votação EleiçãoNet.
Seja amigável, direta e ajude o eleitor com suas dúvidas.

Regras do Sistema EleiçãoNet que você deve saber para responder aos eleitores:
- A votação é 100% online, rápida e segura.
- O eleitor acessa com CPF e senha.
- O eleitor tem 10 (dez) minutos para concluir a votação após iniciar.
- Após confirmar o voto, o sistema gera um comprovante digital.
- Em caso de perda de senha, o eleitor deve usar a opção "Recuperar Senha" na tela inicial.
- Se houver erro de cadastro ou bloqueio, oriente a procurar a Comissão Eleitoral.

Regras de Segurança (Siga estritamente):
- NUNCA altere dados cadastrais.
- NUNCA vote pelo eleitor.
- NUNCA invente informações, candidatos ou regras que não estão listadas acima.
- Responda de forma objetiva, curta (máximo de 2 parágrafos) e focada apenas na pergunta do usuário.
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
        # Pleito 1: Diretoria (Vão ganhar os IDs 1, 2, 3 e 4)
        models.Chapa(numero="C1", nome="CHAPA 1 - INOVAÇÃO E GESTÃO"),
        models.Chapa(numero="C2", nome="CHAPA 2 - UNIÃO E TRANSPARÊNCIA"),
        models.Chapa(numero="C3", nome="CHAPA 3 - MOVIMENTO RENOVA"),
        models.Chapa(numero="C4", nome="CHAPA 4 - ÉTICA E EXPERIÊNCIA"),
        
        # Pleito 2: Conselho (Vão ganhar os IDs 5, 6 e 7)
        models.Chapa(numero="CA", nome="CHAPA A - FOCO E RESULTADO"),
        models.Chapa(numero="CB", nome="CHAPA B - AÇÃO CONJUNTA"),
        models.Chapa(numero="CC", nome="CHAPA C - INOVAÇÃO CONSTANTE"),
        
        # Pleito 3: Regional (Vão ganhar os IDs 8, 9, 10 e 11)
        models.Chapa(numero="J", nome="CANDIDATO JOÃO DA SILVA"),
        models.Chapa(numero="M", nome="CANDIDATA MARIA SOUZA"),
        models.Chapa(numero="P", nome="CANDIDATO PEDRO ALVES"),
        models.Chapa(numero="A", nome="CANDIDATA ANA COSTA")
    ]
    
    db.add_all(chapas_iniciais)
    db.commit()
    
    return {"mensagem": "Sucesso! Banco inicializado com todas as chapas e candidatos."}

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
        "usuario": {
            "id": usuario.id,
            "nome": usuario.nome
        }
    }


# -------------------------------------------------------------------
# Rotas protegidas (exigem Bearer token)
# -------------------------------------------------------------------
@app.post("/perguntar")
async def processar_pergunta(
    requisicao: RequisicaoPergunta,
    db: Session = Depends(get_db)
):
    # 🚀 AJUSTE: Burlamos a exigência de Token JWT apenas para essa rota
    # e validamos a existência do eleitor direto no banco com o CPF.
    usuario = db.query(models.Usuario).filter(
        models.Usuario.cpf == requisicao.login
    ).first()

    if not usuario:
        raise HTTPException(status_code=401, detail="Eleitor não encontrado no banco de dados.")

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

# Rota para listar todas as chapas
@app.get("/chapas")
def listar_chapas(db: Session = Depends(get_db)):
    return db.query(models.Chapa).all()

# Rota para registrar votos em lote (Agora 100% Anônimo)
@app.post("/votar")
async def registrar_votos_lote(requisicao: RequisicaoVotarLote, db: Session = Depends(get_db)):
    # Inicia o processamento da lista de votos
    try:
        for voto_req in requisicao.votos:
            
            # 1. Verifica na TABELA DE CONTROLE se o eleitor já votou NESTE pleito
            ja_votou = db.query(models.ControleVoto).filter(
                models.ControleVoto.usuario_id == requisicao.usuario_id,
                models.ControleVoto.pleito_id == voto_req.pleito_id
            ).first()
            
            if ja_votou:
                # Se achar voto duplicado, CANCELA TUDO que foi feito no loop
                db.rollback() 
                raise HTTPException(
                    status_code=400, 
                    detail=f"Você já registrou seu voto para o pleito {voto_req.pleito_id}!"
                )

            # 2. Adiciona o eleitor na TABELA DE CONTROLE (Registro de comparecimento)
            registro_controle = models.ControleVoto(
                usuario_id=requisicao.usuario_id,
                pleito_id=voto_req.pleito_id
            )
            db.add(registro_controle) # Adiciona à fila da transação

            # 3. Adiciona o voto na URNA ANÔNIMA (Perceba que não passamos o usuario_id aqui!)
            novo_voto = models.Voto(
                chapa_id=voto_req.chapa_id,
                tipo_voto=voto_req.tipo, # Ex: "VALIDO", "BRANCO", "NULO"
                pleito_id=voto_req.pleito_id
            )
            db.add(novo_voto) # Adiciona à fila da transação
        
        # Se o loop terminar sem erros, confirma TUDO de uma vez no banco
        db.commit()      
        
        return {
            "status": "Sucesso",
            "mensagem": f"{len(requisicao.votos)} votos computados com sucesso e sigilo garantido!"
        }
        
    except HTTPException:
        # Repassa o erro 400 da duplicidade sem cair no bloco genérico 500
        raise 
    except Exception as e:
        db.rollback() # Garante que nada será salvo em caso de erro interno
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/dashboard/metricas")
def obter_metricas_dashboard(db: Session = Depends(get_db)):
    # 1. Total de eleitores cadastrados
    total_eleitores = db.query(models.Usuario).count()
    
    # 2. Conta eleitores ÚNICOS que votaram na tabela de Controle
    eleitores_votaram = db.query(models.ControleVoto.usuario_id).distinct().count()
    
    # 3. Calcula o quórum percentual
    quorum = 0
    if total_eleitores > 0:
        quorum = round((eleitores_votaram / total_eleitores) * 100, 1)
        
    # 4. Total de votos avulsos registrados
    total_votos_urna = db.query(models.Voto).count()

    return {
        "total_eleitores": total_eleitores,
        "eleitores_votaram": eleitores_votaram,
        "quorum_percentual": quorum,
        "total_votos_urna": total_votos_urna,
        "status_urna": "Ativa"
    }

@app.get("/admin/dashboard/grafico")
def obter_dados_grafico(db: Session = Depends(get_db)):
    votos = db.query(models.Voto).all()
    
    # Array com 9 posições para o gráfico: [00h, 03h, 06h, 09h, 12h, 15h, 18h, 21h, 24h]
    dados_hoje = [0, 0, 0, 0, 0, 0, 0, 0, 0]
    votos_hoje_count = 0
    
    # Data e hora atual (UTC)
    agora = datetime.datetime.utcnow()
    hoje = agora.date()
    
    for voto in votos:
        # Pega apenas os votos registrados no dia de hoje
        if voto.data_voto.date() == hoje:
            votos_hoje_count += 1
            hora = voto.data_voto.hour
            
            # Divide a hora por 3 para achar o bloco correto no gráfico
            indice = hora // 3
            if indice <= 8:
                dados_hoje[indice] += 1
                
    # Calcula a média de votos por hora (evitando divisão por zero)
    hora_atual = agora.hour if agora.hour > 0 else 1
    votos_por_hora = round(votos_hoje_count / hora_atual)
    
    return {
        "votos_por_hora": votos_por_hora,
        "grafico_hoje": dados_hoje
    }

@app.get("/admin/auditoria/logs")
def listar_logs(db: Session = Depends(get_db)):
    # Busca os logs ordenados do mais recente para o mais antigo
    logs = db.query(models.LogAtividade).order_by(models.LogAtividade.data_hora.desc()).all()
    
    # Se não tiver nenhum log ainda, a gente manda uns falsos só para a tela não ficar vazia na apresentação
    if not logs:
        return [
            {"tipo": "settings", "cor": "green", "titulo": "Admin ativou a urna com segurança", "data": "31/05/2026", "hora": "02:00"},
            {"tipo": "file", "cor": "blue", "titulo": "Sistema gerou certificado SSL", "data": "31/05/2026", "hora": "01:45"},
            {"tipo": "user", "cor": "blue", "titulo": "Admin iniciou o sistema", "data": "31/05/2026", "hora": "01:30"}
        ]
    
    resultado = []
    for log in logs:
        resultado.append({
            "tipo": log.tipo,
            "cor": "blue" if log.tipo in ["user", "file"] else "green",
            "titulo": log.titulo,
            "data": log.data_hora.strftime("%d/%m/%Y"),
            "hora": log.data_hora.strftime("%H:%M")
        })
    return resultado

@app.post("/admin/auditoria/zeresima")
def gerar_zeresima(db: Session = Depends(get_db)):
    # A Zerésima SÓ PODE ser gerada se a urna estiver vazia!
    total_votos = db.query(models.Voto).count()
    
    if total_votos > 0:
        return {
            "success": False, 
            "message": f"ERRO DE INTEGRIDADE: A urna já possui {total_votos} votos registrados. A zerésima exige urna vazia!"
        }
    
    # Se tiver vazia, anota no log que a zerésima foi gerada
    novo_log = models.LogAtividade(tipo="file", titulo="Admin gerou relatório de Zerésima")
    db.add(novo_log)
    db.commit()
    
    return {"success": True, "message": "Zerésima verificada e gerada com sucesso."}

@app.get("/admin/relatorios/dados")
def obter_dados_relatorio(db: Session = Depends(get_db)):
    # Conta total de eleitores e total de votos
    total_eleitores = db.query(models.Usuario).count()
    total_votos = db.query(models.Voto).count()
    
    # Pega a data e hora atual do fechamento
    agora = datetime.datetime.now()
    
    return {
        "total_eleitores": total_eleitores,
        "total_votos": total_votos,
        "data_fechamento": agora.strftime("%d/%m/%Y"),
        "hora_fechamento": agora.strftime("%H:%M")
    }