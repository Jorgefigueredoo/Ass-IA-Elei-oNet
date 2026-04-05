from fastapi import FastAPI
import requests

app = FastAPI()

# Este é o "Cérebro" do assistente com as regras dos manuais
PROMPT_SISTEMA = """
Você é o assistente oficial do EleiçãoNet. Use as seguintes regras para ajudar o eleitor:
1. O acesso exige CPF (apenas números) e a senha recebida por E-mail ou SMS.
2. Se o eleitor não tiver a senha, ele deve digitar o CPF, marcar 'Não sou um robô' e clicar em 'RECUPERAR SENHA'.
3. O tempo limite para votar é de exatamente 10 minutos após o login.
4. O eleitor pode votar em chapas, candidatos, BRANCO ou NULO.
5. Antes de confirmar, ele pode usar o botão 'CORRIGIR' para alterar o voto.
6. O comprovante de votação aparece na tela logo após a confirmação.
"""

@app.post("/perguntar")
async def processar_pergunta(dados: dict):
    pergunta_usuario = dados.get("pergunta")
    
    # Conecta com o Ollama (Llama 3) que você baixou
    try:
        response = requests.post("http://localhost:11434/api/generate", json={
            "model": "llama3",
            "prompt": f"{PROMPT_SISTEMA}\n\nUsuário: {pergunta_usuario}\nAssistente:",
            "stream": False
        })
        return {"resposta": response.json().get("response")}
    except Exception as e:
        return {"erro": "Certifique-se de que o Ollama está aberto e o modelo llama3 baixado."}