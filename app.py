import os
import pytz
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from flask import Flask, render_template, request, redirect, url_for, flash
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'chave_secreta_mkt'

# Novo ID da pasta 'Fotos Estoque MKT' dentro do Drive Compartilhado 'Compras'
DRIVE_FOLDER_ID = "193W91ecaAJIS_I-ekRl-HUKa_XDkHzYC"

SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

def get_drive_and_sheets():
    """Autentica e retorna os serviços do Google Drive e do Google Sheets."""
    creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", SCOPE)
    
    client = gspread.authorize(creds)
    sheet = client.open("Controle de Estoque MKT - Produtos")
    
    drive_service = build('drive', 'v3', credentials=creds)
    
    return drive_service, sheet.worksheet("Produtos"), sheet.worksheet("Movimentacoes")

def salvar_foto_no_drive(drive_service, file_storage):
    """Realiza o upload da foto diretamente para a pasta no Drive Compartilhado."""
    if not file_storage or file_storage.filename == '':
        return ""

    caminho_temp = os.path.join("/tmp" if os.name != 'nt' else ".", file_storage.filename)
    file_storage.save(caminho_temp)

    try:
        nome_arquivo = f"produto_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file_storage.filename}"
        media = MediaFileUpload(caminho_temp, mimetype=file_storage.mimetype, resumable=True)
        
        file_metadata = {
            'name': nome_arquivo,
            'parents': [DRIVE_FOLDER_ID]
        }
        
        # Envia o arquivo com suporte a Drives Compartilhados ativado
        arquivo_drive = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id',
            supportsAllDrives=True,
            supportsTeamDrives=True
        ).execute()

        file_id = arquivo_drive.get('id')

        # Concede permissão de leitura pública para renderizar a miniatura na tabela do site
        try:
            drive_service.permissions().create(
                fileId=file_id,
                body={'type': 'anyone', 'role': 'reader'},
                supportsAllDrives=True,
                supportsTeamDrives=True
            ).execute()
        except Exception:
            pass

        return f"https://lh3.googleusercontent.com/d/{file_id}"

    finally:
        if os.path.exists(caminho_temp):
            os.remove(caminho_temp)

@app.route('/')
def index():
    try:
        _, sheet_produtos, sheet_mov = get_drive_and_sheets()
        produtos = sheet_produtos.get_all_records()
        movimentacoes = sheet_mov.get_all_records()
        movimentacoes_recentes = movimentacoes[-10:][::-1]
    except Exception as e:
        flash(f'Erro ao carregar os dados do sistema: {e}', 'danger')
        produtos = []
        movimentacoes_recentes = []

    return render_template('index.html', produtos=produtos, movimentacoes=movimentacoes_recentes)

@app.route('/cadastrar', methods=['POST'])
def cadastrar():
    nome = request.form['nome']
    categoria = request.form['categoria']
    qtd_inicial = int(request.form.get('quantidade', 0))
    file_foto = request.files.get('foto')

    try:
        drive_service, sheet_produtos, _ = get_drive_and_sheets()
        produtos = sheet_produtos.get_all_records()

        for p in produtos:
            if str(p.get('Nome')).strip().lower() == nome.strip().lower():
                flash('Erro: Um produto com esse nome já existe no sistema!', 'danger')
                return redirect(url_for('index'))

        # Envia a foto para a nova pasta no Drive Compartilhado
        foto_url = salvar_foto_no_drive(drive_service, file_foto)

        novo_id = len(produtos) + 1
        # Regista na planilha [ID, Nome, Categoria, Quantidade, Foto]
        sheet_produtos.append_row([novo_id, nome, categoria, qtd_inicial, foto_url])
        flash('Produto cadastrado e foto enviada com sucesso!', 'success')
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
        _, sheet_produtos, sheet_mov = get_drive_and_sheets()
        cell = sheet_produtos.find(nome_produto)
        if not cell:
            flash('Produto não encontrado no sistema!', 'danger')
            return redirect(url_for('index'))

        linha = cell.row
        qtd_atual = int(sheet_produtos.cell(linha, 4).value)

        if tipo == 'Saida' and qtd > qtd_atual:
            flash(f'Erro: Estoque insuficiente! Saldo atual: {qtd_atual}', 'warning')
            return redirect(url_for('index'))

        nova_qtd = (qtd_atual + qtd) if tipo == 'Entrada' else (qtd_atual - qtd)
        sheet_produtos.update_cell(linha, 4, nova_qtd)

        fuso_br = pytz.timezone('America/Sao_Paulo')
        data_hora = datetime.now(fuso_br).strftime('%Y-%m-%d %H:%M:%S')
        sheet_mov.append_row([data_hora, nome_produto, tipo, qtd, obs])

        flash(f'Movimentação de {tipo} realizada com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao registrar movimentação: {e}', 'danger')

    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)