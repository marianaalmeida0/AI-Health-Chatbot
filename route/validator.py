# validator.py
import re
import sqlparse
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional

# === DDL REAL ===
SCHEMA: Dict[str, Dict[str, str]] = {
    "sys_medicos": {"num_ord_medico": "INT", "nome": "TEXT"},
    "sys_especialidades": {"cod_especialidade": "INT", "des_especialidade": "VARCHAR"},
    "con_med_esp": {"cod_med_esp": "INT", "cod_especialidade": "INT", "cod_medico": "INT"},
    "pacientes": {
        "num_sequencial": "INT",
        "nome": "VARCHAR",
        "data_nascimento": "DATE",
        "sexo": "VARCHAR",
        "num_processo": "INT",
    },
    "dpedidos": {
        "numpedido": "VARCHAR",
        "episodio": "INT",
        "modulo": "VARCHAR",
        "designamodulo": "VARCHAR",
        "idser": "VARCHAR",
        "servico": "VARCHAR",
        "datapedido": "DATE",
        "posto": "VARCHAR",
        "num_sequencial": "INT",
        "datanascimento": "DATE",
        "sexo": "CHAR",
        "modalidade": "VARCHAR",
        "numexame": "VARCHAR",
        "marcado": "VARCHAR",
        "fechado": "VARCHAR",
        "segura": "VARCHAR",
        "utiliza": "INT",
        "dataexame": "DATE",
        "datamarcacao": "DATE",
    },
    "dexames": {
        "numexame": "VARCHAR",
        "episodio": "INT",
        "modulo": "VARCHAR",
        "designamodulo": "VARCHAR",
        "idser": "VARCHAR",
        "servico": "VARCHAR",
        "datapedido": "DATE",
        "posto": "VARCHAR",
        "num_sequencial": "INT",
        "datanascimento": "DATE",
        "sexo": "CHAR",
        "modalidade": "VARCHAR",
        "relatorio": "TEXT",
        "pathrelatorio": "TEXT",
        "fechado": "VARCHAR",
        "segura": "VARCHAR",
        "utiliza": "VARCHAR",
        "dataexame": "DATE",
    },
    "con_diarios": {"id_diario": "INT", "episodio": "INT", "diario": "VARCHAR", "cod_medico": "INT", "data_diario": "DATE"},
    "tabigif": {"cigif": "VARCHAR", "idser": "VARCHAR", "servico": "VARCHAR", "modalidade": "VARCHAR", "digif": "VARCHAR", "tipo_am": "VARCHAR", "ativo": "VARCHAR"},
    "pedidos": {"numpedido": "VARCHAR", "ordem": "INT", "idser": "VARCHAR", "modalidade": "VARCHAR", "cod_pedido": "VARCHAR", "des_pedido": "TEXT"},
    "exames": {"numexame": "VARCHAR", "versao": "INT", "ordem": "INT", "idser": "VARCHAR", "codigif": "VARCHAR", "designacaoigif": "VARCHAR", "verificado": "VARCHAR", "facturado": "VARCHAR"},
    "con_marcacoes": {"num_sequencial": "INT", "cod_med_esp": "INT", "tip_consulta": "VARCHAR", "dta_consulta": "DATE", "hora_consulta": "INT", "cod_sala": "VARCHAR", "cod_especialidade": "INT", "tip_agenda": "CHAR"},
    "con_registadas": {"episodio": "INT", "num_sequencial": "INT", "cod_med_esp": "INT", "tip_consulta": "VARCHAR", "dta_realizacao": "DATE", "hora_realizacao": "INT", "cod_sala": "VARCHAR", "cod_especialidade": "INT", "tip_agenda": "CHAR"},
}
GREETINGS = {"olá", "ola", "oi", "bom dia", "boa tarde", "boa noite", "hello", "hi", "hey"}
DML_PATTERN = re.compile(r"\b(INSERT|UPDATE|DELETE|ALTER|DROP|TRUNCATE|CREATE)\b", re.I)

