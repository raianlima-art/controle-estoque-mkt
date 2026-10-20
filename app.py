import os
import pytz
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from flask import Flask, render_template, request, redirect, url_for, flash
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'chave_secreta_mkt'

SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

def get_sheets():
    """Autentica e retorna as abas do Google Sheets."""
    creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", SCOPE)
    client = gspread.authorize(creds)
    sheet = client.open("Controle de Estoque MKT - Produtos")
    return sheet.worksheet("Produtos"), sheet.worksheet("Movimentacoes")

def normalizar_dados_produtos(produtos_raw):
    """Normaliza as chaves do dicionário para evitar erros no HTML."""
    produtos_formatados = []
    for p in produtos_raw:
        item_id = p.get('ID', p.get('id', ''))
        nome = p.get('Produto', p.get('Nome', p.get('produto', '')))
        categoria = p.get('Categoria', p.get('categoria', 'Geral'))
        
        saldo = p.get('Saldo Em Estoque', p.get('Saldo em Estoque', p.get('Quantidade', p.get('quantidade', 0))))
        try:
            saldo = int(saldo) if str(saldo).isdigit() else 0
        except Exception:
            saldo = 0

        produtos_formatados.append({
            'ID': item_id,
            'Produto': nome,
            'Categoria': categoria,
            'Saldo': saldo
        })
    return produtos_formatados

@app.route('/')
def index():
    try:
        sheet_produtos, sheet_mov = get_sheets()
        produtos_raw = sheet_produtos.get_all_records()
        movimentacoes_raw = sheet_mov.get_all_records()
        
        produtos = normalizar_dados_produtos(produtos_raw)
        movimentacoes_recentes = movimentacoes_raw[-15:][::-1] if movimentacoes_raw else []
    except Exception as e:
        flash(f'Erro ao carregar dados do sistema: {e}', 'danger')
        produtos = []
        movimentacoes_recentes = []

    return render_template('index.html', produtos=produtos, movimentacoes=movimentacoes_recentes)

@app.route('/cadastrar', methods=['POST'])
def cadastrar():
    nome = request.form['nome']
    categoria = request.form['categoria']
    qtd_inicial = int(request.form.get('quantidade', 0))

    try:
        sheet_produtos, sheet_mov = get_sheets()
        produtos_raw = sheet_produtos.get_all_records()

        for p in produtos_raw:
            nome_p = p.get('Produto', p.get('Nome', ''))
            if str(nome_p).strip().lower() == nome.strip().lower():
                flash('Erro: Um produto com esse nome já existe!', 'danger')
                return redirect(url_for('index'))

        novo_id = len(produtos_raw) + 1
        # Registra o novo produto na aba Produtos
        sheet_produtos.append_row([novo_id, nome, categoria, qtd_inicial])

        # Se houver quantidade inicial maior que zero, registra no histórico de movimentação
        if qtd_inicial > 0:
            fuso_br = pytz.timezone('America/Sao_Paulo')
            data_hora = datetime.now(fuso_br).strftime('%d/%m/%Y %H:%M:%S')
            sheet_mov.append_row([data_hora, nome, 'Entrada', qtd_inicial, 'Cadastro inicial de estoque'])

        flash('Produto cadastrado com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao cadastrar produto: {e}', 'danger')

    return redirect(url_for('index'))

@app.route('/movimentar', methods=['POST'])
def movimentar():
    nome_produto = request.form['produto_id']
    tipo = request.form['tipo']
    qtd = int(request.form['quantidade'])
    obs = request.form['observacao']

    try:
        sheet_produtos, sheet_mov = get_sheets()
        cell = sheet_produtos.find(nome_produto)
        if not cell:
            flash('Produto não encontrado no sistema!', 'danger')
            return redirect(url_for('index'))

        linha = cell.row
        val_atual = sheet_produtos.cell(linha, 4).value
        qtd_atual = int(val_atual) if str(val_atual).isdigit() else 0

        if tipo == 'Saida' and qtd > qtd_atual:
            flash(f'Erro: Estoque insuficiente! Saldo atual: {qtd_atual}', 'warning')
            return redirect(url_for('index'))

        nova_qtd = (qtd_atual + qtd) if tipo == 'Entrada' else (qtd_atual - qtd)
        sheet_produtos.update_cell(linha, 4, nova_qtd)

        # Grava a data e hora em formato brasileiro no Histórico de Movimentações
        fuso_br = pytz.timezone('America/Sao_Paulo')
        data_hora = datetime.now(fuso_br).strftime('%d/%m/%Y %H:%M:%S')
        sheet_mov.append_row([data_hora, nome_produto, tipo, qtd, obs])

        flash(f'Movimentação de {tipo} registrada com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao registrar movimentação: {e}', 'danger')

    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)