# 📄 Case – Aplicação de Performance (MVP)

Esse README mostra o que foi feito, como rodar e como pensar grande depois do MVP.

## 🚀 Sobre o projeto
Este projeto é um **MVP** de uma aplicação web para gestores de uma agência de marketing digital.  
Ele permite:  
- Login por e-mail e senha  
- Visualizar dados de performance em tabela  
- Filtrar por intervalo de datas  
- Ordenar por qualquer coluna  
- Exibir a coluna `cost_micros` apenas para usuários com papel **admin**  

## 🏗️ Arquitetura  

A aplicação foi organizada em **3 camadas principais**, separando responsabilidades de forma clara:  

- **Frontend (Camada de Apresentação):**  
  Construído em **HTML, CSS e JavaScript puro**, garantindo simplicidade no MVP.  
  - Exibe os dados em formato de tabela.  
  - Permite filtros por data e ordenação de colunas.  
  - Controla a experiência do usuário (UX).  
  - Futuramente pode ser migrado para um framework moderno como **React, Vue.js ou Angular**.  

- **Backend (Camada de Lógica / API):**  
  Desenvolvido em **Python (Flask)**.  
  - Fornece rotas para login e acesso aos dados.  
  - Aplica regras de negócio (ex.: esconder a coluna `cost_micros` para usuários não-admin).  
  - Garante segurança com autenticação via email e senha.  
  - Organização modular:  
    - `app.py` → ponto de entrada da API.  
    - `auth.py` → autenticação e controle de acesso.  
    - `data_loader.py` → carregamento e tratamento dos CSVs.  
    - `utils.py` → funções auxiliares.  

- **Dados (Camada de Persistência):**  
  Utiliza **arquivos CSV** como fonte de dados inicial:  
  - `users.csv` → armazena usuários e papéis (admin ou user).  
  - `performance.csv` → contém as métricas de performance das contas da agência.  
  - Esses arquivos podem futuramente ser substituídos por um banco de dados (ex.: PostgreSQL).  

---

### 🔎 Diagrama da Arquitetura  

### 🔗 Diagrama Simplificado da Arquitetura  

```plaintext
Usuário
   │
   ▼
Frontend (HTML, CSS, JS)
   │  solicita dados
   ▼
Backend (Flask API)
   │  regras de negócio:
   │   - login (email/senha)
   │   - admin vê "cost_micros"
   │   - user não vê
   ▼
Arquivos CSV (users.csv / metrics.csv)

---

## ✅ Requisitos atendidos
- Login e logout de usuários  
- Sessão simples para manter usuário logado  
- Filtro por data  
- Ordenação clicando nos cabeçalhos da tabela  
- RBAC: regra de acesso no **backend** (não-admin não recebe a coluna `cost_micros`)  
- API escrita em **Python**  
## 📋 Requisitos

### Funcionais (RF)
- RF-01: Login por e-mail e senha
- RF-02: Exibir dados em tabela
- RF-03: Filtrar dados por data
- RF-04: Ordenar por qualquer coluna
- RF-05: Exibir `cost_micros` somente para admin

### Não Funcionais (RNF)
- RNF-01: API escrita em Python
- RNF-02: Regras de acesso aplicadas no backend
- RNF-03: Dados lidos de arquivos CSV
- RNF-04: Documentação para execução do projeto

---

## 📂 Estrutura do projeto
.monks/
.monks/

│── backend/

│   ├── app.py          # API principal em Flask

│   ├── auth.py         # lógica de login

│   ├── data_loader.py  # leitura dos CSV

│   ├── utils.py        # funções auxiliares

│── frontend/

│   ├── index.html      # página inicial

│   ├── app.js       # lógica de frontend

│   ├── style.css       # estilos

│── data/

│   ├── users.csv       # usuários do sistema

│   ├── performance.csv # métricas da agência

│── requirements.txt

│── README.md


---
## 🔧 Como rodar localmente

### 1. Pré-requisitos
- Python 3.10+  
- pip  

### 2. Instalar dependências
```bash
cd marketing_case
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate
pip install flask flask-cors pandas


3. Rodar o servidor
python app.py


A aplicação estará disponível em:
👉 http://localhost:8000

🔑 Usuários de teste

Arquivo data/users.csv contém usuários de exemplo:

email	senha	role
user1	oeiIuhn56146	admin
user2	908ij0fff	user

Logando como user1 (admin) → a tabela mostra cost_micros.

Logando como user2 (user) → essa coluna não aparece.

📡 Endpoints da API
POST /api/login

Body:

{ "email": "user1", "password": "oeiIuhn56146" }


Resposta:

{ "ok": true, "user": { "email": "user1", "role": "admin" } }

GET /api/me

Retorna usuário atual.

POST /api/logout

Encerra sessão.

GET /api/data?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD&sort_by=col&sort_dir=asc|desc

Retorna dados filtrados e ordenados.

Se role=user, a coluna cost_micros não é enviada.

🌱 Evoluções futuras

Se fosse evoluir este MVP para produção, os próximos passos seriam:

Substituir CSV por PostgreSQL

Migrar de Flask para FastAPI (mais moderno e escalável)

Usar JWT para autenticação

Implementar paginação e exportação de CSV

Criar testes automáticos (pytest)

Dockerizar a aplicação para rodar em qualquer ambiente

## 🌟 Conclusão

Este projeto foi desenvolvido como um MVP de estudo e demonstração prática de Engenharia de Software.
Mesmo sendo simples, ele já aplica conceitos importantes como separação de camadas, regras de negócio no backend e controle de acesso baseado em papéis.

O objetivo não é só atender os requisitos, mas também mostrar como a solução pode evoluir para produção: trocar CSV por banco de dados, adotar FastAPI, JWT, testes automatizados e deploy em containers futuramente.