# === Aliases automáticos (apenas hints, não bloqueiam execução) ===
RESERVED_KEYWORDS = {"as", "or", "and", "by", "in", "is", "not", "to", "on"}

def generate_aliases_dict(table_names: List[str]) -> Dict[str, str]:
    aliases = {}
    for t in table_names:
        t_clean = t.split(".")[-1]
        if "_" in t_clean:
            alias = "".join([w[0] for w in t_clean.split("_")]).lower()
        else:
            alias = t_clean[:2].lower()
        if alias in aliases.values() or alias in RESERVED_KEYWORDS:
            alias = t_clean[:3].lower()
        num = 2
        while alias in aliases.values() or alias in RESERVED_KEYWORDS:
            alias = t_clean[0].lower() + str(num)
            num += 1
        aliases[t_clean] = alias
    return aliases

def mk_alias_str(table_aliases: Dict[str, str]) -> str:
    """Gera uma string de comentários tipo:
       -- sys_medicos AS sm
       -- con_marcacoes AS cm
    """
    return "\n".join([f"-- {t} AS {a}" for t, a in table_aliases.items()])


# === Estruturas de validação ===
@dataclass
class ValidationIssue:
    level: str
    message: str

@dataclass
class ValidationResult:
    ok: bool
    sql_original: str
    sql_validated: str
    issues: List[ValidationIssue] = field(default_factory=list)
    is_greeting: bool = False
    aliases: Dict[str, str] = field(default_factory=dict)

class SQLValidator:
    def __init__(self, schema: Dict[str, Dict[str, str]]):
        self.schema = {t.lower(): {c.lower(): v.upper() for c, v in cols.items()} for t, cols in schema.items()}
        self.aliases_dict = generate_aliases_dict(list(self.schema.keys()))

    def _rule_greeting(self, sql: str, issues: List[ValidationIssue]) -> bool:
        q_clean = re.sub(r"[^\w\s]", "", sql.strip().lower())
        if q_clean in GREETINGS:
            issues.append(ValidationIssue("INFO", "Greeting detected, no SQL execution needed."))
            return True
        return False

    def _normalize(self, sql: str) -> str:
        return sqlparse.format(sql, keyword_case="upper", identifier_case="lower", strip_comments=True, reindent=True)

    def validate(self, sql: str, attempt_autofix: bool = True) -> ValidationResult:
        original = sql.strip()
        issues: List[ValidationIssue] = []

        if self._rule_greeting(original, issues):
            return ValidationResult(False, original, "", issues, is_greeting=True, aliases=self.aliases_dict)

        normalized = self._normalize(original)

        # ⚠️ Só bloqueia DML
        if DML_PATTERN.search(normalized):
            issues.append(ValidationIssue("ERROR", "DML statements não permitidos (INSERT/UPDATE/DELETE/ALTER/...)."))
            return ValidationResult(False, original, normalized, issues, aliases=self.aliases_dict)

        return ValidationResult(True, original, normalized, issues, aliases=self.aliases_dict)


# === Execução segura ===
def safe_execute(connection, sql: str, validator: Optional[SQLValidator] = None):
    if validator is None:
        validator = SQLValidator(SCHEMA)
    result = validator.validate(sql, attempt_autofix=True)

    for it in result.issues:
        print(f"[{it.level}] {it.message}")

    if result.is_greeting:
        return "Olá!"

    if not result.ok:
        return "Ocorreu um erro de execução na base de dados. Não foi possível obter a informação"

    try:
        cur = connection.cursor()
        cur.execute(result.sql_validated)
        rows = cur.fetchall()
        cur.close()
        return rows
    except Exception as e:
        print("Erro ao executar SQL validado:", e)
        return "Ocorreu um erro de execução na base de dados. Não foi possível obter a informação"
