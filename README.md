# 🗳️ EleiçãoNet — Assistente Virtual com IA Local

> Back-end do assistente inteligente para o sistema **EleiçãoNet**, orientando eleitores em tempo real com base nos manuais oficiais — sem APIs pagas, sem enviar dados para a nuvem.

O projeto combina **FastAPI** e **Ollama** para rodar um modelo de linguagem (LLM) inteiramente na máquina local, garantindo **privacidade total** e **custo zero** de inferência.

---

## 🛠️ Tecnologias

| Ferramenta | Versão | Descrição |
| :--- | :---: | :--- |
| **Python** | 3.14+ | Linguagem base do projeto |
| **FastAPI** | latest | Framework para criação da API REST |
| **Uvicorn** | latest | Servidor ASGI para execução da aplicação |
| **Ollama** | latest | Runner de modelos de IA locais |
| **Llama 3** | 8B | Modelo de linguagem usado como motor de IA |

---

## 📂 Estrutura do Projeto

```
eleicaonet-ai/
├── venv/               # Ambiente virtual (não versionar)
├── main.py             # Rotas da API e Prompt de Sistema
└── README.md
```

---

## 🚀 Como Rodar Localmente

Siga os passos **na ordem indicada**.

### Pré-requisitos

- **Python 3.14** ou superior → [python.org](https://python.org)
- **Ollama** instalado → [ollama.com](https://ollama.com)

---

### 1. Preparar o modelo de IA

Com o Ollama instalado, abra um terminal e baixe o Llama 3:

```powershell
ollama run llama3
```

> ⚠️ **Mantenha este terminal aberto.** Ele roda o servidor de processamento da IA em segundo plano.

---

### 2. Configurar o ambiente Python

Abra um **segundo terminal** dentro da pasta do projeto e execute:

```powershell
# Entre na pasta do projeto
cd eleicaonet-ai

# Crie o ambiente virtual
python -m venv venv

# Ative o ambiente virtual
.\venv\Scripts\activate

# Instale as dependências
pip install fastapi uvicorn requests
```

---

### 3. Iniciar a API

Com o ambiente virtual ativo, suba o servidor:

```powershell
uvicorn main:app --reload
```

A API estará disponível em: **http://127.0.0.1:8000**

---

## 🧪 Como Testar

### Opção A — Swagger UI (recomendado)

O FastAPI gera uma interface interativa automaticamente:

1. Acesse **http://127.0.0.1:8000/docs** no navegador
2. Localize o endpoint `POST /perguntar` e clique em **Try it out**
3. Envie sua pergunta no formato abaixo e clique em **Execute**

```json
{
  "pergunta": "Quanto tempo tenho para votar?"
}
```

### Opção B — cURL

```bash
curl -X POST http://127.0.0.1:8000/perguntar \
  -H "Content-Type: application/json" \
  -d '{"pergunta": "Como recupero minha senha?"}'
```

**Resposta esperada:**

```json
{
  "resposta": "Para recuperar sua senha, digite seu CPF, marque 'Não sou um robô' e clique em 'RECUPERAR SENHA'. A nova senha será enviada ao seu e-mail ou SMS cadastrado."
}
```

---

## 🧠 Regras de Negócio Implementadas

O assistente responde **estritamente** com base nas regras extraídas dos manuais oficiais do EleiçãoNet:

| Regra | Detalhe |
| :--- | :--- |
| **Acesso** | Login exige CPF (somente números) e senha recebida por e-mail ou SMS |
| **Recuperação de senha** | CPF → marcar "Não sou um robô" → clicar em **RECUPERAR SENHA** |
| **Tempo limite** | Exatamente **10 minutos** após o login para concluir o voto |
| **Opções de voto** | Candidatos, chapas, **BRANCO** ou **NULO** |
| **Correção** | Botão **CORRIGIR** disponível antes da confirmação final |
| **Comprovante** | Exibido automaticamente na tela após a conclusão do voto |

---

## ⚠️ Solução de Problemas

| Sintoma | Causa provável | Solução |
| :--- | :--- | :--- |
| `"Certifique-se de que o Ollama está aberto..."` | Ollama não está em execução | Execute `ollama serve` em outro terminal |
| `model not found` | Modelo não foi baixado | Execute `ollama pull llama3` |
| Porta 8000 já em uso | Outra aplicação na mesma porta | Use `uvicorn main:app --port 8001` |
| `pip` não reconhecido | Ambiente virtual não ativado | Execute `.\venv\Scripts\activate` antes do pip |

---
