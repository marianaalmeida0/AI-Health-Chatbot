import psycopg2
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
import os
import torch
from langchain_community.llms import LlamaCpp
#from langchain.llms import LlamaCpp
from langchain_core.prompts import ChatPromptTemplate
import datetime
from config import DB_CONFIG
import pickle
import os

from validator import SQLValidator,SCHEMA, mk_alias_str
validator = SQLValidator(SCHEMA)
aliases_str = mk_alias_str(validator.aliases_dict)

# ** Carregar o Modelo SQLCoder **
model_name = "defog/llama-3-sqlcoder-8b"
tokenizer = AutoTokenizer.from_pretrained(model_name)
bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,  
    bnb_4bit_use_double_quant=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.float16
)

# Verificar a memória disponível na GPU
available_memory = torch.cuda.mem_get_info()[0] if torch.cuda.is_available() else 0

if available_memory > 20e9:  # Se tiver pelo menos 20GB de VRAM
    print("🔹 GPU com memória suficiente! Carregando em float16...")
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        trust_remote_code=True,
        torch_dtype=torch.float16,
        device_map="auto",
        use_cache=True,
        offload_folder="offload",  # Pasta para armazenar camadas descarregadas
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
        offload_folder="offload",  # Pasta para armazenar camadas descarregadas
        offload_state_dict=False,
    )

print(torch.cuda.memory_allocated() / 1024**2, "MiB alocados inicialmente")
print(torch.cuda.memory_reserved() / 1024**2, "MiB reservados")

# ** Carregar o Modelo LLamaCpp para NLP **
n_gpu_layers = -1  
n_batch = 512  
n_ctx = 2048 

llm = LlamaCpp(
    model_path="../models/model_Q5_K_S.gguf",
    temperature=0,
    max_tokens=500,  
    n_ctx=n_ctx,
    top_p=1,
    n_threads=8,
    verbose=True,
    f16_kv=True,
    n_gpu_layers=0,
    n_batch=n_batch,
    chat_format="chatml"
)


# ** Função para Gerar a Query SQL **
def generate_query(question):

    prompt = f"""<|begin_of_text|><|start_header_id|>user<|end_header_id|>

Generate a SQL query to answer this question: `{question}`

- Given an input question, create a syntactically correct query to run, then look at the results of the query and return the answer.
- If the question is unrelated to the medical or clinical database context (e.g., greetings, general knowledge, jokes, or chit-chat), respond with: "I am a medical database assistant. Please ask about consultations, exams, or patients."
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

DDL statements:
`{ddl_statments}`
`{aliases_str}`

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

    inputs = tokenizer(prompt, return_tensors="pt").to("cuda" if torch.cuda.is_available() else "cpu")
    generated_ids = model.generate(
        **inputs, num_return_sequences=1, eos_token_id=tokenizer.eos_token_id, 
        pad_token_id=tokenizer.eos_token_id, max_new_tokens=600, do_sample=False, num_beams=2, temperature=0.0, top_p=None
    )
    outputs = tokenizer.batch_decode(generated_ids, skip_special_tokens=True )#True
    torch.cuda.empty_cache()
    torch.cuda.synchronize()


    query = outputs[0].split("```sql")[1].split(";")[0].strip()
    print(query)
    
    return query
    
# ** Função para Executar a Query no PostgreSQL **
def execute_sql_query(query):
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute(query)
        result = cursor.fetchall()
        print(result)
        cursor.close()
        conn.close()
        return result if result else []
    except Exception as e:
        return f"Erro ao executar query: {str(e)}"



# ** Função para Converter SQL para Linguagem Natural **
def sql_result_to_natural_language(llm,question, sql_query, result):
   
# **Criar o prompt**
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an AI assistant that converts SQL database query results into natural language sentences. "
                   "Make the answer clear as if reporting to a doctor or hospital administrator"
                    "Do not repeat the question and do not include follow-up prompts.\n\n"),
        
        ("user", f"""Question: {question}
    SQL Query: {sql_query}
    SQL Result: {result}
    
    Translate this SQL result into a short and clear response in Portuguese of Portugal."""),
    ])

   #  **Converter para string no formato correto**
    formatted_prompt = f"""<|im_start|>system
    {prompt.format_messages()[0].content}<|im_end|>
    <|im_start|>user
    {prompt.format_messages()[1].content}<|im_end|>
    <|im_start|>assistant
    """
    
    #  **Executar a inferência**
    print("\n🔹 Gerando resposta...")
    
    generated_text = ""
    for chunk in llm.stream(formatted_prompt):
        print(chunk, end="", flush=True)  
        generated_text += chunk
    
    # **Formatar saída final**
     if "<|im_end|>" in generated_text:
    
        response = generated_text.split("<|im_end|>")[0].strip()
    else:
        response = generated_text.strip()

    return response
    

def is_visual_query(question: str) -> bool:
    visual_keywords = ["distribuição", "número", "quantos", "por dia", "por especialidade", "ao longo do tempo", "tendência"]
    return any(kw in question.lower() for kw in visual_keywords)


def process_medical_query(question: str):
    """
    Chatbot normal (médico) -> responde sobre consultas, exames e pacientes.
    """
    sql_query = generate_query(question)
    result = execute_sql_query(sql_query)

    if isinstance(result, str):
        return {"tipo": "erro", "mensagem": result}

    if is_visual_query(question) and result and len(result[0]) == 2:
        return {"tipo": "grafico", "dados": result, "pergunta": question, "sql": sql_query}

    resposta = sql_result_to_natural_language(llm, question, sql_query, result)
    return {"tipo": "texto", "mensagem": resposta, "sql": sql_query}


def process_medical_query_patient(question: str, patient_id: int):
    """
    Chatbot do paciente -> força o filtro pelo paciente_id.
    """
    # Garantir que a query sempre inclui o paciente
    question_with_filter = f"{question} only for patient id {patient_id}"
    sql_query = generate_query(question_with_filter)
    result = execute_sql_query(sql_query)

    if isinstance(result, str):
        return {"tipo": "erro", "mensagem": result}

    resposta = sql_result_to_natural_language(llm, question, sql_query, result)
    return {"tipo": "texto", "mensagem": resposta, "sql": sql_query}


def process_medical_query_admin(question: str):
    """
    Chatbot do administrador -> pode responder com gráficos globais.
    """
    sql_query = generate_query(question)
    result = execute_sql_query(sql_query)

    if isinstance(result, str):
        return {"tipo": "erro", "mensagem": result}

    # Administrador deve ver gráficos sempre que possível
    if is_visual_query(question) and result and len(result[0]) == 2:
        return {"tipo": "grafico", "dados": result, "pergunta": question, "sql": sql_query}

    resposta = sql_result_to_natural_language(llm, question, sql_query, result)
    return {"tipo": "texto", "mensagem": resposta, "sql": sql_query}


