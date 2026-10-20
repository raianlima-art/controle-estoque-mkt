import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from flask import Flask, render_template, request, redirect, url_for, flash
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'chave_secreta_mkt'

# Configuração de Autenticação com o Google Sheets
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

def get_sheets():
    """Autentica e conecta com a Planilha Google usando o arquivo credentials.json."""
    creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", SCOPE)
    client = gspread.authorize(creds)
    
    # Abre a planilha pelo nome exato
    sheet = client.open("Controle de Estoque MKT - Produtos")
    return sheet.worksheet("Produtos"), sheet.worksheet("Movimentacoes")

@app.route('/')
def index():
    try:
        sheet_produtos, sheet_mov = get_sheets()
        
        # Obtém todos os registros como listas de dicionários
        produtos = sheet_produtos.get_all_records()
        movimentacoes = sheet_mov.get_all_records()
        
        # Pega as últimas 10 movimentações em ordem reversa
        movimentacoes_recentes = movimentacoes[-10:][::-1]
        
    except Exception as e:
        flash(f'Erro ao conectar com o Google Sheets: {e}', 'danger')
        produtos = []
        movimentacoes_recentes = []

    return render_template('index.html', produtos=produtos, movimentacoes=movimentacoes_recentes)

@app.route('/cadastrar', methods=['POST'])
def cadastrar():
    nome = request.form['nome']
    categoria = request.form['categoria']
    qtd_inicial = int(request.form.get('quantidade', 0))

    try:
        sheet_produtos, _ = get_sheets()
        produtos = sheet_produtos.get_all_records()

        # Verifica se já existe um produto com o mesmo nome
        for p in produtos:
            if str(p.get('Nome')).strip().lower() == nome.strip().lower():
                flash('Erro: Um produto com esse nome já existe na planilha!', 'danger')
                return redirect(url_for('index'))

        novo_id = len(produtos) + 1
        # Adiciona nova linha na aba Produtos [ID, Nome, Categoria, Quantidade]
        sheet_produtos.append_row([novo_id, nome, categoria, qtd_inicial])
        flash('Produto cadastrado com sucesso no Google Sheets!', 'success')
    except Exception as e:
        flash(f'Erro ao cadastrar produto: {e}', 'danger')

    return redirect(url_for('index'))

@app.route('/movimentar', methods=['POST'])
def movimentar():
    nome_produto = request.form['produto_id']  # Recebe o nome/identificador do produto
    tipo = request.form['tipo']
    qtd = int(request.form['quantidade'])
    obs = request.form['observacao']

    try:
        sheet_produtos, sheet_mov = get_sheets()
        
        # Procura a linha do produto na aba 'Produtos'
        cell = sheet_produtos.find(nome_produto)
        if not cell:
            flash('Produto não encontrado na planilha!', 'danger')
            return redirect(url_for('index'))

        linha = cell.row
        qtd_atual = int(sheet_produtos.cell(linha, 4).value)  # Coluna 4 é Quantidade

        # Validação de Estoque Negativo
        if tipo == 'Saida' and qtd > qtd_atual:
            flash(f'Erro: Estoque insuficiente! Saldo atual na planilha: {qtd_atual}', 'warning')
            return redirect(url_for('index'))

        nova_qtd = (qtd_atual + qtd) if tipo == 'Entrada' else (qtd_atual - qtd)

        # Atualiza a Quantidade na aba 'Produtos'
        sheet_produtos.update_cell(linha, 4, nova_qtd)

        # Registra no histórico da aba 'Movimentacoes'
        data_hora = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        sheet_mov.append_row([data_hora, nome_produto, tipo, qtd, obs])

        flash(f'Movimentação de {tipo} salva com sucesso no Google Sheets!', 'success')
    except Exception as e:
        flash(f'Erro ao registrar movimentação: {e}', 'danger')

    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)