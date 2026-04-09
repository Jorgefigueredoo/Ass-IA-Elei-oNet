# 🗳️ EleiçãoNet — Assistente Virtual com IA Local

> Back-end do assistente inteligente para o sistema **EleiçãoNet**, orientando eleitores em tempo real com base nos manuais oficiais — sem APIs pagas, sem enviar dados para a nuvem e com auditoria completa de atendimentos.

O projeto combina **FastAPI** e **Ollama** para rodar um modelo de linguagem (LLM) inteiramente na máquina local, garantindo **privacidade total** e **custo zero** de inferência, além de registrar o histórico de interações em um banco **SQLite** local via **SQLAlchemy**.

---

## 🛠️ Tecnologias

| Ferramenta | Versão | Descrição |
| :--- | :---: | :--- |
| **Python** | 3.x | Linguagem base do projeto |
| **FastAPI** | latest | Framework para criação da API REST |
| **Uvicorn** | latest | Servidor ASGI para execução da aplicação |
| **SQLAlchemy**| latest | ORM para mapeamento e gestão do banco de dados |
| **SQLite** | nativo | Banco de dados leve e embutido para auditoria |
| **Ollama** | latest | Runner de modelos de IA locais |
| **Llama 3** | 8B | Modelo de linguagem usado como motor de IA |

---

## 📂 Estrutura do Projeto

```text
eleicaonet-ai/
├── venv/               # Ambiente virtual (não versionar)
├── .gitignore          # Arquivos ignorados pelo Git (venv, *.db, etc.)
├── database.py         # Configurações de conexão com o banco SQLite
├── main.py             # Rotas da API, regras de negócio e integração IA
├── models.py           # Modelos das tabelas do banco de dados (Auditoria)
├── requirements.txt    # Lista oficial de dependências do projeto
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

# Ative o ambiente virtual (Windows)
.\venv\Scripts\activate

# Instale as dependências do projeto
pip install -r requirements.txt
```

---
### 3. Iniciar a API

Com o ambiente virtual ativo, suba o servidor:

```powershell
uvicorn main:app --reload
```

> **Nota:** Ao iniciar o servidor pela primeira vez, o arquivo `eleicaonet.db` será criado automaticamente na raiz do projeto para salvar os logs de auditoria.

A API estará disponível em: **[http://127.0.0.1:8000](http://127.0.0.1:8000)**

---

## 🧪 Como Testar

### Opção A — Swagger UI (recomendado)

O FastAPI gera uma interface interativa automaticamente:

1. Acesse **[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)** no navegador
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
  "resposta": "Para recuperar sua senha, digite seu CPF, marque 'Não sou um robô' e clique em 'RECUPERAR SENHA'. A nova senha será enviada ao seu e-mail ou SMS cadastrado.",
  "id_atendimento": 1
}
```

---

## 🧠 Regras de Negócio e Auditoria

O assistente responde **estritamente** com base nas regras extraídas dos manuais oficiais do EleiçãoNet e rastreia os atendimentos:

| Regra | Detalhe |
| :--- | :--- |
| **Acesso** | Login exige CPF (somente números) e senha recebida por e-mail ou SMS |
| **Recuperação de senha** | CPF → marcar "Não sou um robô" → clicar em **RECUPERAR SENHA** |
| **Tempo limite** | Exatamente **10 minutos** após o login para concluir o voto |
| **Opções de voto** | Candidatos, chapas, **BRANCO** ou **NULO** |
| **Correção** | Botão **CORRIGIR** disponível antes da confirmação final |
| **Comprovante** | Exibido automaticamente na tela após a conclusão do voto |
| **Auditoria (DB)** | Todas as interações são salvas localmente, marcando se houve necessidade de encaminhamento à Comissão Eleitoral. |

---

## ⚠️ Solução de Problemas

| Sintoma | Causa provável | Solução |
| :--- | :--- | :--- |
| `"Certifique-se de que o Ollama está em execução..."` | Ollama não está aberto | Execute `ollama run llama3` em outro terminal |
| `model not found` | Modelo não foi baixado | Execute `ollama pull llama3` |
| Erro vermelho de caminhos no terminal | Resquícios de outra `venv` | Delete a pasta `venv`, recrie e instale o `requirements.txt` |
| Porta 8000 já em uso | Outra aplicação na mesma porta | Use `uvicorn main:app --port 8001` |
| `pip` não reconhecido | Ambiente virtual não ativado | Execute `.\venv\Scripts\activate` antes do pip |

---
