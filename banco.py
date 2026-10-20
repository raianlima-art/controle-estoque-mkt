import sqlite3

def init_db():
    conn = sqlite3.connect('estoque.db')
    cursor = conn.cursor()

    # Tabela de Produtos
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS produtos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL UNIQUE,
            categoria TEXT NOT NULL,
            quantidade INTEGER NOT NULL DEFAULT 0
        )
    ''')

    # Tabela de Movimentações (Histórico)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS movimentacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            produto_id INTEGER NOT NULL,
            tipo TEXT CHECK(tipo IN ('Entrada', 'Saida')) NOT NULL,
            quantidade INTEGER NOT NULL,
            observacao TEXT,
            data_hora DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (produto_id) REFERENCES produtos (id)
        )
    ''')

    conn.commit()
    conn.close()
    print("Banco de dados 'estoque.db' inicializado com sucesso!")

if __name__ == '__main__':
    init_db()