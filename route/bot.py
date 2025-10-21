# bot.py
import os
import re
import time
import datetime
import psycopg2
import torch

from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
from langchain_community.llms import LlamaCpp
from langchain_core.prompts import ChatPromptTemplate

from config import DB_CONFIG
from .validator import SQLValidator, SCHEMA, mk_alias_str


# ============================================================
#  QUICK_SQL_QUERIES 
# ============================================================

QUICK_SQL_QUERIES = {
    "quantos pacientes tenho hoje": """
        SELECT COUNT(DISTINCT p.num_sequencial)
        FROM con_marcacoes m
        JOIN pacientes p ON p.num_sequencial = m.num_sequencial
        LEFT JOIN con_med_esp cme 
               ON cme.cod_med_esp = m.cod_med_esp
              AND m.tip_agenda = 'E'
        WHERE m.dta_consulta = CURRENT_DATE
          AND (
                (m.tip_agenda = 'M' AND m.cod_med_esp = %s)
             OR (m.tip_agenda = 'E' AND cme.cod_medico = %s)
              );
    """,
    "consultas agendadas amanhã": """
        SELECT COUNT(*)
        FROM con_marcacoes m
        LEFT JOIN con_med_esp cme 
               ON cme.cod_med_esp = m.cod_med_esp
              AND m.tip_agenda = 'E'
        WHERE m.dta_consulta = CURRENT_DATE + INTERVAL '1 day'
          AND (
                (m.tip_agenda = 'M' AND m.cod_med_esp = %s)
             OR (m.tip_agenda = 'E' AND cme.cod_medico = %s)
              );
    """,
    "pacientes este mês": """
        SELECT COUNT(DISTINCT p.num_sequencial)
        FROM con_marcacoes m
        JOIN pacientes p ON p.num_sequencial = m.num_sequencial
        LEFT JOIN con_med_esp cme 
               ON cme.cod_med_esp = m.cod_med_esp
              AND m.tip_agenda = 'E'
        WHERE m.dta_consulta >= date_trunc('month', CURRENT_DATE)
          AND m.dta_consulta <  date_trunc('month', CURRENT_DATE) + INTERVAL '1 month'
          AND (
                (m.tip_agenda = 'M' AND m.cod_med_esp = %s)
             OR (m.tip_agenda = 'E' AND cme.cod_medico = %s)
              );
    """
}

# ============================================================
#  Validator + Aliases
# ============================================================
validator = SQLValidator(SCHEMA)
ALIASES_STR = mk_alias_str(validator.aliases_dict)

# ============================================================
#  Greetings
# ============================================================
GREETINGS = {"olá", "ola", "oi", "bom dia", "boa tarde", "boa noite", "hello", "hi", "hey"}

def is_greeting(text: str) -> bool:
    q = text.strip().lower()
    q_clean = re.sub(r"[^\w\s]", "", q)
    return q_clean in GREETINGS

# ============================================================
#  Carregar DDL para o prompt
# ============================================================
def load_ddl(md_path: str = "ddl.md") -> str:
    """
    Lê o ficheiro DDL (markdown ou texto) para colocar no prompt.
    """
    if not os.path.exists(md_path):
        print(f"[WARN] DDL file not found at: {md_path}. Prompt will not include DDL.")
        return ""
    with open(md_path, "r", encoding="utf-8") as f:
        return f.read()

DDL_TEXT = load_ddl("route/ddl.md")

# ============================================================
#  Modelo SQLCoder (transformers)
# ============================================================
model_name = "defog/llama-3-sqlcoder-8b"
tokenizer = AutoTokenizer.from_pretrained(model_name)

bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_use_double_quant=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.float16,
)

available_memory = torch.cuda.mem_get_info()[0] if torch.cuda.is_available() else 0
if available_memory > 20e9:
    print("🔹 GPU com memória suficiente! Carregando em float16...")
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        trust_remote_code=True,
        torch_dtype=torch.float16,
        device_map="auto",
        use_cache=True,
        offload_folder="offload",
        offload_state_dict=True,
    )
else:
    print("⚠️ Pouca memória na GPU! Carregando em 4-bit com quantização...")
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        trust_remote_code=False,
        quantization_config=bnb_config,
        device_map="auto",
        use_cache=True,
        offload_folder="offload",
        offload_state_dict=False,
    )

print(torch.cuda.memory_allocated() / 1024**2, "MiB alocados inicialmente")
print(torch.cuda.memory_reserved() / 1024**2, "MiB reservados")

