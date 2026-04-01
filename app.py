import csv
import datetime
import json
import os
import shutil
import sqlite3
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure


# ─── Caminhos ────────────────────────────────────────────────────────────────

def obter_diretorio_base():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


BASE_DIR   = obter_diretorio_base()
DB_FILE    = os.path.join(BASE_DIR, "controle_financeiro_ultra.db")
BACKUP_DIR = os.path.join(BASE_DIR, "backups")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

# ─── Constantes ──────────────────────────────────────────────────────────────

MOEDAS = {
    "BRL": {"simbolo": "R$", "nome": "Real"},
    "USD": {"simbolo": "$",  "nome": "Dólar"},
    "EUR": {"simbolo": "€",  "nome": "Euro"},
    "GBP": {"simbolo": "£",  "nome": "Libra"},
    "JPY": {"simbolo": "¥",  "nome": "Iene"},
}

CATEGORIAS_PADRAO = [
    "Aluguel", "Salário", "Cliente", "Fornecedor", "Transporte",
    "Alimentação", "Serviço", "Investimento", "Saúde", "Educação",
    "Lazer", "Outros",
]

MESES_NOME = {
    1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr",
    5: "Mai", 6: "Jun", 7: "Jul", 8: "Ago",
    9: "Set", 10: "Out", 11: "Nov", 12: "Dez",
}

CONFIG_PADRAO = {
    "tema": "dark",
    "moeda_padrao": "BRL",
    "max_backups": 15,
    "busca_tempo_real": True,
}

# ─── Configuração persistente ───────────────────────────────────────────────

def carregar_config() -> dict:
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            dados = json.load(f)
        # Mescla com padrão para garantir chaves novas
        return {**CONFIG_PADRAO, **dados}
    except Exception:
        return dict(CONFIG_PADRAO)


def salvar_config(config: dict):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ─── Utilitários ─────────────────────────────────────────────────────────────

def parse_data_br(data_str: str) -> datetime.date:
    return datetime.datetime.strptime(data_str.strip(), "%d/%m/%Y").date()


def formatar_data_br(data: datetime.date) -> str:
    return data.strftime("%d/%m/%Y")


def formatar_data_hora_br(dt: datetime.datetime) -> str:
    return dt.strftime("%d/%m/%Y %H:%M:%S")


def normalizar_valor(valor_str: str) -> float:
    """Converte string digitada em float. Suporta BR (1.234,56) e US (1,234.56)."""
    valor_str = valor_str.strip().replace(" ", "")
    if not valor_str:
        raise ValueError("Valor vazio")
    for simbolo in ["R$", "$", "€", "£", "¥"]:
        valor_str = valor_str.replace(simbolo, "").strip()
    tem_v = "," in valor_str
    tem_p = "." in valor_str
    if tem_v and tem_p:
        if valor_str.rfind(",") > valor_str.rfind("."):
            valor_str = valor_str.replace(".", "").replace(",", ".")
        else:
            valor_str = valor_str.replace(",", "")
    elif tem_v:
        partes = valor_str.split(",")
        if len(partes) == 2 and len(partes[1]) <= 2:
            valor_str = valor_str.replace(",", ".")
        else:
            valor_str = valor_str.replace(",", "")
    elif tem_p:
        partes = valor_str.split(".")
        if not (len(partes) == 2 and len(partes[1]) <= 2):
            valor_str = valor_str.replace(".", "")
    valor = float(valor_str)
    if valor <= 0:
        raise ValueError("Valor deve ser positivo")
    return round(valor, 2)


def formatar_valor(valor: float, moeda: str) -> str:
    simbolo = MOEDAS.get(moeda, {}).get("simbolo", moeda)
    s = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{simbolo} {s}"


def somente_data(conteudo: str) -> str:
    return "".join(ch for ch in conteudo if ch.isdigit() or ch == "/")[:10]


def somente_valor(conteudo: str) -> str:
    """Só dígitos + UMA vírgula decimal (padrão BR). Máx 2 casas decimais."""
    limpo = "".join(ch for ch in conteudo if ch.isdigit() or ch == ",")
    partes = limpo.split(",", 1)
    if len(partes) == 1:
        return partes[0][:15]
    return f"{partes[0][:15]},{partes[1][:2]}"


# ─── Backup ──────────────────────────────────────────────────────────────────

def garantir_pasta_backup():
    os.makedirs(BACKUP_DIR, exist_ok=True)


def realizar_backup_automatico(db_file: str, max_backups: int = 15):
    if not os.path.exists(db_file):
        return
    garantir_pasta_backup()
    agora = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    destino = os.path.join(BACKUP_DIR, f"controle_financeiro_backup_{agora}.db")
    try:
        shutil.copy2(db_file, destino)
    except OSError:
        return
    backups = sorted(
        [os.path.join(BACKUP_DIR, a) for a in os.listdir(BACKUP_DIR) if a.endswith(".db")],
        key=os.path.getmtime, reverse=True,
    )
    for old in backups[max_backups:]:
        try:
            os.remove(old)
        except OSError:
            pass


# ─── Temas ───────────────────────────────────────────────────────────────────

TEMAS = {
    "dark": {
        "bg": "#0D1117", "surface": "#161B22", "surface2": "#1C2433",
        "surface3": "#243147", "fg": "#E6EDF3", "muted": "#8B949E",
        "primary": "#7C3AED", "primary_hover": "#6D28D9",
        "danger": "#F85149", "danger_hover": "#DA3633",
        "success": "#3FB950", "warning": "#D29922", "info": "#58A6FF",
        "entry_bg": "#21262D", "entry_fg": "#E6EDF3",
        "heading": "#161B22", "tooltip_bg": "#2D333B", "tooltip_fg": "#E6EDF3",
        "text_bg": "#21262D", "text_fg": "#E6EDF3",
        "summary_row": "#1F2D3D", "border": "#30363D",
        "nav": "#0D1117", "nav_active": "#7C3AED", "nav_hover": "#1C2433",
        "pag_color": "#F85149", "rec_color": "#3FB950",
        "saldo_pos": "#3FB950", "saldo_neg": "#F85149",
    },
    "light": {
        "bg": "#F6F8FA", "surface": "#FFFFFF", "surface2": "#EFF2F5",
        "surface3": "#E2E8F0", "fg": "#1F2937", "muted": "#6B7280",
        "primary": "#7C3AED", "primary_hover": "#6D28D9",
        "danger": "#DC2626", "danger_hover": "#B91C1C",
        "success": "#16A34A", "warning": "#D97706", "info": "#2563EB",
        "entry_bg": "#FFFFFF", "entry_fg": "#1F2937",
        "heading": "#F3F4F6", "tooltip_bg": "#1F2937", "tooltip_fg": "#F9FAFB",
        "text_bg": "#FFFFFF", "text_fg": "#1F2937",
        "summary_row": "#EDE9FE", "border": "#E5E7EB",
        "nav": "#FFFFFF", "nav_active": "#7C3AED", "nav_hover": "#F3F4F6",
        "pag_color": "#DC2626", "rec_color": "#16A34A",
        "saldo_pos": "#16A34A", "saldo_neg": "#DC2626",
    },
}


# ─── Banco de Dados ───────────────────────────────────────────────────────────

