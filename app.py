
from flask import Flask, request, render_template, session, redirect, url_for, jsonify,send_file,Response
from route.bot import process_medical_query, process_medical_query_patient,process_medical_query_admin
import os
import json
import psycopg2
from config import DB_CONFIG
from utils import get_pacientes_do_medico, load_accounts, calcular_idade, traduzir_sexo, get_detalhes_paciente, get_pacientes_total
from datetime import datetime
import csv, io, tempfile
from fpdf import FPDF   
from datetime import date

app = Flask(__name__)
app.secret_key = os.urandom(24)  # Chave secreta para sessão




# Página de Login
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        accounts = load_accounts()
        if username in accounts and accounts[username] == password:

            if not username.isdigit() and username != "admin":
                error = "Nome de utilizador inválido. Use apenas o número da ordem do médico ou 'admin'."
                return render_template("login.html", error=error)

            session['user'] = username

            if username == "admin":
                session["nome_medico"] = "Administrador"
                pacientes = get_pacientes_total()
                return render_template("dashboard_admin.html", username="admin", pacientes=pacientes)

            # Só aqui faz int(), pois temos a certeza que é numérico
            cod_medico = int(username)

            # Buscar nome do médico
            connection = psycopg2.connect(**DB_CONFIG)
            cur = connection.cursor()
            cur.execute("SELECT nome FROM sys_medicos WHERE num_ord_medico = %s", (cod_medico,))
            row = cur.fetchone()
            session["nome_medico"] = row[0] if row else "Desconhecido"
            cur.close()
            connection.close()

            pacientes = get_pacientes_do_medico(cod_medico)
            return render_template("dashboard.html", username=username, nome_medico=session["nome_medico"], pacientes=pacientes)

        else:
            error = "Nome de utilizador ou password inválidos. Tente novamente."
            return render_template("login.html", error=error)

    return render_template("login.html")

# Página Principal

@app.route("/dashboard")
def dashboard():
    if 'user' in session:
        username = session.get("user")
        if username == "admin":
            pacientes= get_pacientes_total()
            print("AQUII", pacientes)
            return render_template("dashboard_admin.html", username=session['user'], pacientes=pacientes)
        cod_medico = session['user']
        pacientes = get_pacientes_do_medico(cod_medico)  #  aqui é uma lista de dicionários [{id: 1, nome: "Maria"}]
        print(pacientes)
        return render_template("dashboard.html", username=session['user'], nome_medico=session.get("nome_medico", "Médico"), pacientes=pacientes)
    else:
        return redirect(url_for("login"))

# Rota de Logout
@app.route("/logout")
def logout():
    session.clear()  # Limpar a sessão
    return redirect(url_for("login"))

# Rota para detalhes do paciente
@app.route("/detalhes/<int:paciente_id>")
def detalhes_paciente(paciente_id):
    paciente = get_detalhes_paciente(paciente_id)
    return render_template("chatbot_paciente.html", paciente=paciente, paciente_id=paciente_id)

@app.route("/consulta", methods=["POST"])
def consulta():
    data = request.get_json()
    pergunta = data.get("mensagem")

    cod_medico = None
    if "user" in session and session["user"] != "admin":
        cod_medico = int(session["user"])  # número da ordem do médico

    resposta = process_medical_query(pergunta, cod_medico=cod_medico)

    if resposta["tipo"] == "erro":
        return jsonify({
            "tipo": "erro",
            "resposta": resposta["mensagem"]
        })
    else:
        return jsonify({
            "tipo": resposta["tipo"],
            "resposta": resposta["mensagem"],
            "sql": resposta.get("sql", "")
        })


@app.route("/consulta_admin", methods=["POST"])
def consulta_admin():
    data = request.get_json()
    pergunta = data.get("mensagem")

    resposta = process_medical_query_admin(pergunta)

    if resposta["tipo"] == "erro":
        return jsonify({
            "tipo": "erro",
            "resposta": resposta["mensagem"],
            "sql": resposta.get("sql", "")
        })
    elif resposta["tipo"] == "grafico":
        return jsonify({
            "tipo": "grafico",
            "dados": resposta["dados"],       # <-- devolve dados para Chart.js
            "pergunta": resposta["pergunta"],
            "sql": resposta.get("sql", "")
        })
    else:
        return jsonify({
            "tipo": "texto",
            "resposta": resposta["mensagem"],
            "sql": resposta.get("sql", "")
        })



@app.route("/consulta_paciente", methods=["POST"])
def consulta_paciente():
    data = request.get_json()
    question = data.get("mensagem")
    patient_id = data.get("paciente_id")

    if not question or not patient_id:
        return jsonify({"erro": "Faltam parâmetros obrigatórios."}), 400
    
    resposta = process_medical_query_patient(question, patient_id)
    return jsonify({"resposta": resposta})


@app.route("/export_pacientes")
def export_pacientes():
    formato = request.args.get("fmt", "csv")   # ?fmt=csv  ou  ?fmt=pdf
    rows  = [(p["id"], p["nome"]) for p in get_pacientes_total()]

    if formato == "pdf":
        pdf = FPDF(orientation="P", unit="mm", format="A4")
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        pdf.set_font("Helvetica", size=14)
        pdf.cell(0, 10, "Lista de Pacientes", ln=1, align="C")
        pdf.ln(4)
        pdf.set_font(size=11)
        for rid, nome in rows:
            pdf.cell(30, 8, str(rid), border=0)
            pdf.cell(0, 8, nome, border=0, ln=1)
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        pdf.output(tmp.name)
        return send_file(tmp.name,
                         as_attachment=True,
                         download_name=f"pacientes_{date.today()}.pdf")

    # default CSV
    si = io.StringIO()
    si.write("\ufeff") 
    cw = csv.writer(si)
    cw.writerow(["id_paciente", "nome_paciente"])
    cw.writerows(rows)
    return Response(si.getvalue(),
                    mimetype="text/csv",
                    headers={"Content-Disposition":
                             f"attachment;filename=pacientes_{date.today()}.csv"})    

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5001,debug=True, use_reloader= False)