# ============================================================
#  Modelo para NL (LlamaCpp) 
# ============================================================
n_gpu_layers = -1
n_batch = 512
n_ctx = 2048

llm = LlamaCpp(
    model_path="../models/mistral-7b-openorca.Q5_K_M.gguf",
    temperature=0,
    max_tokens=300,           # limitar para reduzir latência
    n_ctx=n_ctx,
    top_p=1,
    n_threads=8,
    verbose=False,
    f16_kv=True,
    n_gpu_layers=n_gpu_layers,
    n_batch=n_batch,
    chat_format="chatml",
)

# ============================================================
#  Helpers
# ============================================================
def build_sql_prompt(question: str, ddl_text: str, aliases_str: str) -> str:
    """
    Constrói o prompt completo para o SQLCoder (formato chatml usado pelo repo do sqlcoder).
    """
    return f"""<|begin_of_text|><|start_header_id|>user<|end_header_id|>

Generate a SQL query to answer this question: `{question}`

- Given an input question, create a syntactically correct query to run, then look at the results of the query and return the answer.
- If the question is unrelated to the medical or clinical database context (e.g., greetings, general knowledge, jokes, or chit-chat), respond with: " Olá, sou um assistente onde pode colocar questões sobre consultas agendadas ou realizadas, exames, pacientes ou estatísticas globais."
- Never query for all columns from a table; only select the relevant columns for the question.
- Only return the columns explicitly requested by the user. Do not include extra ID columns unless the user asks for them.
- Do not add ORDER BY unless the user explicitly requests ordering.
- If the question cannot be answered with the available database schema, return "I do not know."
- Ensure no query returns two columns with the same name. If needed, disambiguate by appending the table name (e.g., nome_paciente_pacientes).
- DO NOT make any DML statements (INSERT, UPDATE, DELETE, DROP, etc.).
- Never invent column names or table names. Only use those explicitly listed in the DDL above.
- Verify column types from the DDL before using them in conditions or joins.
- Never compare different data types directly (e.g., VARCHAR = INT). Always cast explicitly if needed.

Rules for exams:
- Use the table exames when the question is about billing (facturado) or verification (verificado).
- Use the table dexames when the question is about exam details such as date (dataexame), service (servico), or report (relatorio).

Rules for consultations & appointments:
- Use the table con_marcacoes for future or present appointments (keywords: "hoje", "amanhã", or a future date).
- Use the table con_registadas for past consultations (keywords: "tive", "ontem", or a past date).
- For "hoje", compare using CURRENT_DATE.
- For "amanhã", compare using CURRENT_DATE + INTERVAL '1 day'.

Handling doctors and specialties (cod_med_esp):
IMPORTANT: The meaning of cod_med_esp depends on tip_agenda.

- If tip_agenda = 'M' (doctor agenda):
  - cod_med_esp stores the doctor's ID (sys_medicos.num_ord_medico), NOT a foreign key to con_med_esp.
  - To resolve the doctor without specialty:
    JOIN sys_medicos ON sys_medicos.num_ord_medico = cod_med_esp
  - Only join con_med_esp if you need the specialty linked to that doctor; in that case:
    JOIN con_med_esp ON con_med_esp.cod_medico = cod_med_esp
    JOIN sys_especialidades ON sys_especialidades.cod_especialidade = con_med_esp.cod_especialidade

- If tip_agenda = 'E' (specialty agenda):
  - cod_med_esp stores a key to con_med_esp.cod_med_esp.
  - To resolve doctor and/or specialty:
    JOIN con_med_esp ON con_med_esp.cod_med_esp = cod_med_esp
    LEFT JOIN sys_medicos ON sys_medicos.num_ord_medico = con_med_esp.cod_medico
    LEFT JOIN sys_especialidades ON sys_especialidades.cod_especialidade = con_med_esp.cod_especialidade

Rules for dates and times:
- Do not use TO_DATE() when filtering by a DATE column (e.g., dta_consulta). Use the value directly (DATE 'YYYY-MM-DD' or CURRENT_DATE).
- To display a DATE as DD/MM/YYYY, use: TO_CHAR(dta_consulta, 'DD/MM/YYYY').
- For comparisons, use CURRENT_DATE or DATE 'YYYY-MM-DD'.
- Time-of-day stored in seconds:
  - To get an hour-of-day integer: (hora_consulta / 3600)
  - To cast seconds to time: (TIME '00:00:00' + make_interval(secs => hora_consulta))::time
  - Example: afternoon filter => (hora_consulta / 3600) BETWEEN 12 AND 17

General query validation:
- If querying from a single table, only use columns that exist in that table.
- If a column is missing in the primary table, verify whether it exists in a related table before joining.
- Always double-check your query before execution.
- If execution fails, rewrite the query and try again.

-- Table alias hints (use if helpful):
{aliases_str}

DDL statements:
{ddl_text}

<|eot_id|><|start_header_id|>assistant<|end_header_id|>
I will reflect on the user's request before answering the question. I was asked to generate a SQL query for this question: `{question}`

Step 1: Identify what the user is asking.
Step 2: Find the relevant tables and columns from the DDL statements.
Step 3: Determine if joins are required.
Step 4: Apply filters (WHERE) correctly.
Step 5: Generate a syntactically valid SQL query for PostgreSQL.

With this in mind, here is the SQL query that best answers the question while only using appropriate tables and columns from the DDL statements:
```sql
"""

