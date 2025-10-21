import os
import json
import psycopg2
from config import DB_CONFIG
from datetime import datetime, timedelta


def get_pacientes_total():
    query = """ SELECT DISTINCT p.num_sequencial, p.nome FROM pacientes p ORDER BY p.num_sequencial;"""

    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute(query)
        resultados = cur.fetchall()
        cur.close()
        conn.close()
        return [{"id": row[0], "nome": row[1]} for row in resultados]
    except Exception as e:
        print("Erro:", e)
        return []

    


def get_pacientes_do_medico(cod_medico: int) -> list[dict]:
    query = """
        SELECT DISTINCT p.num_sequencial, p.nome
        FROM   con_marcacoes m
        JOIN   pacientes p ON p.num_sequencial = m.num_sequencial
        LEFT JOIN con_med_esp cme 
               ON cme.cod_med_esp = m.cod_med_esp
              AND m.tip_agenda = 'E'
        WHERE (
                (m.tip_agenda = 'M' AND m.cod_med_esp = %s)
             OR (m.tip_agenda = 'E' AND cme.cod_medico = %s)
              )
          AND m.dta_consulta = CURRENT_DATE
        ORDER BY p.num_sequencial;
    """

    try:
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, (cod_medico, cod_medico))
                resultados = cursor.fetchall()
                return [{"id": row[0], "nome": row[1]} for row in resultados]
    except Exception as e:
        print(f" Erro ao obter pacientes do médico {cod_medico}: {e}")
        return []




# Carregar contas a partir do JSON
def load_accounts():
    # Caminho para o JSON de contas
    ACCOUNTS_FILE = os.path.join("static", "database", "accounts.json")
    try:
        with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def calcular_idade(data_nascimento):
    hoje = datetime.today()
    nascimento = datetime.strptime(data_nascimento, "%Y-%m-%d")
    return hoje.year - nascimento.year - ((hoje.month, hoje.day) < (nascimento.month, nascimento.day))

def traduzir_sexo(codigo):
    return "M" if codigo == "1" else "F" if codigo == "2" else "?"

def get_detalhes_paciente(paciente_id):
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    # 1. Dados principais do paciente
    cur.execute("""
        SELECT nome, data_nascimento, sexo 
        FROM pacientes 
        WHERE num_sequencial = %s
    """, (paciente_id,))
    nome, data_nascimento, sexo = cur.fetchone()

    idade = calcular_idade(str(data_nascimento))
    sexo_formatado = traduzir_sexo(sexo)

    # 2. Exames recentes
    cur.execute("""
        SELECT d.dataexame, e.designacaoigif
        FROM dexames d
        JOIN exames e ON d.numexame = e.numexame
        WHERE d.num_sequencial = %s AND d.dataexame IS NOT NULL
        ORDER BY d.dataexame DESC
        LIMIT 5
    """, (paciente_id,))
    exames = [{"data": row[0].strftime("%d/%m/%Y"), "nome": row[1].capitalize()} for row in cur.fetchall()]

    # 3. Consultas agendadas
    cur.execute("""
    SELECT dta_consulta, hora_consulta, tip_consulta
    FROM con_marcacoes
    WHERE num_sequencial = %s AND dta_consulta >= CURRENT_DATE
    ORDER BY dta_consulta ASC
    LIMIT 5 """, (paciente_id,))

    consultas = [{
    "data": row[0].strftime("%d/%m/%Y"),
    "hora": str(timedelta(seconds=row[1]))[:5],
    "tipo": "Primeira consulta" if row[2] == "P" else " Consulta subsequente" if row[2] == "S" else row[2]} for row in cur.fetchall()]
    cur.close()
    conn.close()

    return {
        "nome": nome,
        "data_nascimento": str(data_nascimento),
        "idade": idade,
        "sexo": sexo_formatado,
        "exames": exames,
        "consultas": consultas
    }



