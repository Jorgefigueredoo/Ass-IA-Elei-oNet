from fastapi import FastAPI, Depends
from pydantic import BaseModel
import requests
from sqlalchemy.orm import Session

# Importando as configurações do banco
import models
from database import engine, SessionLocal

# Cria as tabelas no banco de dados assim que a API iniciar
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# Dependência para abrir e fechar a sessão com o banco
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class RequisicaoPergunta(BaseModel):
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

@app.post("/perguntar")
async def processar_pergunta(requisicao: RequisicaoPergunta, db: Session = Depends(get_db)):
    
    # Payload com temperatura baixa para evitar alucinações da IA
    payload = {
        "model": "llama3",
        "prompt": f"{PROMPT_SISTEMA}\n\nEleitor: {requisicao.pergunta}\nAssistente:",
        "stream": False,
        "options": {"temperature": 0.1}
    }
    
    try:
        response = requests.post("http://localhost:11434/api/generate", json=payload)
        resposta_ia = response.json().get("response")
        
        # Identifica se a IA mandou procurar a comissão
        encaminhou = "comissão eleitoral" in resposta_ia.lower()
        
        # Salva a interação no SQLite
        novo_registro = models.AuditoriaAtendimento(
            pergunta_eleitor=requisicao.pergunta,
            resposta_ia=resposta_ia,
            precisou_encaminhar=encaminhou,
            tema_recorrente="A classificar"
        )
        db.add(novo_registro)
        db.commit()
        db.refresh(novo_registro)

        return {"resposta": resposta_ia, "id_atendimento": novo_registro.id}

    except Exception as e:
        return {"erro": "Certifique-se de que o Ollama está em execução e o modelo llama3 está baixado."}