def extract_sql_from_output(text: str) -> str:
    """
    Extrai a primeira query entre ```sql ... ``` ou, em falta,
    tenta apanhar o primeiro 'SELECT ...'.
    """
    # bloco markdown ```sql ... ```
    m = re.search(r"```sql(.*?)(```|$)", text, flags=re.S | re.I)
    if m:
        snippet = m.group(1)
    else:
        # fallback: a partir de SELECT até ao primeiro ';' (ou fim)
        m2 = re.search(r"(SELECT\b.*?)(;|$)", text, flags=re.S | re.I)
        if not m2:
            raise ValueError("Não foi possível extrair SQL do output do modelo.")
        snippet = m2.group(1)
    # tira lixo e devolve
    sql = snippet.strip()
    # limpa fence restante acidental
    sql = sql.replace("```", "").strip()
    return sql

# ============================================================
#  Geração de SQL
# ============================================================
def generate_query(question: str) -> str:
    if is_greeting(question):
        # short-circuit: não gerar SQL
        return ""

    prompt = build_sql_prompt(question, DDL_TEXT, ALIASES_STR)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    inputs = tokenizer(prompt, return_tensors="pt").to(device)

    generated_ids = model.generate(
        **inputs,
        num_return_sequences=1,
        eos_token_id=tokenizer.eos_token_id,
        pad_token_id=tokenizer.eos_token_id,
        max_new_tokens=500,
        do_sample=False,
        num_beams=4,
        temperature=0.0,
        top_p=1.0,
    )

    outputs = tokenizer.batch_decode(generated_ids, skip_special_tokens=False)
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    query = outputs[0].split("```sql")[1].split(";")[0].strip()
    print(query)
    return query

# ============================================================
#  Execução de SQL
# ============================================================
def execute_sql_query(query: str):
    if not query:
        # ex: saudação
        return "Olá! Em que posso ajudar?"
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute(query)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows if rows else []
    except Exception as e:
        return f"Erro ao executar query: {str(e)}"

# ============================================================
#  SQL → Linguagem Natural 
# ============================================================
def sql_result_to_natural_language(question: str, sql_query: str, result):
    # Se for greeting curto-circuitado
    if is_greeting(question):
        return "Olá! Em que posso ajudar?"

    prompt = ChatPromptTemplate.from_messages([
        ("system",
         "You are an AI assistant that converts SQL database query results into natural language sentences. "
         "Always respond in European Portuguese and be concise and professional. "
         "Do not repeat the question and do not include follow-up prompts."
        ),
        ("user",
         f"Question: {question}\nSQL Query: {sql_query}\nSQL Result: {result}\n"
         "Produce one short sentence with the answer. If the result list is empty, say that nothing was found."
        ),
    ])

    formatted_prompt = (
        f"<|im_start|>system\n{prompt.format_messages()[0].content}<|im_end|>\n"
        f"<|im_start|>user\n{prompt.format_messages()[1].content}<|im_end|>\n"
        f"<|im_start|>assistant\n"
    )

    start = time.time()
    generated_text = ""
    for chunk in llm.stream(formatted_prompt):
        generated_text += chunk
    elapsed = time.time() - start
    print(f"⏱️ Tempo de inferência (NL): {elapsed:.2f}s")

   
    if "<|im_end|>" in generated_text:
        generated_text = generated_text.split("<|im_end|>")[0].strip()

    return generated_text.strip() or "Não foi possível gerar resposta."

