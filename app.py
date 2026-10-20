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
    """Autentica e retorna as abas do Google Sheets de forma otimizada."""
    creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", SCOPE)
    client = gspread.authorize(creds)
    sheet = client.open("Controle de Estoque MKT - Produtos")
    return sheet.worksheet("Produtos"), sheet.worksheet("Movimentacoes")

def normalizar_dados_produtos(produtos_raw):
    """Normaliza as chaves da planilha de produtos."""
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

def extrair_mes_ano(data_str):
    """Extrai YYYY-MM para ordenação e filtro independente do formato da data."""
    data_str = str(data_str).strip()
    try:
        if '-' in data_str[:10]: # Formato YYYY-MM-DD
            partes = data_str[:10].split('-')
            return f"{partes[0]}-{partes[1]}"
        elif '/' in data_str[:10]: # Formato DD/MM/YYYY
            partes = data_str[:10].split('/')
            return f"{partes[2]}-{partes[1]}"
    except Exception:
        pass
    fuso_br = pytz.timezone('America/Sao_Paulo')
    return datetime.now(fuso_br).strftime('%Y-%m')

def normalizar_dados_movimentacoes(movimentacoes_raw):
    """Normaliza e extrai data/hora e mês/ano das movimentações."""
    movimentacoes_formatadas = []
    for m in movimentacoes_raw:
        data_hora = (
            m.get('Data_Hora') or 
            m.get('Data/Hora') or 
            m.get('Data / Hora') or 
            m.get('Data') or 
            m.get('DataHora') or 
            'Sem data'
        )
        
        produto = m.get('Produto', m.get('produto', ''))
        tipo = m.get('Tipo', m.get('tipo', ''))
        qtd = m.get('Quantidade', m.get('Qtd', m.get('quantidade', 0)))
        obs = m.get('Observacao', m.get('Observação', m.get('observacao', '')))
        
        mes_ano = extrair_mes_ano(data_hora)

        movimentacoes_formatadas.append({
            'DataHora': str(data_hora),
            'Produto': produto,
            'Tipo': tipo,
            'Quantidade': qtd,
            'Observacao': obs,
            'MesAno': mes_ano
        })
    return movimentacoes_formatadas

@app.route('/')
def index():
    try:
        sheet_produtos, sheet_mov = get_sheets()
        produtos_raw = sheet_produtos.get_all_records()
        movimentacoes_raw = sheet_mov.get_all_records()
        
        produtos = normalizar_dados_produtos(produtos_raw)
        movimentacoes = normalizar_dados_movimentacoes(movimentacoes_raw)
        movimentacoes_ordenadas = movimentacoes[::-1] if movimentacoes else []
        
        # Mês vigente atual (Ex: '2026-10')
        fuso_br = pytz.timezone('America/Sao_Paulo')
        mes_vigente = datetime.now(fuso_br).strftime('%Y-%m')
        
        # Coleta lista de meses únicos disponíveis no histórico
        meses_disponiveis = sorted(list(set(m['MesAno'] for m in movimentacoes if m['MesAno'] != 'Sem data')), reverse=True)
        if mes_vigente not in meses_disponiveis:
            meses_disponiveis.insert(0, mes_vigente)

    except Exception as e:
        flash(f'Erro ao carregar dados do sistema: {e}', 'danger')
        produtos = []
        movimentacoes_ordenadas = []
        meses_disponiveis = []
        fuso_br = pytz.timezone('America/Sao_Paulo')
        mes_vigente = datetime.now(fuso_br).strftime('%Y-%m')

    return render_template(
        'index.html', 
        produtos=produtos, 
        movimentacoes=movimentacoes_ordenadas,
        meses_disponiveis=meses_disponiveis,
        mes_vigente=mes_vigente
    )

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
        sheet_produtos.append_row([novo_id, nome, categoria, qtd_inicial])

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
        produtos_raw = sheet_produtos.get_all_records()
        
        linha_index = None
        qtd_atual = 0
        
        for idx, p in enumerate(produtos_raw, start=2):
            nome_p = p.get('Produto', p.get('Nome', ''))
            if str(nome_p).strip() == str(nome_produto).strip():
                linha_index = idx
                val_atual = p.get('Saldo Em Estoque', p.get('Saldo em Estoque', p.get('Quantidade', 0)))
                qtd_atual = int(val_atual) if str(val_atual).isdigit() else 0
                break

        if not linha_index:
            flash('Produto não encontrado no sistema!', 'danger')
            return redirect(url_for('index'))

        if tipo == 'Saida' and qtd > qtd_atual:
            flash(f'Erro: Estoque insuficiente! Saldo atual: {qtd_atual}', 'warning')
            return redirect(url_for('index'))

        nova_qtd = (qtd_atual + qtd) if tipo == 'Entrada' else (qtd_atual - qtd)
        sheet_produtos.update_cell(linha_index, 4, nova_qtd)

        fuso_br = pytz.timezone('America/Sao_Paulo')
        data_hora = datetime.now(fuso_br).strftime('%d/%m/%Y %H:%M:%S')
        sheet_mov.append_row([data_hora, nome_produto, tipo, qtd, obs])

        flash(f'Movimentação de {tipo} registrada com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao registrar movimentação: {e}', 'danger')

    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)