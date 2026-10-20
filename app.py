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

# ID da pasta 'Fotos Estoque MKT'
DRIVE_FOLDER_ID = "1VfYSxih1ZiQYUTnTWsxPQntv-qKej"

SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

def get_drive_and_sheets():
    """Autentica e retorna os serviços do Google Drive e do Google Sheets."""
    creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", SCOPE)
    
    # Cliente do Sheets
    client = gspread.authorize(creds)
    sheet = client.open("Controle de Estoque MKT - Produtos")
    
    # Serviço da API do Google Drive para upload
    drive_service = build('drive', 'v3', credentials=creds)
    
    return drive_service, sheet.worksheet("Produtos"), sheet.worksheet("Movimentacoes")

def salvar_foto_no_drive(drive_service, file_storage):
    """Salva o arquivo temporariamente e realiza o upload para o Google Drive."""
    if not file_storage or file_storage.filename == '':
        return ""

    # Salva temporariamente no disco local
    caminho_temp = os.path.join("/tmp" if os.name != 'nt' else ".", file_storage.filename)
    file_storage.save(caminho_temp)

    try:
        # Metadados do arquivo
        file_metadata = {
            'name': f"produto_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file_storage.filename}",
            'parents': [DRIVE_FOLDER_ID]
        }
        media = MediaFileUpload(caminho_temp, mimetype=file_storage.mimetype)
        
        # Realiza o Upload com suporte total a drives compartilhados e permissões herdadas
        arquivo_drive = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id',
            supportsAllDrives=True,
            supportsTeamDrives=True
        ).execute()

        file_id = arquivo_drive.get('id')

        # Torna o arquivo público para visualização da miniatura
        try:
            drive_service.permissions().create(
                fileId=file_id,
                body={'type': 'anyone', 'role': 'reader'},
                supportsAllDrives=True,
                supportsTeamDrives=True
            ).execute()
        except Exception:
            pass

        # Retorna link direto de imagem para uso nas tags <img>
        return f"https://lh3.googleusercontent.com/d/{file_id}"

    finally:
        # Remove o arquivo temporário do servidor
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

        # Envia a foto para a pasta do Google Drive
        foto_url = salvar_foto_no_drive(drive_service, file_foto)

        novo_id = len(produtos) + 1
        # Adiciona na planilha [ID, Nome, Categoria, Quantidade, Foto]
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