# ============================================================
# 
# ============================================================
def is_visual_query(question: str) -> bool:
    visual_keywords = ["distribuição", "número", "quantos", "por dia", "por especialidade", "ao longo do tempo", "tendência","numero"]
    return any(kw in question.lower() for kw in visual_keywords)

def process_medical_query(question: str, cod_medico: int = None):
    """
    Processa a pergunta feita no dashboard médico.
    Se for saudação → responde direto
    Se bater em quick query → executa SQL fixo
    Caso contrário → usa LLM
    """

    # 1) Check saudação
    if is_greeting(question):
        return {"tipo": "texto", "mensagem": "Olá! Em que posso ajudar?", "sql": ""}

    # 2) Normaliza pergunta
    qnorm = question.strip().lower()

    # 3) Quick queries (caso haja cod_medico)
    if cod_medico is not None:
        for key, sql in QUICK_SQL_QUERIES.items():
            if key in qnorm:
                try:
                    conn = psycopg2.connect(**DB_CONFIG)
                    cur = conn.cursor()
                    cur.execute(sql, (cod_medico, cod_medico))
                    result = cur.fetchone()
                    cur.close()
                    conn.close()

                    count = result[0] if result else 0
                    # 🔹 Envia o resultado para o tradutor LLM
                    resposta = sql_result_to_natural_language(question, sql, [(count,)])
                    query_str = cur.mogrify(sql, (cod_medico, cod_medico)).decode("utf-8")
                    return {"tipo": "texto", "mensagem": f"{count}", "sql": query_str}
                except Exception as e:
                    return {"tipo": "erro", "mensagem": f"Erro ao executar query fixa: {str(e)}", "sql": query_str}

    # 4) Caso contrário → força o filtro do médico dentro do prompt
    if cod_medico is not None:
        question = f"{question} only for doctor id {cod_medico}"

    generated_sql = generate_query(question)
    result = safe_execute_wrapper(generated_sql)

    if isinstance(result, str):
        return {"tipo": "erro", "mensagem": result, "sql": generated_sql}

    if is_visual_query(question) and result and len(result[0]) == 2:
        return {"tipo": "grafico", "dados": result, "pergunta": question, "sql": generated_sql}

    resposta = sql_result_to_natural_language(question, generated_sql, result)
    return {"tipo": "texto", "mensagem": resposta, "sql": generated_sql}



def process_medical_query_patient(question: str, patient_id: int):
    if is_greeting(question):
        return {"tipo": "texto", "mensagem": "Olá! Em que posso ajudar?", "sql": ""}

    question_with_filter = f"{question} only for patient id {patient_id}"
    generated_sql = generate_query(question_with_filter)
    result = safe_execute_wrapper(generated_sql)

    if isinstance(result, str):
        return {"tipo": "erro", "mensagem": result, "sql": generated_sql}

    resposta = sql_result_to_natural_language(question, generated_sql, result)
    return {"tipo": "texto", "mensagem": resposta, "sql": generated_sql}

def process_medical_query_admin(question: str):
    if is_greeting(question):
        return {"tipo": "texto", "mensagem": "Olá! Em que posso ajudar?", "sql": ""}

    generated_sql = generate_query(question)
    result = safe_execute_wrapper(generated_sql)

    if isinstance(result, str):
        return {"tipo": "erro", "mensagem": result, "sql": generated_sql}

    if is_visual_query(question) and result and len(result[0]) == 2:
        return {"tipo": "grafico", "dados": result, "pergunta": question, "sql": generated_sql}

    resposta = sql_result_to_natural_language(question, generated_sql, result)
    return {"tipo": "texto", "mensagem": resposta, "sql": generated_sql}

# ============================================================
# Wrapper do validator.safe_execute para usar DB_CONFIG
# ============================================================
def safe_execute_wrapper(sql: str):
    if not sql:
        return "Olá!"
    try:
        # Usa o validator minimalista (só bloqueia DML e greetings)
        val = SQLValidator(SCHEMA)
        result = val.validate(sql, attempt_autofix=True)
        for it in result.issues:
            print(f"[{it.level}] {it.message}")

        if result.is_greeting:
            return "Olá!"

        if not result.ok:
            return "Ocorreu um erro de execução na base de dados. Não foi possível obter a informação"

        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute(result.sql_validated)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows
    except Exception as e:
        print("Erro ao executar SQL validado:", e)
        return "Ocorreu um erro de execução na base de dados. Não foi possível obter a informação"
