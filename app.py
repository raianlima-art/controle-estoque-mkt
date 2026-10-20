import sqlite3
from flask import Flask, render_template, request, redirect, url_for, flash

app = Flask(__name__)
app.secret_key = 'chave_secreta_mkt'

def get_db_connection():
    conn = sqlite3.connect('estoque.db')
    conn.row_factory = sqlite3.Row  # Retorna resultados como dicionários
    return conn

# Rota Principal: Listar produtos e formulários
@app.route('/')
def index():
    conn = get_db_connection()
    produtos = conn.execute('SELECT * FROM produtos').fetchall()
    
    # Histórico das últimas 10 movimentações
    movimentacoes = conn.execute('''
        SELECT m.id, p.nome, m.tipo, m.quantidade, m.observacao, m.data_hora
        FROM movimentacoes m
        JOIN produtos p ON m.produto_id = p.id
        ORDER BY m.data_hora DESC LIMIT 10
    ''').fetchall()
    
    conn.close()
    return render_template('index.html', produtos=produtos, movimentacoes=movimentacoes)

# Rota: Cadastrar Novo Produto
@app.route('/cadastrar', methods=['POST'])
def cadastrar():
    nome = request.form['nome']
    categoria = request.form['categoria']
    qtd_inicial = int(request.form.get('quantidade', 0))

    conn = get_db_connection()
    try:
        conn.execute(
            'INSERT INTO produtos (nome, categoria, quantidade) VALUES (?, ?, ?)',
            (nome, categoria, qtd_inicial)
        )
        conn.commit()
        flash('Produto cadastrado com sucesso!', 'success')
    except sqlite3.IntegrityError:
        flash('Erro: Um produto com esse nome já existe!', 'danger')
    finally:
        conn.close()

    return redirect(url_for('index'))

# Rota: Movimentar Estoque (Entrada / Saída)
@app.route('/movimentar', methods=['POST'])
def movimentar():
    produto_id = int(request.form['produto_id'])
    tipo = request.form['tipo']
    qtd = int(request.form['quantidade'])
    obs = request.form['observacao']

    conn = get_db_connection()
    produto = conn.execute('SELECT * FROM produtos WHERE id = ?', (produto_id,)).fetchone()

    if not produto:
        flash('Produto não encontrado!', 'danger')
        conn.close()
        return redirect(url_for('index'))

    qtd_atual = produto['quantidade']

    # Validação de Estoque Negativo
    if tipo == 'Saida' and qtd > qtd_atual:
        flash(f'Erro: Estoque insuficiente! Saldo atual: {qtd_atual}', 'warning')
        conn.close()
        return redirect(url_for('index'))

    nova_qtd = (qtd_atual + qtd) if tipo == 'Entrada' else (qtd_atual - qtd)

    # Atualiza saldo do produto
    conn.execute('UPDATE produtos SET quantidade = ? WHERE id = ?', (nova_qtd, produto_id))
    
    # Registra no histórico
    conn.execute(
        'INSERT INTO movimentacoes (produto_id, tipo, quantidade, observacao) VALUES (?, ?, ?, ?)',
        (produto_id, tipo, qtd, obs)
    )

    conn.commit()
    conn.close()
    flash(f'Movimentação de {tipo} registrada com sucesso!', 'success')
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)