class FinanceiroDB:
    def __init__(self, db_file: str):
        self.db_file = db_file
        self._init_db()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS registros (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    tipo             TEXT NOT NULL,
                    nome             TEXT NOT NULL,
                    data             TEXT NOT NULL,
                    valor            REAL NOT NULL,
                    moeda            TEXT NOT NULL,
                    categoria        TEXT NOT NULL,
                    observacao       TEXT DEFAULT '',
                    data_hora_adicao TEXT NOT NULL,
                    data_hora_edicao TEXT DEFAULT ''
                )
            """)
            # Migrações seguras
            for col, typedef in [
                ("observacao",       "TEXT DEFAULT ''"),
                ("data_hora_edicao", "TEXT DEFAULT ''"),
            ]:
                try:
                    cur.execute(f"ALTER TABLE registros ADD COLUMN {col} {typedef}")
                except sqlite3.OperationalError:
                    pass
            # Tabela de categorias customizadas
            cur.execute("""
                CREATE TABLE IF NOT EXISTS categorias_custom (
                    nome TEXT PRIMARY KEY
                )
            """)
            conn.commit()

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def inserir_registro(self, tipo, nome, data, valor, moeda, categoria, observacao):
        agora = datetime.datetime.now().isoformat()
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO registros
                    (tipo, nome, data, valor, moeda, categoria, observacao, data_hora_adicao)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (tipo, nome.strip(), data.isoformat(), valor,
                  moeda, categoria, observacao.strip(), agora))
            conn.commit()
            return cur.lastrowid

    def atualizar_registro(self, reg_id, tipo, nome, data, valor, moeda, categoria, observacao):
        agora = datetime.datetime.now().isoformat()
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE registros
                SET tipo=?, nome=?, data=?, valor=?, moeda=?, categoria=?,
                    observacao=?, data_hora_edicao=?
                WHERE id=?
            """, (tipo, nome.strip(), data.isoformat(), valor, moeda,
                  categoria, observacao.strip(), agora, reg_id))
            conn.commit()
            return cur.rowcount > 0

    def excluir_registro(self, reg_id):
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM registros WHERE id = ?", (reg_id,))
            conn.commit()
            return cur.rowcount > 0

    def obter_por_id(self, reg_id):
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM registros WHERE id = ?", (reg_id,))
            row = cur.fetchone()
            return self._row_para_dict(row) if row else None

    def listar_todos(self):
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM registros ORDER BY data DESC, data_hora_adicao DESC, id DESC")
            return [self._row_para_dict(r) for r in cur.fetchall()]

    # ── Busca SQL parametrizada ───────────────────────────────────────────────

    def buscar(self, texto="", tipo="Todos", moeda="Todas", categoria="Todas",
               mes=None, ano=None, data_inicial=None, data_final=None,
               valor_min=None, valor_max=None):
        """Filtragem feita diretamente no SQL."""
        conds, params = [], []
        if tipo != "Todos":
            conds.append("tipo = ?"); params.append(tipo)
        if moeda != "Todas":
            conds.append("moeda = ?"); params.append(moeda)
        if categoria != "Todas":
            conds.append("categoria = ?"); params.append(categoria)
        if mes is not None:
            conds.append("CAST(strftime('%m', data) AS INTEGER) = ?"); params.append(mes)
        if ano is not None:
            conds.append("CAST(strftime('%Y', data) AS INTEGER) = ?"); params.append(ano)
        if data_inicial is not None:
            conds.append("data >= ?"); params.append(data_inicial.isoformat())
        if data_final is not None:
            conds.append("data <= ?"); params.append(data_final.isoformat())
        if valor_min is not None:
            conds.append("valor >= ?"); params.append(valor_min)
        if valor_max is not None:
            conds.append("valor <= ?"); params.append(valor_max)

        where = ("WHERE " + " AND ".join(conds)) if conds else ""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute(f"""
                SELECT * FROM registros {where}
                ORDER BY data DESC, data_hora_adicao DESC, id DESC
            """, params)
            regs = [self._row_para_dict(r) for r in cur.fetchall()]

        # Texto livre em Python (múltiplos campos + formatação)
        if texto:
            t = texto.lower().strip()
            regs = [r for r in regs if any(t in c for c in [
                str(r["id"]), r["tipo"].lower(), r["nome"].lower(),
                r["moeda"].lower(), r["categoria"].lower(),
                r.get("observacao", "").lower(),
                formatar_data_br(r["data"]),
                str(r["valor"]),
                formatar_valor(r["valor"], r["moeda"]).lower(),
            ])]
        return regs

    # ── Utilitários de DB ─────────────────────────────────────────────────────

    def anos_existentes(self):
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT DISTINCT CAST(strftime('%Y', data) AS INTEGER)
                FROM registros ORDER BY 1 DESC
            """)
            return [r[0] for r in cur.fetchall()]

    def categorias_existentes(self):
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT DISTINCT categoria FROM registros WHERE categoria != ''")
            do_banco = {r[0] for r in cur.fetchall()}
            cur.execute("SELECT nome FROM categorias_custom")
            custom = {r[0] for r in cur.fetchall()}
        return sorted(do_banco | custom | set(CATEGORIAS_PADRAO))

    def adicionar_categoria(self, nome: str) -> bool:
        nome = nome.strip()
        if not nome:
            return False
        with self._get_conn() as conn:
            try:
                conn.execute("INSERT INTO categorias_custom (nome) VALUES (?)", (nome,))
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def remover_categoria(self, nome: str) -> bool:
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM categorias_custom WHERE nome = ?", (nome,))
            conn.commit()
            return cur.rowcount > 0

    def resumo_periodo(self, tipo, periodo):
        hoje = datetime.date.today()
        mapa = {
            "diario":  (hoje, hoje),
            "semanal": (hoje - datetime.timedelta(days=6), hoje),
            "mensal":  (hoje.replace(day=1), hoje),
            "anual":   (hoje.replace(month=1, day=1), hoje),
        }
        if periodo not in mapa:
            return []
        di, df = mapa[periodo]
        return self.buscar(tipo=tipo, data_inicial=di, data_final=df)

    def exportar_csv(self, caminho: str, registros: list):
        with open(caminho, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["ID","Tipo","Data","Nome","Valor","Moeda",
                        "Categoria","Observação","DataHoraAdicao","DataHoraEdicao"])
            for r in registros:
                edicao = ""
                if r.get("data_hora_edicao"):
                    try:
                        edicao = formatar_data_hora_br(
                            datetime.datetime.fromisoformat(r["data_hora_edicao"]))
                    except Exception:
                        pass
                w.writerow([
                    r["id"], r["tipo"], formatar_data_br(r["data"]),
                    r["nome"], f"{r['valor']:.2f}", r["moeda"],
                    r["categoria"], r.get("observacao", ""),
                    formatar_data_hora_br(r["data_hora_adicao"]), edicao,
                ])

    def importar_csv(self, caminho: str) -> tuple[int, int, list]:
        """Importa CSV exportado pelo app. Retorna (ok, erros, msgs_erro)."""
        ok, erros, msgs = 0, 0, []
        try:
            with open(caminho, "r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f, delimiter=";")
                for i, row in enumerate(reader, start=2):
                    try:
                        tipo      = row.get("Tipo", "").strip()
                        nome      = row.get("Nome", "").strip()
                        data      = parse_data_br(row.get("Data", "").strip())
                        valor     = normalizar_valor(row.get("Valor", "").strip())
                        moeda     = row.get("Moeda", "BRL").strip() or "BRL"
                        categoria = row.get("Categoria", "Outros").strip() or "Outros"
                        observacao = row.get("Observação", "").strip()
                        if tipo not in ("Pagamento", "Recebimento"):
                            raise ValueError(f"Tipo inválido: {tipo!r}")
                        if not nome:
                            raise ValueError("Nome vazio")
                        if moeda not in MOEDAS:
                            moeda = "BRL"
                        self.inserir_registro(tipo, nome, data, valor, moeda, categoria, observacao)
                        ok += 1
                    except Exception as e:
                        erros += 1
                        msgs.append(f"Linha {i}: {e}")
        except Exception as e:
            msgs.append(f"Erro ao abrir arquivo: {e}")
        return ok, erros, msgs

    # ── Dados para gráficos (SQL agregado) ───────────────────────────────────

    def dados_grafico_mensal(self):
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT strftime('%Y-%m', data) AS mes, tipo, SUM(valor)
                FROM registros GROUP BY mes, tipo ORDER BY mes
            """)
            rows = cur.fetchall()
        agregados = {}
        for mes, tipo, soma in rows:
            agregados.setdefault(mes, {"Pagamento": 0.0, "Recebimento": 0.0})
            agregados[mes][tipo] = soma
        meses = sorted(agregados)[-12:]
        labels = []
        for m in meses:
            try:
                d = datetime.datetime.strptime(m, "%Y-%m")
                labels.append(d.strftime("%b/%y"))
            except Exception:
                labels.append(m)
        return labels, [agregados[m]["Pagamento"] for m in meses], \
                       [agregados[m]["Recebimento"] for m in meses]

    def dados_grafico_categoria(self, tipo="Pagamento"):
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT COALESCE(NULLIF(categoria,''),'Outros') AS cat, SUM(valor)
                FROM registros WHERE tipo = ?
                GROUP BY cat ORDER BY SUM(valor) DESC
            """, (tipo,))
            rows = cur.fetchall()
        return [r[0] for r in rows], [r[1] for r in rows]

    def dados_grafico_saldo_acumulado(self):
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT strftime('%Y-%m', data) AS mes,
                       SUM(CASE WHEN tipo='Recebimento' THEN valor ELSE -valor END)
                FROM registros WHERE moeda='BRL'
                GROUP BY mes ORDER BY mes
            """)
            rows = cur.fetchall()
        labels, acumulado, total = [], [], 0.0
        for mes, delta in rows:
            total += (delta or 0.0)
            acumulado.append(total)
            try:
                d = datetime.datetime.strptime(mes, "%Y-%m")
                labels.append(f"{MESES_NOME[d.month]}/{str(d.year)[2:]}")
            except Exception:
                labels.append(mes)
        return labels, acumulado

    def estatisticas_gerais(self):
        """Totais por moeda via SQL agregado — sem carregar registros."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM registros")
            total = cur.fetchone()[0]
            cur.execute("""
                SELECT moeda, tipo, SUM(valor)
                FROM registros GROUP BY moeda, tipo
            """)
            rows = cur.fetchall()
        por_moeda = {}
        for moeda, tipo, soma in rows:
            por_moeda.setdefault(moeda, {"pag": 0.0, "rec": 0.0})
            por_moeda[moeda]["pag" if tipo == "Pagamento" else "rec"] += soma
        return total, por_moeda

    def _row_para_dict(self, row):
        if row is None:
            return None
        keys = row.keys()
        d = {
            "id":               row["id"],
            "tipo":             row["tipo"],
            "nome":             row["nome"],
            "data":             datetime.datetime.strptime(row["data"], "%Y-%m-%d").date(),
            "valor":            float(row["valor"]),
            "moeda":            row["moeda"],
            "categoria":        row["categoria"],
            "observacao":       row["observacao"] or "",
            "data_hora_adicao": datetime.datetime.fromisoformat(row["data_hora_adicao"]),
            "data_hora_edicao": "",
        }
        if "data_hora_edicao" in keys and row["data_hora_edicao"]:
            try:
                d["data_hora_edicao"] = row["data_hora_edicao"]
            except Exception:
                pass
        return d


# ─── Tooltip da tabela ────────────────────────────────────────────────────────

class TreeTooltip:
    def __init__(self, tree, tema):
        self.tree = tree
        self.tema = tema
        self.tip = None
        self.current_item = None
        tree.bind("<Motion>", self._on_motion)
        tree.bind("<Leave>",  self.hide)

    def update_theme(self, tema):
        self.tema = tema

    def _on_motion(self, event):
        item_id = self.tree.identify_row(event.y)
        if not item_id:
            self.hide(); return
        tags = self.tree.item(item_id, "tags")
        dh_tag = next((t[3:] for t in tags if t.startswith("dh:")), None)
        ed_tag = next((t[3:] for t in tags if t.startswith("ed:")), None)
        if not dh_tag:
            self.hide(); return
        if self.current_item == item_id and self.tip:
            return
        self.hide()
        try:
            dh = datetime.datetime.fromisoformat(dh_tag)
        except ValueError:
            return
        self.current_item = item_id
        self.tip = tk.Toplevel(self.tree)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{event.x_root + 15}+{event.y_root + 10}")
        linhas = [f"Criado em:  {formatar_data_hora_br(dh)}"]
        if ed_tag:
            try:
                ed = datetime.datetime.fromisoformat(ed_tag)
                linhas.append(f"Editado em: {formatar_data_hora_br(ed)}")
            except Exception:
                pass
        tk.Label(
            self.tip, text="\n".join(linhas),
            bg=self.tema["tooltip_bg"], fg=self.tema["tooltip_fg"],
            relief="flat", borderwidth=0, font=("Segoe UI", 9),
            justify="left", padx=12, pady=8,
        ).pack()

    def hide(self, event=None):
        self.current_item = None
        if self.tip:
            self.tip.destroy()
            self.tip = None


# ─── Diálogo de edição ────────────────────────────────────────────────────────

class EditarRegistroDialog(tk.Toplevel):
    def __init__(self, master, registro, categorias, tema, callback_salvar):
        super().__init__(master)
        self.title(f"Editar Registro  #{registro['id']}")
        self.geometry("640x540")
        self.resizable(True, True)
        self.minsize(560, 460)
        self.transient(master)
        self.grab_set()
        self.registro  = registro
        self.categorias = categorias
        self.tema      = tema
        self.callback_salvar = callback_salvar
        self.configure(bg=tema["bg"])
        self._build()

    def _entry_style(self):
        return dict(
            bg=self.tema["entry_bg"], fg=self.tema["entry_fg"],
            insertbackground=self.tema["entry_fg"], relief="flat",
            font=("Segoe UI", 10), bd=0, highlightthickness=1,
            highlightbackground=self.tema["border"],
            highlightcolor=self.tema["primary"],
        )

    def _build(self):
        t = self.tema
        s = ttk.Style(self)
        s.configure("DE.TLabel",   background=t["bg"], foreground=t["fg"])
        s.configure("DE.TFrame",   background=t["bg"])
        s.configure("DE.TCombobox", fieldbackground=t["entry_bg"], foreground=t["entry_fg"])
        s.configure("DPri.TButton", background=t["primary"],  foreground="#FFF",
                    padding=(12,9), font=("Segoe UI Semibold",10,"bold"), borderwidth=0)
        s.map("DPri.TButton", background=[("active", t["primary_hover"])])
        s.configure("DSec.TButton", background=t["surface2"], foreground=t["fg"],
                    padding=(12,9), font=("Segoe UI Semibold",10,"bold"), borderwidth=0)
        s.map("DSec.TButton", background=[("active", t["surface3"])])

        f = tk.Frame(self, bg=t["bg"], padx=24, pady=20)
        f.pack(fill="both", expand=True)
        f.columnconfigure(1, weight=1)

        # Cabeçalho colorido por tipo
        hdr = tk.Frame(f, bg=t["surface"], pady=12, padx=16)
        hdr.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0,18))
        hdr.columnconfigure(0, weight=1)
        tk.Label(hdr, text=f"Editar  ·  ID {self.registro['id']}",
                 bg=t["surface"], fg=t["fg"],
                 font=("Segoe UI Semibold",14,"bold")).pack(side="left")
        badge_cor = t["pag_color"] if self.registro["tipo"] == "Pagamento" else t["rec_color"]
        tk.Label(hdr, text=f"  {self.registro['tipo']}  ",
                 bg=badge_cor, fg="#FFF",
                 font=("Segoe UI Semibold",9,"bold"), padx=10, pady=4).pack(side="right")

        def lbl(txt, row):
            tk.Label(f, text=txt, bg=t["bg"], fg=t["muted"],
                     font=("Segoe UI",9,"bold")).grid(
                row=row, column=0, sticky="w", pady=6, padx=(0,14))

        lbl("Tipo", 1)
        self.tipo_combo = ttk.Combobox(f, state="readonly",
                                        values=["Pagamento","Recebimento"])
        self.tipo_combo.grid(row=1, column=1, sticky="ew", pady=6)
        self.tipo_combo.set(self.registro["tipo"])

        lbl("Nome / Empresa", 2)
        self.nome_entry = tk.Entry(f, **self._entry_style())
        self.nome_entry.grid(row=2, column=1, sticky="ew", pady=6, ipady=6)
        self.nome_entry.insert(0, self.registro["nome"])

        lbl("Data (dd/mm/aaaa)", 3)
        self.data_entry = tk.Entry(f, **self._entry_style())
        self.data_entry.grid(row=3, column=1, sticky="ew", pady=6, ipady=6)
        self.data_entry.insert(0, formatar_data_br(self.registro["data"]))
        self.data_entry.bind("<KeyRelease>", lambda e: self._fmt_data())

        lbl("Valor", 4)
        self.valor_entry = tk.Entry(f, **self._entry_style())
        self.valor_entry.grid(row=4, column=1, sticky="ew", pady=6, ipady=6)
        self.valor_entry.insert(0, f"{self.registro['valor']:.2f}".replace(".", ","))
        self.valor_entry.bind("<KeyRelease>", lambda e: self._fmt_valor())

        lbl("Moeda", 5)
        self.moeda_combo = ttk.Combobox(f, state="readonly", values=list(MOEDAS.keys()))
        self.moeda_combo.grid(row=5, column=1, sticky="ew", pady=6)
        self.moeda_combo.set(self.registro["moeda"])

        lbl("Categoria", 6)
        self.cat_combo = ttk.Combobox(f, values=self.categorias)
        self.cat_combo.grid(row=6, column=1, sticky="ew", pady=6)
        self.cat_combo.set(self.registro["categoria"])

        lbl("Observação", 7)
        self.obs_text = tk.Text(
            f, height=4, bg=t["text_bg"], fg=t["text_fg"],
            insertbackground=t["text_fg"], relief="flat", padx=10, pady=8,
            font=("Segoe UI",10), highlightthickness=1,
            highlightbackground=t["border"], highlightcolor=t["primary"],
            undo=True, maxundo=50,
        )
        self.obs_text.grid(row=7, column=1, sticky="ew", pady=6)
        self.obs_text.insert("1.0", self.registro.get("observacao", ""))

        # Auditoria
        criado = formatar_data_hora_br(self.registro["data_hora_adicao"])
        edicao_str = ""
        if self.registro.get("data_hora_edicao"):
            try:
                ed = datetime.datetime.fromisoformat(self.registro["data_hora_edicao"])
                edicao_str = f"   ·   Editado: {formatar_data_hora_br(ed)}"
            except Exception:
                pass
        tk.Label(f, text=f"Criado: {criado}{edicao_str}",
                 bg=t["bg"], fg=t["muted"], font=("Segoe UI",8)).grid(
            row=8, column=0, columnspan=2, sticky="w", pady=(4,0))

        tk.Frame(f, bg=t["border"], height=1).grid(
            row=9, column=0, columnspan=2, sticky="ew", pady=(12,0))

        btns = tk.Frame(f, bg=t["bg"])
        btns.grid(row=10, column=0, columnspan=2, sticky="ew", pady=(12,0))
        btns.columnconfigure(0, weight=1)
        btns.columnconfigure(1, weight=1)
        ttk.Button(btns, text="Salvar Alterações", command=self._salvar,
                   style="DPri.TButton").grid(row=0, column=0, sticky="ew", padx=(0,6))
        ttk.Button(btns, text="Cancelar", command=self.destroy,
                   style="DSec.TButton").grid(row=0, column=1, sticky="ew", padx=(6,0))

    def _fmt_data(self):
        e = self.data_entry
        filtrado = somente_data(e.get())
        if filtrado != e.get():
            pos = e.index(tk.INSERT)
            e.delete(0, tk.END); e.insert(0, filtrado)
            e.icursor(min(pos, len(filtrado)))
        v = e.get()
        if len(v) in (2, 5) and not v.endswith("/"):
            e.insert(tk.END, "/")

    def _fmt_valor(self):
        e = self.valor_entry
        atual = e.get()
        filtrado = somente_valor(atual)
        if filtrado != atual:
            pos = e.index(tk.INSERT)
            chars_ok = len(somente_valor(atual[:pos]))
            e.delete(0, tk.END); e.insert(0, filtrado)
            e.icursor(min(chars_ok, len(filtrado)))

    def _salvar(self):
        try:
            tipo  = self.tipo_combo.get().strip()
            nome  = self.nome_entry.get().strip()
            if len(nome) < 2:
                messagebox.showwarning("Campo inválido",
                                       "Nome deve ter pelo menos 2 caracteres.", parent=self)
                self.nome_entry.focus_set(); return
            data_str = self.data_entry.get().strip()
            if len(data_str) != 10:
                raise ValueError("Data incompleta")
            data      = parse_data_br(data_str)
            valor     = normalizar_valor(self.valor_entry.get().strip())
            moeda     = self.moeda_combo.get().strip()
            categoria = self.cat_combo.get().strip() or "Outros"
            obs       = self.obs_text.get("1.0", "end-1c").strip()
            self.callback_salvar(self.registro["id"], tipo, nome,
                                 data, valor, moeda, categoria, obs)
            self.destroy()
        except ValueError as e:
            messagebox.showerror("Erro de validação", f"Revise os campos:\n{e}", parent=self)
        except Exception:
            messagebox.showerror("Erro", "Revise os campos.", parent=self)


# ─── Diálogo de Configurações ─────────────────────────────────────────────────

class ConfigDialog(tk.Toplevel):
    def __init__(self, master, config: dict, tema: dict, callback):
        super().__init__(master)
        self.title("Configurações")
        self.geometry("460x340")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        self.config_atual = dict(config)
        self.tema = tema
        self.callback = callback
        self.configure(bg=tema["bg"])
        self._build()

    def _build(self):
        t = self.tema
        f = tk.Frame(self, bg=t["bg"], padx=28, pady=24)
        f.pack(fill="both", expand=True)
        f.columnconfigure(1, weight=1)

        tk.Label(f, text="Configurações", bg=t["bg"], fg=t["fg"],
                 font=("Segoe UI Semibold",14,"bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0,20))

        def lbl(txt, row):
            tk.Label(f, text=txt, bg=t["bg"], fg=t["muted"],
                     font=("Segoe UI",9,"bold")).grid(
                row=row, column=0, sticky="w", pady=8, padx=(0,16))

        # Tema
        lbl("Tema padrão", 1)
        self.tema_combo = ttk.Combobox(f, state="readonly",
                                        values=["dark","light"])
        self.tema_combo.grid(row=1, column=1, sticky="ew", pady=8)
        self.tema_combo.set(self.config_atual.get("tema","dark"))

        # Moeda padrão
        lbl("Moeda padrão", 2)
        self.moeda_combo = ttk.Combobox(f, state="readonly",
                                         values=list(MOEDAS.keys()))
        self.moeda_combo.grid(row=2, column=1, sticky="ew", pady=8)
        self.moeda_combo.set(self.config_atual.get("moeda_padrao","BRL"))

        # Max backups
        lbl("Máx. backups", 3)
        self.backups_spin = tk.Spinbox(f, from_=3, to=50, width=6,
                                        bg=t["entry_bg"], fg=t["entry_fg"],
                                        relief="flat", font=("Segoe UI",10))
        self.backups_spin.grid(row=3, column=1, sticky="w", pady=8)
        self.backups_spin.delete(0, tk.END)
        self.backups_spin.insert(0, str(self.config_atual.get("max_backups", 15)))

        # Busca em tempo real
        lbl("Busca em tempo real", 4)
        self.btr_var = tk.BooleanVar(value=self.config_atual.get("busca_tempo_real", True))
        tk.Checkbutton(f, variable=self.btr_var, bg=t["bg"],
                       activebackground=t["bg"]).grid(row=4, column=1, sticky="w", pady=8)

        tk.Frame(f, bg=t["border"], height=1).grid(
            row=5, column=0, columnspan=2, sticky="ew", pady=(14,0))

        btns = tk.Frame(f, bg=t["bg"])
        btns.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(14,0))
        btns.columnconfigure(0, weight=1); btns.columnconfigure(1, weight=1)

        s = ttk.Style(self)
        s.configure("CFPri.TButton", background=t["primary"], foreground="#FFF",
                    padding=(12,9), font=("Segoe UI Semibold",10,"bold"), borderwidth=0)
        s.map("CFPri.TButton", background=[("active", t["primary_hover"])])
        s.configure("CFSec.TButton", background=t["surface2"], foreground=t["fg"],
                    padding=(12,9), font=("Segoe UI Semibold",10,"bold"), borderwidth=0)
        s.map("CFSec.TButton", background=[("active", t["surface3"])])

        ttk.Button(btns, text="Salvar", command=self._salvar,
                   style="CFPri.TButton").grid(row=0, column=0, sticky="ew", padx=(0,6))
        ttk.Button(btns, text="Cancelar", command=self.destroy,
                   style="CFSec.TButton").grid(row=0, column=1, sticky="ew", padx=(6,0))

    def _salvar(self):
        try:
            mb = int(self.backups_spin.get())
            if not 1 <= mb <= 100:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Valor inválido",
                                   "Máx. backups deve ser entre 1 e 100.", parent=self)
            return
        self.config_atual["tema"] = self.tema_combo.get()
        self.config_atual["moeda_padrao"] = self.moeda_combo.get()
        self.config_atual["max_backups"] = mb
        self.config_atual["busca_tempo_real"] = self.btr_var.get()
        self.callback(self.config_atual)
        self.destroy()


# ─── Diálogo de Gerenciamento de Categorias ──────────────────────────────────

class CategoriasDialog(tk.Toplevel):
    def __init__(self, master, db: "FinanceiroDB", tema: dict, callback):
        super().__init__(master)
        self.title("Gerenciar Categorias")
        self.geometry("420x480")
        self.resizable(True, True)
        self.minsize(360, 380)
        self.transient(master)
        self.grab_set()
        self.db = db
        self.tema = tema
        self.callback = callback
        self.configure(bg=tema["bg"])
        self._build()

    def _build(self):
        t = self.tema
        f = tk.Frame(self, bg=t["bg"], padx=22, pady=20)
        f.pack(fill="both", expand=True)
        f.columnconfigure(0, weight=1)
        f.rowconfigure(2, weight=1)

        tk.Label(f, text="Gerenciar Categorias", bg=t["bg"], fg=t["fg"],
                 font=("Segoe UI Semibold",13,"bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0,16))

        # Campo nova categoria
        add_frame = tk.Frame(f, bg=t["bg"])
        add_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0,10))
        add_frame.columnconfigure(0, weight=1)

        self.nova_entry = tk.Entry(
            add_frame, bg=t["entry_bg"], fg=t["entry_fg"],
            insertbackground=t["entry_fg"], relief="flat",
            font=("Segoe UI",10), bd=0, highlightthickness=1,
            highlightbackground=t["border"], highlightcolor=t["primary"],
        )
        self.nova_entry.grid(row=0, column=0, sticky="ew", ipady=6, padx=(0,8))
        self.nova_entry.bind("<Return>", lambda e: self._adicionar())

        s = ttk.Style(self)
        s.configure("CAPri.TButton", background=t["primary"], foreground="#FFF",
                    padding=(10,8), font=("Segoe UI Semibold",10,"bold"), borderwidth=0)
        s.map("CAPri.TButton", background=[("active", t["primary_hover"])])
        s.configure("CADan.TButton", background=t["danger"], foreground="#FFF",
                    padding=(10,8), font=("Segoe UI Semibold",10,"bold"), borderwidth=0)
        s.map("CADan.TButton", background=[("active", t["danger_hover"])])

        ttk.Button(add_frame, text="Adicionar", command=self._adicionar,
                   style="CAPri.TButton").grid(row=0, column=1)

        # Lista de categorias
        list_frame = tk.Frame(f, bg=t["surface"])
        list_frame.grid(row=2, column=0, columnspan=2, sticky="nsew")
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        self.listbox = tk.Listbox(
            list_frame, bg=t["surface"], fg=t["fg"],
            selectbackground=t["primary"], selectforeground="#FFF",
            relief="flat", bd=0, font=("Segoe UI",10),
            activestyle="none", highlightthickness=0,
        )
        self.listbox.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.listbox.configure(yscrollcommand=sb.set)

        ttk.Button(f, text="Remover selecionada", command=self._remover,
                   style="CADan.TButton").grid(
            row=3, column=0, columnspan=2, sticky="ew", pady=(10,0))

        tk.Label(f, text="Categorias padrão não podem ser removidas.",
                 bg=t["bg"], fg=t["muted"], font=("Segoe UI",8)).grid(
            row=4, column=0, columnspan=2, sticky="w", pady=(6,0))

        self._atualizar_lista()

    def _atualizar_lista(self):
        self.listbox.delete(0, tk.END)
        for cat in self.db.categorias_existentes():
            self.listbox.insert(tk.END, cat)

    def _adicionar(self):
        nome = self.nova_entry.get().strip()
        if not nome:
            return
        if self.db.adicionar_categoria(nome):
            self.nova_entry.delete(0, tk.END)
            self._atualizar_lista()
            self.callback()
        else:
            messagebox.showwarning("Aviso", f"Categoria '{nome}' já existe.", parent=self)

    def _remover(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        cat = self.listbox.get(sel[0])
        if cat in CATEGORIAS_PADRAO:
            messagebox.showwarning("Não permitido",
                                   f"'{cat}' é uma categoria padrão e não pode ser removida.",
                                   parent=self)
            return
        if messagebox.askyesno("Confirmar", f"Remover categoria '{cat}'?", parent=self):
            self.db.remover_categoria(cat)
            self._atualizar_lista()
            self.callback()


# ─── Aplicação Principal ──────────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.config_app = carregar_config()
        self.db = FinanceiroDB(DB_FILE)
        realizar_backup_automatico(DB_FILE, self.config_app.get("max_backups", 15))

        self.tema_atual_nome = self.config_app.get("tema", "dark")
        self.tema = TEMAS[self.tema_atual_nome]

        self.resultados_atuais: list = []
        self.ordem_coluna: dict = {}
        self.cards_busca: list = []
        self.cards_graficos: list = []
        self.periodo_rapido = None
        self._debounce_id = None

        self.title("JH — Controle Financeiro")
        self.geometry("1400x880")
        self.minsize(1100, 700)

        self._configurar_estilo()
        self._criar_widgets()
        self._carregar_resumos()
        self.ver_todos()

        # Atalhos globais
        self.bind("<Control-f>", lambda e: (self.mostrar_tela("busca"),
                                             self.filtro_texto_entry.focus_set()))
        self.bind("<Control-s>", lambda e: self.salvar_registro()
                  if self.tela_atual == "registrar" else None)
        self.bind("<Control-n>", lambda e: self.mostrar_tela("registrar"))
        self.bind("<F5>", lambda e: self.pesquisar()
                  if self.tela_atual == "busca" else self.ver_todos())
        self.protocol("WM_DELETE_WINDOW", self._ao_fechar)

    # ── Estilos ───────────────────────────────────────────────────────────────

    def _configurar_estilo(self):
        t = self.tema
        self.configure(bg=t["bg"])
        s = self.style = ttk.Style(self)
        s.theme_use("clam")

        s.configure(".", font=("Segoe UI", 10), background=t["bg"])
        s.configure("TFrame",        background=t["bg"])
        s.configure("Card.TFrame",   background=t["surface"])
        s.configure("Sidebar.TFrame",background=t["nav"])

        for name, bg, fg in [
            ("TLabel",      t["bg"],     t["fg"]),
            ("Card.TLabel", t["surface"],t["fg"]),
            ("Sidebar.TLabel",t["nav"],  t["fg"]),
            ("Muted.TLabel",t["bg"],     t["muted"]),
        ]:
            s.configure(name, background=bg, foreground=fg)

        s.configure("Title.TLabel",      background=t["bg"],      foreground=t["fg"],
                    font=("Segoe UI Black",22,"bold"))
        s.configure("Section.TLabel",    background=t["bg"],      foreground=t["fg"],
                    font=("Segoe UI Semibold",15,"bold"))
        s.configure("CardTitle.TLabel",  background=t["surface"], foreground=t["muted"],
                    font=("Segoe UI",9,"bold"))
        s.configure("CardValue.TLabel",  background=t["surface"], foreground=t["fg"],
                    font=("Segoe UI Semibold",18,"bold"))
        s.configure("CardValuePag.TLabel", background=t["surface"],foreground=t["pag_color"],
                    font=("Segoe UI Semibold",16,"bold"))
        s.configure("CardValueRec.TLabel", background=t["surface"],foreground=t["rec_color"],
                    font=("Segoe UI Semibold",16,"bold"))
        s.configure("CardValueSaldo.TLabel",background=t["surface"],foreground=t["fg"],
                    font=("Segoe UI Semibold",16,"bold"))

        def btn(name, bg, fg, hover, **kw):
            s.configure(f"{name}.TButton", background=bg, foreground=fg,
                        padding=(13,9), font=("Segoe UI Semibold",10,"bold"),
                        borderwidth=0, **kw)
            s.map(f"{name}.TButton",
                  background=[("active",hover),("pressed",hover)],
                  foreground=[("active",fg)])
        btn("Primary",   t["primary"],  "#FFF", t["primary_hover"])
        btn("Danger",    t["danger"],   "#FFF", t["danger_hover"])
        btn("Secondary", t["surface2"], t["fg"],t["surface3"])

        s.configure("Nav.TButton", background=t["nav"], foreground=t["muted"],
                    padding=(18,12), font=("Segoe UI Semibold",10),
                    borderwidth=0, anchor="w")
        s.map("Nav.TButton",
              background=[("active",t["nav_hover"]),("pressed",t["nav_hover"])],
              foreground=[("active",t["fg"])])
        s.configure("NavActive.TButton", background=t["nav_active"], foreground="#FFF",
                    padding=(18,12), font=("Segoe UI Semibold",10,"bold"),
                    borderwidth=0, anchor="w")
        s.map("NavActive.TButton",
              background=[("active",t["nav_active"])],
              foreground=[("active","#FFF")])
        s.configure("TButton", background=t["surface2"], foreground=t["fg"],
                    padding=(12,8), font=("Segoe UI",10), borderwidth=0)
        s.map("TButton",
              background=[("active",t["primary"])],
              foreground=[("active","#FFF")])

        s.configure("TEntry",    fieldbackground=t["entry_bg"], foreground=t["entry_fg"],
                    padding=8, relief="flat", borderwidth=0)
        s.configure("TCombobox", fieldbackground=t["entry_bg"], foreground=t["entry_fg"],
                    selectbackground=t["primary"], padding=7, relief="flat")
        s.map("TCombobox",
              fieldbackground=[("readonly",t["entry_bg"])],
              foreground=[("readonly",t["entry_fg"])])

        s.configure("Treeview",
                    background=t["surface"], foreground=t["fg"],
                    fieldbackground=t["surface"], rowheight=36,
                    font=("Segoe UI",10), borderwidth=0)
        s.configure("Treeview.Heading",
                    background=t["heading"], foreground=t["muted"],
                    font=("Segoe UI Semibold",9,"bold"), relief="flat", padding=(10,8))
        s.map("Treeview",
              background=[("selected",t["primary"])],
              foreground=[("selected","#FFF")])
        s.map("Treeview.Heading", background=[("active",t["surface2"])])
        s.configure("TScrollbar", background=t["surface2"], troughcolor=t["bg"],
                    borderwidth=0, arrowsize=13)

        self.option_add("*TCombobox*Listbox.font",            ("Segoe UI",10))
        self.option_add("*TCombobox*Listbox.background",      t["entry_bg"])
        self.option_add("*TCombobox*Listbox.foreground",      t["entry_fg"])
        self.option_add("*TCombobox*Listbox.selectBackground",t["primary"])

    def alternar_tema(self):
        self.tema_atual_nome = "light" if self.tema_atual_nome == "dark" else "dark"
        self.tema = TEMAS[self.tema_atual_nome]
        self.config_app["tema"] = self.tema_atual_nome
        salvar_config(self.config_app)
        self._reaplicar_tema()

    def _reaplicar_tema(self):
        self._configurar_estilo()
        self.configure(bg=self.tema["bg"])
        if hasattr(self, "cad_obs_text"):
            self.cad_obs_text.configure(bg=self.tema["text_bg"],
                                         fg=self.tema["text_fg"],
                                         insertbackground=self.tema["text_fg"])
        if hasattr(self, "sidebar"):
            self.sidebar.configure(style="Sidebar.TFrame")
        if hasattr(self, "tooltip"):
            self.tooltip.update_theme(self.tema)
        if hasattr(self, "tree"):
            for tag, bg, fg, fnt in [
                ("total",    self.tema["summary_row"], self.tema["fg"],      ("Segoe UI Semibold",10,"bold")),
                ("saldo_pos",self.tema["summary_row"], self.tema["saldo_pos"],("Segoe UI Semibold",10,"bold")),
                ("saldo_neg",self.tema["summary_row"], self.tema["saldo_neg"],("Segoe UI Semibold",10,"bold")),
            ]:
                self.tree.tag_configure(tag, background=bg, foreground=fg, font=fnt)
            self.tree.tag_configure("pagamento",   foreground=self.tema["pag_color"])
            self.tree.tag_configure("recebimento", foreground=self.tema["rec_color"])
        if hasattr(self, "btn_tema"):
            icon = "☀️" if self.tema_atual_nome == "dark" else "🌙"
            self.btn_tema.configure(text=f"{icon}  Alternar Tema")
        self._carregar_resumos()
        self.pesquisar()
        if hasattr(self, "nav_buttons") and hasattr(self, "tela_atual"):
            self.mostrar_tela(self.tela_atual)

    # ── Widgets principais ────────────────────────────────────────────────────

    def _criar_widgets(self):
        self.tela_atual = "registrar"
        shell = ttk.Frame(self)
        shell.pack(fill="both", expand=True)
        shell.columnconfigure(1, weight=1)
        shell.rowconfigure(0, weight=1)

        # Sidebar
        self.sidebar = ttk.Frame(shell, style="Sidebar.TFrame", width=220, padding=(14,20))
        self.sidebar.grid(row=0, column=0, sticky="ns")
        self.sidebar.grid_propagate(False)
        self.sidebar.columnconfigure(0, weight=1)

        logo = ttk.Frame(self.sidebar, style="Sidebar.TFrame")
        logo.grid(row=0, column=0, sticky="ew", pady=(0,28))
        tk.Label(logo, text="JH", bg=self.tema["nav"], fg=self.tema["primary"],
                 font=("Segoe UI Black",28,"bold"), anchor="w").pack(anchor="w")
        tk.Label(logo, text="Controle Financeiro", bg=self.tema["nav"],
                 fg=self.tema["muted"], font=("Segoe UI",10), anchor="w").pack(anchor="w")

        tk.Frame(self.sidebar, bg=self.tema["border"], height=1).grid(
            row=1, column=0, sticky="ew", pady=(0,16))

        self.nav_buttons = {}
        for idx, (key, label) in enumerate([
            ("registrar","✚  Registrar"),
            ("busca",    "⊞  Registros"),
            ("graficos", "⬛  Gráficos"),
        ], start=2):
            btn = ttk.Button(self.sidebar, text=label,
                             command=lambda k=key: self.mostrar_tela(k),
                             style="Nav.TButton")
            btn.grid(row=idx, column=0, sticky="ew", pady=3)
            self.nav_buttons[key] = btn

        ttk.Frame(self.sidebar, style="Sidebar.TFrame").grid(row=5, column=0, sticky="ew")
        self.sidebar.rowconfigure(5, weight=1)

        tk.Frame(self.sidebar, bg=self.tema["border"], height=1).grid(
            row=6, column=0, sticky="ew", pady=(0,10))

        icon = "☀️" if self.tema_atual_nome == "dark" else "🌙"
        self.btn_tema = ttk.Button(self.sidebar, text=f"{icon}  Alternar Tema",
                                    command=self.alternar_tema, style="Secondary.TButton")
        self.btn_tema.grid(row=7, column=0, sticky="ew", pady=(0,4))

        ttk.Button(self.sidebar, text="⚙  Configurações",
                   command=self._abrir_configuracoes,
                   style="Secondary.TButton").grid(row=8, column=0, sticky="ew", pady=(0,4))

        ttk.Button(self.sidebar, text="≡  Categorias",
                   command=self._abrir_categorias,
                   style="Secondary.TButton").grid(row=9, column=0, sticky="ew")

        tk.Label(self.sidebar, text="v9.0", bg=self.tema["nav"],
                 fg=self.tema["muted"], font=("Segoe UI",8)).grid(
            row=10, column=0, sticky="e", pady=(10,0))

        # Área principal
        main = ttk.Frame(shell, padding=(24,18,24,18))
        main.grid(row=0, column=1, sticky="nsew")
        main.columnconfigure(0, weight=1)
        main.rowconfigure(1, weight=1)

        hdr = ttk.Frame(main)
        hdr.grid(row=0, column=0, sticky="ew", pady=(0,16))
        hdr.columnconfigure(0, weight=1)
        ttk.Label(hdr, text="JH — Controle Financeiro",
                  style="Title.TLabel").grid(row=0, column=0, sticky="w")
        self.header_subtitle = ttk.Label(hdr, text="", style="Muted.TLabel",
                                          font=("Segoe UI",10))
        self.header_subtitle.grid(row=1, column=0, sticky="w", pady=(3,0))
        self.lbl_data_atual = tk.Label(hdr, text="", bg=self.tema["bg"],
                                        fg=self.tema["muted"], font=("Segoe UI",9))
        self.lbl_data_atual.grid(row=0, column=1, sticky="e", rowspan=2)
        self._atualizar_relogio()

        host = ttk.Frame(main)
        host.grid(row=1, column=0, sticky="nsew")
        host.columnconfigure(0, weight=1)
        host.rowconfigure(0, weight=1)

        self.aba_registrar = ttk.Frame(host, padding=2)
        self.aba_busca     = ttk.Frame(host, padding=2)
        self.aba_graficos  = ttk.Frame(host, padding=2)
        for f in (self.aba_registrar, self.aba_busca, self.aba_graficos):
            f.grid(row=0, column=0, sticky="nsew")

        self._criar_aba_registrar()
        self._criar_aba_busca()
        self._criar_aba_graficos()
        self.mostrar_tela("registrar")

    def _atualizar_relogio(self):
        self.lbl_data_atual.configure(
            text=datetime.datetime.now().strftime("📅  %d/%m/%Y   🕐  %H:%M:%S"),
            bg=self.tema["bg"], fg=self.tema["muted"])
        self.after(1000, self._atualizar_relogio)

    def mostrar_tela(self, nome):
        self.tela_atual = nome
        subtitulos = {
            "registrar": "Cadastre pagamentos e recebimentos com rapidez.",
            "busca":     "Pesquise, edite e apague registros.",
            "graficos":  "Acompanhe tendências e distribuições.",
        }
        titulos = {
            "registrar": "JH — Controle Financeiro · Registrar",
            "busca":     "JH — Controle Financeiro · Registros",
            "graficos":  "JH — Controle Financeiro · Gráficos",
        }
        telas = {"registrar": self.aba_registrar,
                 "busca": self.aba_busca,
                 "graficos": self.aba_graficos}
        for key, frame in telas.items():
            if key == nome:
                frame.tkraise()
                self.nav_buttons[key].configure(style="NavActive.TButton")
            else:
                self.nav_buttons[key].configure(style="Nav.TButton")
        self.header_subtitle.configure(text=subtitulos.get(nome, ""))
        self.title(titulos.get(nome, "JH — Controle Financeiro"))
        if nome == "graficos":
            self.after(80, self._atualizar_todos_graficos)

    # ── Diálogos externos ─────────────────────────────────────────────────────

    def _abrir_configuracoes(self):
        def cb(nova_config):
            self.config_app = nova_config
            salvar_config(nova_config)
            novo_tema = nova_config.get("tema", self.tema_atual_nome)
            if novo_tema != self.tema_atual_nome:
                self.tema_atual_nome = novo_tema
                self.tema = TEMAS[novo_tema]
                self._reaplicar_tema()
        ConfigDialog(self, self.config_app, self.tema, cb)

    def _abrir_categorias(self):
        def cb():
            self.atualizar_filtros_dinamicos()
        CategoriasDialog(self, self.db, self.tema, cb)

    # ── Cards de resumo ───────────────────────────────────────────────────────

    def _criar_resumo_compacto(self, parent, destino_lista):
        frame = ttk.Frame(parent)
        for i in range(4):
            frame.grid_columnconfigure(i, weight=1)
        configs = [
            ("Total de Registros",  "CardValue.TLabel",     "⊞"),
            ("Pagamentos",          "CardValuePag.TLabel",  "↑"),
            ("Recebimentos",        "CardValueRec.TLabel",  "↓"),
            ("Saldo (BRL)",         "CardValueSaldo.TLabel","≈"),
        ]
        refs = []
        for i, (titulo, estilo, icone) in enumerate(configs):
            card = ttk.Frame(frame, style="Card.TFrame", padding=(14,12))
            card.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 6, 0))
            top = ttk.Frame(card, style="Card.TFrame")
            top.pack(fill="x")
            ttk.Label(top, text=titulo, style="CardTitle.TLabel").pack(side="left")
            ttk.Label(top, text=icone, style="CardTitle.TLabel",
                      font=("Segoe UI",12)).pack(side="right")
            lbl = ttk.Label(card, text="0", style=estilo)
            lbl.pack(anchor="w", pady=(8,0))
            refs.append(lbl)
        destino_lista.append(refs)
        return frame

    def _carregar_resumos(self):
        total_regs, por_moeda = self.db.estatisticas_gerais()
        # BRL para saldo; demais moedas somadas apenas para pag/rec (sem conversão)
        brl = por_moeda.get("BRL", {"pag": 0.0, "rec": 0.0})
        total_pag = sum(v["pag"] for v in por_moeda.values())
        total_rec = sum(v["rec"] for v in por_moeda.values())
        saldo_brl = brl["rec"] - brl["pag"]

        def fmt(v):
            return f"{v:,.2f}".replace(",","X").replace(".",",").replace("X",".")

        saldo_txt = ("+ " if saldo_brl >= 0 else "- ") + fmt(abs(saldo_brl))
        cor_saldo = self.tema["saldo_pos"] if saldo_brl >= 0 else self.tema["saldo_neg"]

        # Aviso se houver múltiplas moedas
        aviso = " (somente BRL)" if len(por_moeda) > 1 else ""

        for grupo in (self.cards_busca + self.cards_graficos):
            grupo[0].config(text=str(total_regs))
            grupo[1].config(text=fmt(total_pag))
            grupo[2].config(text=fmt(total_rec))
            grupo[3].config(text=saldo_txt + aviso, foreground=cor_saldo)

        self._atualizar_todos_graficos()

    # ── Aba Registrar ─────────────────────────────────────────────────────────

    def _criar_aba_registrar(self):
        outer = ttk.Frame(self.aba_registrar)
        outer.pack(fill="both", expand=True)
        outer.grid_columnconfigure(0, weight=1)
        outer.grid_rowconfigure(0, weight=1)

        card = ttk.Frame(outer, style="Card.TFrame", padding=(28,24))
        card.grid(row=0, column=0, sticky="nsew")
        for col in range(4):
            card.grid_columnconfigure(col, weight=1)

        # Título
        tit = ttk.Frame(card, style="Card.TFrame")
        tit.grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0,22))
        tit.columnconfigure(0, weight=1)
        ttk.Label(tit, text="Novo Registro", style="Card.TLabel",
                  font=("Segoe UI Semibold",16,"bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(tit, text=f"Hoje: {formatar_data_br(datetime.date.today())}",
                  style="CardTitle.TLabel").grid(row=0, column=1, sticky="e")

        def lbl(txt, r, c, anchor="w"):
            ttk.Label(card, text=txt, style="Card.TLabel").grid(
                row=r, column=c, sticky=anchor,
                padx=(6 if c == 0 else 10, 0), pady=8)

        lbl("Tipo:", 1, 0)
        self.cad_tipo_combo = ttk.Combobox(card, state="readonly",
                                            values=["Pagamento","Recebimento"])
        self.cad_tipo_combo.grid(row=1, column=1, sticky="ew", padx=6, pady=8)
        self.cad_tipo_combo.set("Pagamento")

        lbl("Nome / Pessoa / Empresa:", 1, 2)
        self.cad_nome_entry = ttk.Entry(card)
        self.cad_nome_entry.grid(row=1, column=3, sticky="ew", padx=6, pady=8)

        lbl("Data (dd/mm/aaaa):", 2, 0)
        self.cad_data_entry = ttk.Entry(card)
        self.cad_data_entry.grid(row=2, column=1, sticky="ew", padx=6, pady=8)
        self.cad_data_entry.insert(0, formatar_data_br(datetime.date.today()))
        self._configurar_entry_data(self.cad_data_entry)

        lbl("Valor:", 2, 2)
        self.cad_valor_entry = ttk.Entry(card)
        self.cad_valor_entry.grid(row=2, column=3, sticky="ew", padx=6, pady=8)
        self._configurar_entry_valor(self.cad_valor_entry)

        moeda_padrao = self.config_app.get("moeda_padrao", "BRL")
        lbl("Moeda:", 3, 0)
        self.cad_moeda_combo = ttk.Combobox(card, state="readonly",
                                             values=list(MOEDAS.keys()))
        self.cad_moeda_combo.grid(row=3, column=1, sticky="ew", padx=6, pady=8)
        self.cad_moeda_combo.set(moeda_padrao)

        lbl("Categoria:", 3, 2)
        self.cad_categoria_combo = ttk.Combobox(card,
                                                 values=self.db.categorias_existentes())
        self.cad_categoria_combo.grid(row=3, column=3, sticky="ew", padx=6, pady=8)
        self.cad_categoria_combo.set("Outros")

        lbl("Observação:", 4, 0, "nw")
        self.cad_obs_text = tk.Text(
            card, height=5, bg=self.tema["text_bg"], fg=self.tema["text_fg"],
            insertbackground=self.tema["text_fg"], relief="flat",
            padx=10, pady=10, bd=0,
            highlightthickness=1, highlightbackground=self.tema["border"],
            highlightcolor=self.tema["primary"],
            font=("Segoe UI",10), undo=True, maxundo=50,
        )
        self.cad_obs_text.grid(row=4, column=1, columnspan=3, sticky="ew", padx=6, pady=8)

        botoes = ttk.Frame(card, style="Card.TFrame")
        botoes.grid(row=5, column=0, columnspan=4, sticky="ew", pady=(18,4))
        for i in range(3):
            botoes.grid_columnconfigure(i, weight=1)
        ttk.Button(botoes, text="✔  Salvar", command=self.salvar_registro,
                   style="Primary.TButton").grid(row=0, column=0, padx=(0,8), sticky="ew")
        ttk.Button(botoes, text="↺  Limpar", command=self.limpar_campos_cadastro,
                   style="Secondary.TButton").grid(row=0, column=1, padx=8, sticky="ew")
        ttk.Button(botoes, text="⬛  Backup", command=self.backup_manual,
                   style="Secondary.TButton").grid(row=0, column=2, padx=(8,0), sticky="ew")

        self.cad_status = ttk.Label(card, text="", style="Card.TLabel",
                                     font=("Segoe UI",9))
        self.cad_status.grid(row=6, column=0, columnspan=4, sticky="w",
                              pady=(8,0), padx=6)

        # Tab order explícito
        widgets_tab = [
            self.cad_tipo_combo, self.cad_nome_entry,
            self.cad_data_entry, self.cad_valor_entry,
            self.cad_moeda_combo, self.cad_categoria_combo,
            self.cad_obs_text,
        ]
        for i, w in enumerate(widgets_tab):
            w.lift()
        self.cad_nome_entry.bind("<Return>", lambda e: self.cad_valor_entry.focus_set())
        self.cad_valor_entry.bind("<Return>", lambda e: self.salvar_registro())

        # Tooltips nos botões do formulário
        self._tooltip_btn(botoes, 0, "Ctrl+S")

    # ── Salvar ────────────────────────────────────────────────────────────────

    def salvar_registro(self):
        try:
            tipo      = self.cad_tipo_combo.get().strip()
            nome      = self.cad_nome_entry.get().strip()
            data_str  = self.cad_data_entry.get().strip()
            valor_str = self.cad_valor_entry.get().strip()
            moeda     = self.cad_moeda_combo.get().strip()
            categoria = self.cad_categoria_combo.get().strip() or "Outros"
            obs       = self.cad_obs_text.get("1.0","end-1c").strip()

            if len(nome) < 2:
                self._status(self.cad_status,"⚠  Nome deve ter pelo menos 2 caracteres.","erro")
                self.cad_nome_entry.focus_set(); return
            if not tipo or not moeda:
                self._status(self.cad_status,"⚠  Tipo e Moeda são obrigatórios.","erro"); return
            if len(data_str) != 10:
                self._status(self.cad_status,"⚠  Data inválida (dd/mm/aaaa).","erro")
                self.cad_data_entry.focus_set(); return

            data = parse_data_br(data_str)
            limite = datetime.date.today() + datetime.timedelta(days=366)
            if data > limite:
                self._status(self.cad_status,"⚠  Data muito distante no futuro.","erro"); return

            valor = normalizar_valor(valor_str)
            reg_id = self.db.inserir_registro(tipo, nome, data, valor, moeda, categoria, obs)
            self._status(self.cad_status,
                         f"✔  ID {reg_id} salvo — {tipo}  {formatar_valor(valor, moeda)}",
                         "sucesso")
            self.limpar_campos_cadastro()
            self.atualizar_filtros_dinamicos()
            self._carregar_resumos()
            self.ver_todos()
        except ValueError as e:
            self._status(self.cad_status, f"⚠  {e}", "erro")
        except Exception:
            self._status(self.cad_status,"⚠  Erro: revise os campos.","erro")

    def limpar_campos_cadastro(self):
        self.cad_tipo_combo.set("Pagamento")
        self.cad_nome_entry.delete(0, tk.END)
        self.cad_data_entry.delete(0, tk.END)
        self.cad_data_entry.insert(0, formatar_data_br(datetime.date.today()))
        self.cad_valor_entry.delete(0, tk.END)
        self.cad_moeda_combo.set(self.config_app.get("moeda_padrao","BRL"))
        self.cad_categoria_combo.set("Outros")
        self.cad_obs_text.delete("1.0","end")
        self.cad_nome_entry.focus_set()

    def backup_manual(self):
        realizar_backup_automatico(DB_FILE, self.config_app.get("max_backups",15))
        self._status(self.cad_status,
                     f"✔  Backup salvo em: {BACKUP_DIR}", "sucesso")

    # ── Aba Busca ─────────────────────────────────────────────────────────────

    def _criar_aba_busca(self):
        outer = ttk.Frame(self.aba_busca)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(0, weight=1)

        # Painel de filtros com scroll
        filtros_container = ttk.Frame(outer, style="Card.TFrame")
        filtros_container.grid(row=0, column=0, sticky="nsw", padx=(0,16))
        filtros_container.configure(width=280)
        filtros_container.grid_propagate(False)

        cv = tk.Canvas(filtros_container, bg=self.tema["surface"],
                       highlightthickness=0, width=264)
        sb = ttk.Scrollbar(filtros_container, orient="vertical", command=cv.yview)
        cv.configure(yscrollcommand=sb.set)
        cv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        fw = tk.Frame(cv, bg=self.tema["surface"], padx=16, pady=16)
        fw_id = cv.create_window((0,0), window=fw, anchor="nw")

        cv.bind("<Configure>",  lambda e: cv.itemconfig(fw_id, width=cv.winfo_width()))
        fw.bind("<Configure>",  lambda e: cv.configure(scrollregion=cv.bbox("all")))

        # Scroll do mouse — só quando o cursor está sobre o painel de filtros
        def _mw_f(e):
            cv.yview_scroll(int(-1*(e.delta/120)),"units"); return "break"
        def _mw_f_linux(e):
            cv.yview_scroll(-1 if e.num==4 else 1,"units"); return "break"
        def _on_enter_f(e=None):
            cv.bind_all("<MouseWheel>",_mw_f)
            cv.bind_all("<Button-4>",_mw_f_linux)
            cv.bind_all("<Button-5>",_mw_f_linux)
        def _on_leave_f(e=None):
            cv.unbind_all("<MouseWheel>")
            cv.unbind_all("<Button-4>")
            cv.unbind_all("<Button-5>")
        cv.bind("<Enter>",_on_enter_f); cv.bind("<Leave>",_on_leave_f)
        fw.bind("<Enter>",_on_enter_f); fw.bind("<Leave>",_on_leave_f)

        def sec(txt):
            tk.Label(fw, text=txt, bg=self.tema["surface"], fg=self.tema["fg"],
                     font=("Segoe UI Semibold",11,"bold")).pack(anchor="w", pady=(0,12))
        def lbl(txt):
            tk.Label(fw, text=txt, bg=self.tema["surface"], fg=self.tema["muted"],
                     font=("Segoe UI",9,"bold")).pack(anchor="w", pady=(8,3))

        sec("⊞  Filtros")

        lbl("Texto livre")
        self.filtro_texto_entry = ttk.Entry(fw)
        self.filtro_texto_entry.pack(fill="x", pady=(0,4))

        lbl("Tipo")
        self.filtro_tipo_combo = ttk.Combobox(fw, state="readonly",
                                               values=["Todos","Pagamento","Recebimento"])
        self.filtro_tipo_combo.set("Todos")
        self.filtro_tipo_combo.pack(fill="x", pady=(0,4))

        lbl("Categoria")
        self.filtro_categoria_combo = ttk.Combobox(fw, state="readonly",
                                                    values=["Todas"]+self.db.categorias_existentes())
        self.filtro_categoria_combo.set("Todas")
        self.filtro_categoria_combo.pack(fill="x", pady=(0,4))

        lbl("Moeda")
        self.filtro_moeda_combo = ttk.Combobox(fw, state="readonly",
                                                values=["Todas"]+list(MOEDAS.keys()))
        self.filtro_moeda_combo.set("Todas")
        self.filtro_moeda_combo.pack(fill="x", pady=(0,4))

        lbl("Período")
        self.filtro_periodo_combo = ttk.Combobox(fw, state="readonly",
            values=["Personalizado","Hoje","Esta semana","Este mês","Últimos 30 dias","Este ano"])
        self.filtro_periodo_combo.set("Personalizado")
        self.filtro_periodo_combo.pack(fill="x", pady=(0,4))

        # Mês / Ano
        ma = tk.Frame(fw, bg=self.tema["surface"])
        ma.pack(fill="x", pady=(4,4))
        ma.columnconfigure(0, weight=1); ma.columnconfigure(1, weight=1)
        tk.Label(ma, text="Mês", bg=self.tema["surface"], fg=self.tema["muted"],
                 font=("Segoe UI",9,"bold")).grid(row=0, column=0, sticky="w")
        tk.Label(ma, text="Ano", bg=self.tema["surface"], fg=self.tema["muted"],
                 font=("Segoe UI",9,"bold")).grid(row=0, column=1, sticky="w", padx=(8,0))
        self.filtro_mes_combo = ttk.Combobox(ma, state="readonly",
                                              values=["Todos"]+[str(i) for i in range(1,13)])
        self.filtro_mes_combo.grid(row=1, column=0, sticky="ew")
        self.filtro_mes_combo.set("Todos")
        self.filtro_ano_combo = ttk.Combobox(ma, state="readonly", values=["Todos"])
        self.filtro_ano_combo.grid(row=1, column=1, sticky="ew", padx=(8,0))
        self.filtro_ano_combo.set("Todos")

        # Filtro por valor
        lbl("Valor mínimo")
        self.filtro_valor_min = ttk.Entry(fw)
        self.filtro_valor_min.pack(fill="x", pady=(0,4))
        self._configurar_entry_valor(self.filtro_valor_min)

        lbl("Valor máximo")
        self.filtro_valor_max = ttk.Entry(fw)
        self.filtro_valor_max.pack(fill="x", pady=(0,4))
        self._configurar_entry_valor(self.filtro_valor_max)

        tk.Frame(fw, bg=self.tema["border"], height=1).pack(fill="x", pady=(14,12))

        bf = tk.Frame(fw, bg=self.tema["surface"])
        bf.pack(fill="x", pady=(0,6))
        bf.columnconfigure(0,weight=1); bf.columnconfigure(1,weight=1)
        ttk.Button(bf, text="⊞ Buscar", command=self.pesquisar,
                   style="Primary.TButton").grid(row=0,column=0,sticky="ew",padx=(0,4))
        ttk.Button(bf, text="↺ Limpar", command=self.limpar_filtros,
                   style="Secondary.TButton").grid(row=0,column=1,sticky="ew",padx=(4,0))

        bf2 = tk.Frame(fw, bg=self.tema["surface"])
        bf2.pack(fill="x", pady=(0,4))
        bf2.columnconfigure(0,weight=1); bf2.columnconfigure(1,weight=1)
        ttk.Button(bf2, text="Ver Todos", command=self.ver_todos,
                   style="Secondary.TButton").grid(row=0,column=0,sticky="ew",padx=(0,4))
        ttk.Button(bf2, text="✖ Excluir", command=self.excluir_selecionado,
                   style="Danger.TButton").grid(row=0,column=1,sticky="ew",padx=(4,0))

        tk.Frame(fw, bg=self.tema["border"], height=1).pack(fill="x", pady=(12,10))
        tk.Label(fw, text="⚡  Atalhos rápidos", bg=self.tema["surface"],
                 fg=self.tema["muted"], font=("Segoe UI",9,"bold")).pack(anchor="w",pady=(0,8))

        for txt, modo in [("Hoje","hoje"),("Esta semana","semana"),
                           ("Este mês","mes"),("Últimos 30 dias","30dias"),("Este ano","ano")]:
            ttk.Button(fw, text=txt,
                       command=lambda m=modo: self.aplicar_filtro_rapido(m),
                       style="Secondary.TButton").pack(fill="x", pady=3)

        # ── Área direita ──────────────────────────────────────────────────────
        direita = ttk.Frame(outer)
        direita.grid(row=0, column=1, sticky="nsew")
        direita.columnconfigure(0, weight=1)
        direita.rowconfigure(2, weight=1)

        topbar = ttk.Frame(direita)
        topbar.grid(row=0, column=0, sticky="ew", pady=(0,10))
        topbar.columnconfigure(0, weight=1)
        ttk.Label(topbar, text="Registros", style="Section.TLabel").grid(row=0,column=0,sticky="w")
        acoes = ttk.Frame(topbar)
        acoes.grid(row=0, column=1, sticky="e")
        ttk.Button(acoes, text="✏ Editar",
                   command=self.editar_selecionado, style="Secondary.TButton").pack(side="left",padx=(0,6))
        ttk.Button(acoes, text="⿻ Duplicar",
                   command=self.duplicar_selecionado, style="Secondary.TButton").pack(side="left",padx=(0,6))
        ttk.Button(acoes, text="✖ Apagar",
                   command=self.excluir_selecionado, style="Danger.TButton").pack(side="left",padx=(0,6))
        ttk.Button(acoes, text="📥 CSV",
                   command=self.exportar_csv, style="Secondary.TButton").pack(side="left",padx=(0,6))
        ttk.Button(acoes, text="📤 Importar",
                   command=self.importar_csv, style="Secondary.TButton").pack(side="left")

        resumo_frame = self._criar_resumo_compacto(direita, self.cards_busca)
        resumo_frame.grid(row=1, column=0, sticky="ew", pady=(0,10))

        tabela_card = ttk.Frame(direita, style="Card.TFrame", padding=(12,10))
        tabela_card.grid(row=2, column=0, sticky="nsew")
        tabela_card.columnconfigure(0, weight=1)
        tabela_card.rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            tabela_card,
            columns=("ID","Tipo","Data","Nome","Valor","Moeda","Categoria","Observação"),
            show="headings",
        )
        for nome, larg, anch in [
            ("ID",65,"center"),("Tipo",120,"center"),("Data",100,"center"),
            ("Nome",260,"w"),("Valor",140,"e"),("Moeda",80,"center"),
            ("Categoria",150,"center"),("Observação",340,"w"),
        ]:
            self.tree.heading(nome, text=nome,
                              command=lambda c=nome: self.ordenar_treeview(c))
            self.tree.column(nome, width=larg, minwidth=60, anchor=anch,
                             stretch=(nome in ("Nome","Observação")))

        sy = ttk.Scrollbar(tabela_card, orient="vertical",   command=self.tree.yview)
        sx = ttk.Scrollbar(tabela_card, orient="horizontal",  command=self.tree.xview)
        self.tree.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        sy.grid(row=0, column=1, sticky="ns")
        sx.grid(row=1, column=0, sticky="ew")

        for tag, bg, fg, fnt in [
            ("total",    self.tema["summary_row"],self.tema["fg"],("Segoe UI Semibold",10,"bold")),
            ("saldo_pos",self.tema["summary_row"],self.tema["saldo_pos"],("Segoe UI Semibold",10,"bold")),
            ("saldo_neg",self.tema["summary_row"],self.tema["saldo_neg"],("Segoe UI Semibold",10,"bold")),
        ]:
            self.tree.tag_configure(tag, background=bg, foreground=fg, font=fnt)
        self.tree.tag_configure("pagamento",   foreground=self.tema["pag_color"])
        self.tree.tag_configure("recebimento", foreground=self.tema["rec_color"])

        self.tooltip = TreeTooltip(self.tree, self.tema)
        self.tree.bind("<Double-1>",         lambda e: self.editar_selecionado())
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._status(
            self.lbl_resultado,"Registro selecionado. Duplo clique para editar.","info"))
        self.tree.bind("<Delete>",           lambda e: self.excluir_selecionado())
        self.tree.bind("<Configure>",        self._ajustar_colunas_tabela)
        self.tree.bind("<d>",                lambda e: self.duplicar_selecionado())

        # Scroll isolado na tabela
        def _mw_t(e):
            self.tree.yview_scroll(int(-1*(e.delta/120)),"units"); return "break"
        def _mw_t_linux(e):
            self.tree.yview_scroll(-1 if e.num==4 else 1,"units"); return "break"
        def _on_enter_t(e=None):
            self.tree.bind_all("<MouseWheel>",_mw_t)
            self.tree.bind_all("<Button-4>",_mw_t_linux)
            self.tree.bind_all("<Button-5>",_mw_t_linux)
        def _on_leave_t(e=None):
            self.tree.unbind_all("<MouseWheel>")
            self.tree.unbind_all("<Button-4>")
            self.tree.unbind_all("<Button-5>")
        self.tree.bind("<Enter>",_on_enter_t)
        self.tree.bind("<Leave>",_on_leave_t)

        bottom = ttk.Frame(direita)
        bottom.grid(row=3, column=0, sticky="ew", pady=(8,0))
        bottom.columnconfigure(0, weight=1)
        ttk.Button(bottom, text="Limpar Seleção",
                   command=self.limpar_selecao_registro,
                   style="Secondary.TButton").grid(row=0,column=0,sticky="w")
        self.lbl_resultado = ttk.Label(bottom, text="", style="Muted.TLabel",
                                        font=("Segoe UI",9))
        self.lbl_resultado.grid(row=0, column=1, sticky="e")

        self.atualizar_filtros_dinamicos()

        # Bindings dos filtros
        self.filtro_texto_entry.bind("<Return>", lambda e: self.pesquisar())
        for w in (self.filtro_tipo_combo, self.filtro_categoria_combo,
                  self.filtro_moeda_combo):
            w.bind("<<ComboboxSelected>>", lambda e: self.pesquisar())
        self.filtro_mes_combo.bind("<<ComboboxSelected>>", self._usar_periodo_manual)
        self.filtro_ano_combo.bind("<<ComboboxSelected>>", self._usar_periodo_manual)
        self.filtro_periodo_combo.bind("<<ComboboxSelected>>", self._aplicar_periodo_combo)

        # Busca em tempo real (debounce 350ms)
        if self.config_app.get("busca_tempo_real", True):
            self.filtro_texto_entry.bind("<KeyRelease>", self._busca_tempo_real)
        for w in (self.filtro_valor_min, self.filtro_valor_max):
            w.bind("<Return>", lambda e: self.pesquisar())
            w.bind("<FocusOut>", lambda e: self.pesquisar())

    # ── Aba Gráficos ──────────────────────────────────────────────────────────

    def _criar_aba_graficos(self):
        wrapper = ttk.Frame(self.aba_graficos)
        wrapper.pack(fill="both", expand=True)
        wrapper.columnconfigure(0, weight=1)
        wrapper.rowconfigure(0, weight=1)

        sg = ttk.Scrollbar(wrapper, orient="vertical")
        sg.grid(row=0, column=1, sticky="ns")
        cg = tk.Canvas(wrapper, yscrollcommand=sg.set,
                       highlightthickness=0, bg=self.tema["bg"])
        cg.grid(row=0, column=0, sticky="nsew")
        sg.config(command=cg.yview)

        outer = ttk.Frame(cg)
        oid = cg.create_window((0,0), window=outer, anchor="nw")
        cg.bind("<Configure>", lambda e: cg.itemconfig(oid, width=cg.winfo_width()))
        outer.bind("<Configure>", lambda e: cg.configure(scrollregion=cg.bbox("all")))

        def _mw_g(e):
            cg.yview_scroll(int(-1*(e.delta/120)),"units"); return "break"
        def _mw_g_linux(e):
            cg.yview_scroll(-1 if e.num==4 else 1,"units"); return "break"
        def _on_enter_g(e=None):
            cg.bind_all("<MouseWheel>",_mw_g)
            cg.bind_all("<Button-4>",_mw_g_linux)
            cg.bind_all("<Button-5>",_mw_g_linux)
        def _on_leave_g(e=None):
            cg.unbind_all("<MouseWheel>")
            cg.unbind_all("<Button-4>")
            cg.unbind_all("<Button-5>")
        cg.bind("<Enter>",_on_enter_g); cg.bind("<Leave>",_on_leave_g)
        outer.bind("<Enter>",_on_enter_g); outer.bind("<Leave>",_on_leave_g)

        outer.grid_columnconfigure(0, weight=1)
        ttk.Label(outer, text="Visões Gráficas",
                  style="Section.TLabel").grid(row=0,column=0,sticky="w",pady=(0,10))

        ctrl = ttk.Frame(outer, style="Card.TFrame", padding=14)
        ctrl.grid(row=1, column=0, sticky="ew", pady=(0,12))
        ttk.Label(ctrl, text="Gráfico por categoria:", style="Card.TLabel").pack(side="left",padx=5)
        self.grafico_categoria_tipo = ttk.Combobox(ctrl, state="readonly",
                                                    values=["Pagamento","Recebimento"], width=16)
        self.grafico_categoria_tipo.pack(side="left", padx=6)
        self.grafico_categoria_tipo.set("Pagamento")
        self.grafico_categoria_tipo.bind("<<ComboboxSelected>>",
                                          lambda e: self._atualizar_grafico_categoria())
        ttk.Button(ctrl, text="↺  Atualizar", command=self._atualizar_todos_graficos,
                   style="Primary.TButton").pack(side="left", padx=6)

        cont = ttk.Frame(outer)
        cont.grid(row=2, column=0, sticky="ew", pady=(0,10))
        cont.grid_columnconfigure(0, weight=1)
        cont.grid_columnconfigure(1, weight=1)

        fm = ttk.Frame(cont, style="Card.TFrame", padding=14)
        fm.grid(row=0, column=0, sticky="nsew", padx=(0,6), pady=(0,10))
        self.figura_mensal = Figure(figsize=(5,3.2), dpi=100)
        self.ax_mensal = self.figura_mensal.add_subplot(111)
        self.canvas_mensal = FigureCanvasTkAgg(self.figura_mensal, master=fm)
        self.canvas_mensal.get_tk_widget().pack(fill="both", expand=True)

        fc = ttk.Frame(cont, style="Card.TFrame", padding=14)
        fc.grid(row=0, column=1, sticky="nsew", padx=(6,0), pady=(0,10))
        self.figura_categoria = Figure(figsize=(5,3.2), dpi=100)
        self.ax_categoria = self.figura_categoria.add_subplot(111)
        self.canvas_categoria = FigureCanvasTkAgg(self.figura_categoria, master=fc)
        self.canvas_categoria.get_tk_widget().pack(fill="both", expand=True)

        fs = ttk.Frame(cont, style="Card.TFrame", padding=14)
        fs.grid(row=1, column=0, columnspan=2, sticky="ew")
        self.figura_saldo = Figure(figsize=(10,2.8), dpi=100)
        self.ax_saldo = self.figura_saldo.add_subplot(111)
        self.canvas_saldo = FigureCanvasTkAgg(self.figura_saldo, master=fs)
        self.canvas_saldo.get_tk_widget().pack(fill="both", expand=True)

        resumo = self._criar_resumo_compacto(outer, self.cards_graficos)
        resumo.grid(row=3, column=0, sticky="ew", pady=(12,8))

    # ── Estilos de gráfico ────────────────────────────────────────────────────

    def _estilo_grafico(self, fig, ax, titulo, xlabel, ylabel):
        t = self.tema
        fig.patch.set_facecolor(t["surface"])
        ax.set_facecolor(t["surface"])
        ax.set_title(titulo, pad=10, fontsize=11, fontweight="bold", color=t["fg"])
        ax.set_xlabel(xlabel, color=t["muted"], fontsize=9)
        ax.set_ylabel(ylabel, color=t["muted"], fontsize=9)
        ax.tick_params(axis="x", colors=t["fg"], labelsize=8)
        ax.tick_params(axis="y", colors=t["fg"], labelsize=8)
        ax.grid(True, alpha=0.15, color=t["border"], linestyle="--")
        for sp in ax.spines.values():
            sp.set_color(t["border"]); sp.set_linewidth(0.8)

    def _atualizar_todos_graficos(self):
        self._atualizar_grafico_mensal()
        self._atualizar_grafico_categoria()
        self._atualizar_grafico_saldo()

    def _atualizar_grafico_mensal(self):
        if not hasattr(self, "ax_mensal"):
            return
        labels, pags, recs = self.db.dados_grafico_mensal()
        ax = self.ax_mensal; ax.clear()
        if labels:
            x = range(len(labels))
            pc = "#F85149" if self.tema_atual_nome == "dark" else "#DC2626"
            rc = "#3FB950" if self.tema_atual_nome == "dark" else "#16A34A"
            ax.fill_between(x, pags, alpha=0.08, color=pc)
            ax.fill_between(x, recs, alpha=0.08, color=rc)
            ax.plot(x, pags, marker="o", lw=2, color=pc, label="Pagamentos", ms=5)
            ax.plot(x, recs, marker="o", lw=2, color=rc, label="Recebimentos", ms=5)
            ax.set_xticks(list(x)); ax.set_xticklabels(labels, rotation=35, ha="right")
            ax.legend(frameon=False, labelcolor=self.tema["fg"], fontsize=9)
        else:
            ax.text(0.5,0.5,"Sem dados",ha="center",va="center",
                    transform=ax.transAxes,color=self.tema["muted"])
        self._estilo_grafico(self.figura_mensal,ax,"Pagamentos × Recebimentos","","R$")
        self.figura_mensal.tight_layout(); self.canvas_mensal.draw()

    def _atualizar_grafico_categoria(self):
        if not hasattr(self, "ax_categoria"):
            return
        tipo = self.grafico_categoria_tipo.get() if hasattr(self,"grafico_categoria_tipo") else "Pagamento"
        tipo = tipo or "Pagamento"
        cats, vals = self.db.dados_grafico_categoria(tipo)
        ax = self.ax_categoria; ax.clear()
        if cats:
            cor = ("#F85149" if tipo == "Pagamento" else "#3FB950") \
                  if self.tema_atual_nome == "dark" \
                  else ("#DC2626" if tipo == "Pagamento" else "#16A34A")
            max_v = max(vals) if vals else 1
            bars = ax.bar(cats[:10], vals[:10], width=0.6, color=cor, alpha=0.85, zorder=3)
            for bar, v in zip(bars, vals[:10]):
                ax.text(bar.get_x()+bar.get_width()/2, bar.get_height()+max_v*0.01,
                        f"R$ {v:,.0f}", ha="center", va="bottom",
                        fontsize=7, color=self.tema["muted"])
        else:
            ax.text(0.5,0.5,"Sem dados",ha="center",va="center",
                    transform=ax.transAxes,color=self.tema["muted"])
        self._estilo_grafico(self.figura_categoria,ax,f"{tipo}s por Categoria","","R$")
        ax.tick_params(axis="x",rotation=30)
        self.figura_categoria.tight_layout(); self.canvas_categoria.draw()

    def _atualizar_grafico_saldo(self):
        if not hasattr(self, "ax_saldo"):
            return
        labels, ac = self.db.dados_grafico_saldo_acumulado()
        ax = self.ax_saldo; ax.clear()
        if labels:
            cp = self.tema["saldo_pos"]; cn = self.tema["saldo_neg"]
            ax.fill_between(range(len(labels)),ac,0,
                            where=[v>=0 for v in ac],alpha=0.18,color=cp,interpolate=True)
            ax.fill_between(range(len(labels)),ac,0,
                            where=[v<0  for v in ac],alpha=0.18,color=cn,interpolate=True)
            ax.plot(range(len(labels)),ac,marker="o",lw=2,ms=5,
                    color=(cp if ac[-1]>=0 else cn))
            ax.axhline(0,color=self.tema["border"],lw=1,linestyle="--")
            ax.set_xticks(range(len(labels)))
            ax.set_xticklabels(labels,rotation=30,ha="right")
        else:
            ax.text(0.5,0.5,"Sem dados BRL",ha="center",va="center",
                    transform=ax.transAxes,color=self.tema["muted"])
        self._estilo_grafico(self.figura_saldo,ax,"Saldo Acumulado (BRL)","","R$")
        self.figura_saldo.tight_layout(); self.canvas_saldo.draw()

    # ── Tabela ────────────────────────────────────────────────────────────────

    def _ajustar_colunas_tabela(self, event=None):
        if not hasattr(self,"tree"): return
        try: w = self.tree.winfo_width()
        except Exception: return
        if w <= 100: return
        util = max(w-22, 720)
        props = {"ID":.06,"Tipo":.10,"Data":.09,"Nome":.22,
                 "Valor":.13,"Moeda":.07,"Categoria":.12,"Observação":.21}
        mins  = {"ID":55,"Tipo":90,"Data":85,"Nome":140,
                 "Valor":105,"Moeda":65,"Categoria":100,"Observação":130}
        for nome, prop in props.items():
            self.tree.column(nome, width=max(int(util*prop), mins[nome]))

    def ordenar_treeview(self, col):
        mapa = {
            "ID":         lambda r: r["id"],
            "Tipo":       lambda r: r["tipo"],
            "Data":       lambda r: r["data"],
            "Nome":       lambda r: r["nome"].lower(),
            "Valor":      lambda r: r["valor"],
            "Moeda":      lambda r: r["moeda"],
            "Categoria":  lambda r: r["categoria"].lower(),
            "Observação": lambda r: r.get("observacao","").lower(),
        }
        if col not in mapa: return
        rev = self.ordem_coluna.get(col, False)
        self.ordem_coluna[col] = not rev
        self.preencher_tabela(sorted(self.resultados_atuais, key=mapa[col], reverse=rev),
                               f"Ordenado por {col}.")

    def limpar_tabela(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

    def preencher_tabela(self, registros, mensagem=""):
        self.resultados_atuais = list(registros)
        self.limpar_tabela()
        totais: dict = {}
        n = 0
        for tag, bg, fg, fnt in [
            ("total",    self.tema["summary_row"],self.tema["fg"],("Segoe UI Semibold",10,"bold")),
            ("saldo_pos",self.tema["summary_row"],self.tema["saldo_pos"],("Segoe UI Semibold",10,"bold")),
            ("saldo_neg",self.tema["summary_row"],self.tema["saldo_neg"],("Segoe UI Semibold",10,"bold")),
        ]:
            self.tree.tag_configure(tag,background=bg,foreground=fg,font=fnt)
        self.tree.tag_configure("pagamento",   foreground=self.tema["pag_color"])
        self.tree.tag_configure("recebimento", foreground=self.tema["rec_color"])

        for reg in registros:
            moeda = reg["moeda"]
            totais.setdefault(moeda, {"Pagamento":0.0,"Recebimento":0.0})
            totais[moeda][reg["tipo"]] += reg["valor"]
            n += 1

            obs = reg.get("observacao","")
            obs_ex = obs[:65]+"…" if len(obs)>65 else obs
            tipo_tag = "pagamento" if reg["tipo"]=="Pagamento" else "recebimento"
            tags = [tipo_tag]
            if isinstance(reg.get("data_hora_adicao"), datetime.datetime):
                tags.append(f"dh:{reg['data_hora_adicao'].isoformat()}")
            if reg.get("data_hora_edicao"):
                tags.append(f"ed:{reg['data_hora_edicao']}")

            self.tree.insert("","end",values=(
                reg["id"], reg["tipo"], formatar_data_br(reg["data"]),
                reg["nome"], formatar_valor(reg["valor"],reg["moeda"]),
                reg["moeda"], reg["categoria"], obs_ex,
            ), tags=tuple(tags))

        if registros:
            self.tree.insert("","end",
                values=("","─"*8,"","─"*20,"─"*12,"","",""), tags=("total",))
            for moeda, mp in sorted(totais.items()):
                pag = mp["Pagamento"]; rec = mp["Recebimento"]
                saldo = rec - pag
                stag = "saldo_pos" if saldo>=0 else "saldo_neg"
                pref = "+" if saldo>=0 else ""
                self.tree.insert("","end",values=(
                    "","TOTAL","",f"Pagamentos ({moeda})",
                    formatar_valor(pag,moeda),moeda,"",""), tags=("total",))
                self.tree.insert("","end",values=(
                    "","TOTAL","",f"Recebimentos ({moeda})",
                    formatar_valor(rec,moeda),moeda,"",""), tags=("total",))
                self.tree.insert("","end",values=(
                    "","SALDO","",f"Saldo ({moeda})",
                    f"{pref}{formatar_valor(saldo,moeda)}",moeda,"",""), tags=(stag,))

        self._ajustar_colunas_tabela()
        self._status(self.lbl_resultado,
                     mensagem or f"{n} registro(s) exibido(s).","info")

    # ── Filtros e pesquisa ────────────────────────────────────────────────────

    def _busca_tempo_real(self, event=None):
        if self._debounce_id:
            self.after_cancel(self._debounce_id)
        self._debounce_id = self.after(350, self.pesquisar)

    def _usar_periodo_manual(self, event=None):
        self.periodo_rapido = None
        self.filtro_periodo_combo.set("Personalizado")
        self.pesquisar()

    def _aplicar_periodo_combo(self, event=None):
        mapa = {"Hoje":"hoje","Esta semana":"semana","Este mês":"mes",
                "Últimos 30 dias":"30dias","Este ano":"ano"}
        v = self.filtro_periodo_combo.get().strip()
        if v == "Personalizado":
            self.periodo_rapido = None; self.pesquisar(); return
        modo = mapa.get(v)
        if modo:
            self.aplicar_filtro_rapido(modo)

    def aplicar_filtro_rapido(self, modo):
        self.periodo_rapido = modo
        nomes = {"hoje":"Hoje","semana":"Esta semana","mes":"Este mês",
                 "30dias":"Últimos 30 dias","ano":"Este ano"}
        self.filtro_periodo_combo.set(nomes.get(modo,"Personalizado"))
        self.filtro_mes_combo.set("Todos")
        self.filtro_ano_combo.set("Todos")
        self.pesquisar()

    def atualizar_filtros_dinamicos(self):
        anos = ["Todos"]+[str(a) for a in self.db.anos_existentes()]
        cats = ["Todas"]+self.db.categorias_existentes()
        self.filtro_ano_combo["values"] = anos
        self.filtro_categoria_combo["values"] = cats
        self.cad_categoria_combo["values"] = self.db.categorias_existentes()
        if self.filtro_ano_combo.get() not in anos:
            self.filtro_ano_combo.set("Todos")
        if self.filtro_categoria_combo.get() not in cats:
            self.filtro_categoria_combo.set("Todas")

    def _obter_filtros(self):
        texto     = self.filtro_texto_entry.get().strip()
        tipo      = self.filtro_tipo_combo.get().strip() or "Todos"
        moeda     = self.filtro_moeda_combo.get().strip() or "Todas"
        categoria = self.filtro_categoria_combo.get().strip() or "Todas"
        mes_s = self.filtro_mes_combo.get()
        ano_s = self.filtro_ano_combo.get()
        mes = None if mes_s == "Todos" else int(mes_s)
        ano = None if ano_s == "Todos" else int(ano_s)
        di = df = None
        hoje = datetime.date.today()
        modos = {
            "hoje":   (hoje, hoje),
            "semana": (hoje-datetime.timedelta(days=6), hoje),
            "mes":    (hoje.replace(day=1), hoje),
            "30dias": (hoje-datetime.timedelta(days=29), hoje),
            "ano":    (hoje.replace(month=1,day=1), hoje),
        }
        if self.periodo_rapido in modos:
            di, df = modos[self.periodo_rapido]
            mes = ano = None

        # Filtro de valor
        vm_str = self.filtro_valor_min.get().strip()
        vx_str = self.filtro_valor_max.get().strip()
        vm = None; vx = None
        try:
            if vm_str: vm = normalizar_valor(vm_str)
        except Exception: pass
        try:
            if vx_str: vx = normalizar_valor(vx_str)
        except Exception: pass

        return dict(texto=texto, tipo=tipo, moeda=moeda, categoria=categoria,
                    mes=mes, ano=ano, data_inicial=di, data_final=df,
                    valor_min=vm, valor_max=vx)

    def pesquisar(self):
        try:
            filtros = self._obter_filtros()
            regs = self.db.buscar(**filtros)
            if not regs:
                self.preencher_tabela([], "Nenhum registro encontrado."); return
            partes = []
            if filtros["tipo"] != "Todos":     partes.append(filtros["tipo"].lower())
            if filtros["categoria"] != "Todas":partes.append(f"cat. {filtros['categoria']}")
            if filtros["moeda"] != "Todas":    partes.append(filtros["moeda"])
            if filtros["mes"]:                 partes.append(f"mês {filtros['mes']}")
            if filtros["ano"]:                 partes.append(f"ano {filtros['ano']}")
            if filtros["texto"]:               partes.append('"' + filtros['texto'] + '"')
            if filtros["valor_min"] is not None: partes.append(f"≥ {filtros['valor_min']:.2f}")
            if filtros["valor_max"] is not None: partes.append(f"≤ {filtros['valor_max']:.2f}")
            msg = f"{len(regs)} registro(s)."
            if partes: msg += "  Filtros: " + " · ".join(partes)
            self.preencher_tabela(regs, msg)
        except Exception:
            self._status(self.lbl_resultado,"Erro nos filtros.","erro")

    def ver_todos(self):
        regs = self.db.listar_todos()
        self.preencher_tabela(regs, f"Todos os registros — {len(regs)} no total.")

    def limpar_filtros(self):
        self.periodo_rapido = None
        self.filtro_periodo_combo.set("Personalizado")
        self.filtro_texto_entry.delete(0, tk.END)
        self.filtro_tipo_combo.set("Todos")
        self.filtro_moeda_combo.set("Todas")
        self.filtro_categoria_combo.set("Todas")
        self.filtro_mes_combo.set("Todos")
        self.filtro_ano_combo.set("Todos")
        self.filtro_valor_min.delete(0, tk.END)
        self.filtro_valor_max.delete(0, tk.END)
        self.ver_todos()

    def limpar_selecao_registro(self):
        for item in self.tree.selection():
            self.tree.selection_remove(item)
        self.tree.focus("")
        self._status(self.lbl_resultado,"Seleção limpa.","info")

    def carregar_resumo(self, tipo, periodo):
        regs = self.db.resumo_periodo(tipo, periodo)
        self.preencher_tabela(regs, f"Resumo {periodo} de {tipo.lower()} — {len(regs)} registro(s).")

    # ── CRUD via UI ───────────────────────────────────────────────────────────

    def obter_id_selecionado(self):
        sel = self.tree.selection()
        item = sel[0] if sel else self.tree.focus()
        if not item: return None
        vals = self.tree.item(item,"values")
        if not vals: return None
        try: return int(vals[0])
        except (ValueError, TypeError): return None

    def editar_selecionado(self):
        reg_id = self.obter_id_selecionado()
        if reg_id is None:
            messagebox.showwarning("Aviso","Selecione um registro para editar."); return
        reg = self.db.obter_por_id(reg_id)
        if not reg:
            messagebox.showerror("Erro","Registro não encontrado."); return
        def cb(rid,tipo,nome,data,valor,moeda,cat,obs):
            if self.db.atualizar_registro(rid,tipo,nome,data,valor,moeda,cat,obs):
                self.atualizar_filtros_dinamicos()
                self._carregar_resumos()
                self.pesquisar()
                self._status(self.lbl_resultado,f"✔  Registro ID {rid} atualizado.","sucesso")
            else:
                messagebox.showerror("Erro","Não foi possível atualizar.")
        EditarRegistroDialog(self, reg, self.db.categorias_existentes(), self.tema, cb)

    def duplicar_selecionado(self):
        reg_id = self.obter_id_selecionado()
        if reg_id is None:
            messagebox.showwarning("Aviso","Selecione um registro para duplicar."); return
        reg = self.db.obter_por_id(reg_id)
        if not reg:
            messagebox.showerror("Erro","Registro não encontrado."); return
        # Preenche o formulário e muda para aba registrar
        self.mostrar_tela("registrar")
        self.cad_tipo_combo.set(reg["tipo"])
        self.cad_nome_entry.delete(0,tk.END)
        self.cad_nome_entry.insert(0, reg["nome"])
        self.cad_data_entry.delete(0,tk.END)
        self.cad_data_entry.insert(0, formatar_data_br(datetime.date.today()))
        self.cad_valor_entry.delete(0,tk.END)
        self.cad_valor_entry.insert(0, f"{reg['valor']:.2f}".replace(".",","))
        self.cad_moeda_combo.set(reg["moeda"])
        self.cad_categoria_combo.set(reg["categoria"])
        self.cad_obs_text.delete("1.0","end")
        self.cad_obs_text.insert("1.0", reg.get("observacao",""))
        self._status(self.cad_status,
                     f"Duplicando ID {reg_id} — ajuste os campos e salve.","info")

    def excluir_selecionado(self):
        reg_id = self.obter_id_selecionado()
        if reg_id is None:
            messagebox.showwarning("Aviso","Selecione um registro para excluir."); return
        reg = self.db.obter_por_id(reg_id)
        if not reg:
            messagebox.showerror("Erro","Registro não encontrado."); return
        if not messagebox.askyesno("Confirmar exclusão",
            f"Excluir o registro ID {reg_id}?\n\n"
            f"{reg['tipo']}  |  {reg['nome']}  |  "
            f"{formatar_valor(reg['valor'],reg['moeda'])}"):
            return
        if self.db.excluir_registro(reg_id):
            self.atualizar_filtros_dinamicos()
            self._carregar_resumos()
            self.pesquisar()
            self._status(self.lbl_resultado,f"✔  Registro ID {reg_id} excluído.","sucesso")
        else:
            messagebox.showerror("Erro","Não foi possível excluir.")

    def exportar_csv(self):
        regs = [r for r in self.resultados_atuais if r.get("id")]
        if not regs:
            messagebox.showwarning("Aviso","Não há registros para exportar."); return
        caminho = filedialog.asksaveasfilename(
            title="Salvar CSV", defaultextension=".csv",
            filetypes=[("CSV","*.csv")])
        if not caminho: return
        try:
            self.db.exportar_csv(caminho, regs)
            messagebox.showinfo("Sucesso",f"CSV exportado com {len(regs)} registros.")
        except Exception as e:
            messagebox.showerror("Erro",f"Falha ao exportar:\n{e}")

    def importar_csv(self):
        caminho = filedialog.askopenfilename(
            title="Selecionar CSV", filetypes=[("CSV","*.csv"),("Todos","*.*")])
        if not caminho: return
        ok, erros, msgs = self.db.importar_csv(caminho)
        self.atualizar_filtros_dinamicos()
        self._carregar_resumos()
        self.ver_todos()
        msg = f"Importação concluída:\n✔ {ok} registro(s) importado(s)\n✖ {erros} erro(s)"
        if msgs:
            msg += "\n\nDetalhes:\n" + "\n".join(msgs[:10])
            if len(msgs) > 10:
                msg += f"\n... e mais {len(msgs)-10} erros."
        if erros:
            messagebox.showwarning("Importação com erros", msg)
        else:
            messagebox.showinfo("Sucesso", msg)

    # ── Helpers de UI ─────────────────────────────────────────────────────────

    def _status(self, label, texto, tipo):
        cores = {"erro":self.tema["danger"],"sucesso":self.tema["success"],
                 "info":self.tema["muted"]}
        label.config(text=texto, foreground=cores.get(tipo,self.tema["muted"]))

    def _configurar_entry_data(self, entry):
        entry._ultimo_valido = entry.get()
        entry.bind("<KeyRelease>", lambda e, en=entry: self._fmt_data_auto(en))
        entry.bind("<FocusOut>",   lambda e, en=entry: self._validar_data(en))

    def _configurar_entry_valor(self, entry):
        entry.bind("<KeyRelease>", lambda e, en=entry: self._fmt_valor_auto(en))

    def _fmt_data_auto(self, entry):
        atual = entry.get()
        filtrado = somente_data(atual)
        if filtrado != atual:
            pos = entry.index(tk.INSERT)
            entry.delete(0,tk.END); entry.insert(0,filtrado)
            entry.icursor(min(pos,len(filtrado)))
        v = entry.get()
        if len(v) in (2,5) and not v.endswith("/"):
            entry.insert(tk.END,"/")

    def _validar_data(self, entry):
        c = entry.get().strip()
        if not c:
            entry._ultimo_valido = ""; return
        try:
            parse_data_br(c); entry._ultimo_valido = c
        except Exception:
            messagebox.showwarning("Data inválida","Use o formato dd/mm/aaaa.")
            entry.delete(0,tk.END)
            entry.insert(0, getattr(entry,"_ultimo_valido",""))

    def _fmt_valor_auto(self, entry):
        atual = entry.get()
        filtrado = somente_valor(atual)
        if filtrado == atual: return
        try: pos_antes = entry.index(tk.INSERT)
        except Exception: pos_antes = len(filtrado)
        chars_ok = len(somente_valor(atual[:pos_antes]))
        entry.delete(0,tk.END); entry.insert(0,filtrado)
        entry.icursor(min(chars_ok,len(filtrado)))

    def _tooltip_btn(self, parent, col, hint):
        """Adiciona tooltip simples a um botão na grade."""
        def show(event, btn):
            tip = tk.Toplevel(btn)
            tip.wm_overrideredirect(True)
            tip.wm_geometry(f"+{event.x_root+10}+{event.y_root-28}")
            tk.Label(tip, text=hint, bg=self.tema["tooltip_bg"],
                     fg=self.tema["tooltip_fg"], font=("Segoe UI",8),
                     padx=6, pady=3, relief="flat").pack()
            btn._tip = tip
        def hide(event, btn):
            if hasattr(btn,"_tip") and btn._tip:
                btn._tip.destroy(); btn._tip = None
        try:
            btn = parent.grid_slaves(row=0, column=col)[0]
            btn.bind("<Enter>", lambda e,b=btn: show(e,b))
            btn.bind("<Leave>", lambda e,b=btn: hide(e,b))
        except Exception:
            pass

    def _ao_fechar(self):
        realizar_backup_automatico(DB_FILE, self.config_app.get("max_backups",15))
        self.destroy()


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = App()
    app.mainloop()
