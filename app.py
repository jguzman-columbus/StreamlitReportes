# app.py — Portafolio Deuda (Oracle con SID, PWD por secrets/env)
# Ajustes mínimos: quitar HARDCODED_PWD y leer credenciales seguras
# Mantiene: Header oscuro + menús visibles (⋮ y Deploy) + sin pestaña "Exportar"

import io, re, math, os
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
import oracledb
from datetime import date

# =========================
#  CONFIG: ORACLE (secrets/env)
# =========================
HOST = st.secrets.get("ORACLE_HOST", os.getenv("ORACLE_HOST", "34.134.141.229"))
PORT = int(st.secrets.get("ORACLE_PORT", os.getenv("ORACLE_PORT", "1522")))
SID  = st.secrets.get("ORACLE_SID",  os.getenv("ORACLE_SID",  "DESA2"))
USER = st.secrets.get("ORACLE_USER", os.getenv("ORACLE_USER", "HUB_USER"))
PWD  = st.secrets.get("ORACLE_PWD",  os.getenv("ORACLE_PWD", ""))  # ← ya no hay HARDCODED_PWD

INFLACION_ANUAL = float(st.secrets.get("INFLACION_ANUAL", os.getenv("INFLACION_ANUAL", "0.035")))
DEFAULT_ALIAS   = st.secrets.get("DEFAULT_ALIAS", os.getenv("DEFAULT_ALIAS", "UNIB"))

# =========================
#  PAGE SETUP + Tema — CONTRASTE ALTO
# =========================
st.set_page_config(page_title="Portafolio Deuda — Oracle", page_icon=None, layout="wide")

def css_base_with_sidebar():
    return """
    <style>
    :root{
      --bg1:#0b1020; --bg2:#0f172a;
      --ink:#f9fafb; --ink-weak:#e5e7eb;
      --muted:#cbd5e1; --accent1:#60a5fa; --accent2:#22d3ee;
      --cardbg: rgba(255,255,255,.08); --cardbd: rgba(255,255,255,.22);
    }
    .stApp{
      color:var(--ink);
      background:
        radial-gradient(1200px 800px at 10% 0%, rgba(96,165,250,.12), transparent),
        radial-gradient(1200px 800px at 100% 10%, rgba(34,211,238,.10), transparent),
        linear-gradient(135deg, var(--bg1), var(--bg2));
    }
    [data-testid="stMarkdownContainer"], .stText, .stCaption, p, span, label, h1, h2, h3, h4, h5, h6,
    .st-emotion-cache, .stNumberInput, .stTextInput, .stSelectbox, .stMultiSelect, .stPlotlyChart {
      color: var(--ink) !important;
    }
    .stTabs [aria-selected="true"]{border-bottom-color:var(--accent1) !important; color:#fff !important}

    /* Header superior (antes blanco) */
    header[data-testid="stHeader"]{
      background:
        radial-gradient(800px 400px at 10% 0%, rgba(96,165,250,.15), transparent),
        radial-gradient(800px 400px at 90% 0%, rgba(34,211,238,.12), transparent),
        linear-gradient(180deg, #0c1327, #0f1a38);
      color:#f1f5f9 !important;
      border-bottom:1px solid rgba(255,255,255,.18);
    }
    header[data-testid="stHeader"] *{
      color:#f1f5f9 !important;
      fill:#f1f5f9 !important;
    }

    /* ======== Menú de 3 puntitos (Main menu) y popovers ======== */
    div[data-testid="stMainMenu"],
    section[aria-label="Main menu"],
    [role="menu"]{
      background:#0f1a38 !important;
      color:#f1f5f9 !important;
      border:1px solid rgba(255,255,255,.18) !important;
      box-shadow:0 12px 32px rgba(0,0,0,.45) !important;
    }
    [role="menu"] *{ color:#f1f5f9 !important; }
    [role="menu"] [role="menuitem"],
    [role="menu"] a,
    [role="menu"] button{
      background:transparent !important;
      color:#f1f5f9 !important;
    }
    [role="menu"] [role="menuitem"]:hover,
    [role="menu"] a:hover,
    [role="menu"] button:hover{
      background:rgba(255,255,255,.08) !important;
    }
    [role="menu"] hr{
      border:none !important;
      border-top:1px solid rgba(255,255,255,.18) !important;
    }

    /* ======== Botón/menú de Deploy (badge superior derecho) ======== */
    [data-testid="stStatusWidget"] *,
    [class*="viewerBadge_container"],
    [class*="viewerBadge_links"] *{
      color:#f1f5f9 !important;
      fill:#f1f5f9 !important;
    }
    [role="tooltip"],
    [data-testid="stTooltip"]{
      background:#0f1a38 !important;
      color:#f1f5f9 !important;
      border:1px solid rgba(255,255,255,.18) !important;
      box-shadow:0 12px 32px rgba(0,0,0,.45) !important;
    }
    button[data-testid="baseButton-header"],
    button[data-testid="baseButton-headerNoPadding"],
    header [role="button"]{
      color:#f1f5f9 !important;
      fill:#f1f5f9 !important;
    }

    /* Dataframe headers/body más legibles */
    .dataframe thead tr th{background:rgba(124,58,237,.30); color:#f1f5f9; border:0}
    .dataframe tbody tr{background:rgba(255,255,255,.04); color:#e5e7eb}

    /* Sidebar con contraste */
    section[data-testid="stSidebar"]{
      color: var(--ink);
      background:
        radial-gradient(600px 320px at 30% 0%, rgba(96,165,250,.18), transparent),
        radial-gradient(600px 320px at 90% 0%, rgba(34,211,238,.15), transparent),
        linear-gradient(180deg, #0c1327, #0f1a38);
      border-right: 1px solid rgba(255,255,255,.18);
    }
    .sb-card{
      background: var(--cardbg);
      border:1px solid var(--cardbd);
      border-radius: 14px; padding: 12px 12px; margin: 8px 0;
      box-shadow: 0 10px 30px rgba(0,0,0,.40);
    }
    .sb-title{font-size:.9rem;color:#ffffff;letter-spacing:.06em;text-transform:uppercase;margin-bottom:6px}

    /* Chips de encabezado */
    .chip{
      display:inline-block; padding:.28rem .60rem; border-radius:999px; margin:2px 6px 8px 0;
      background:linear-gradient(90deg, rgba(124,58,237,.28), rgba(34,211,238,.22));
      border:1px solid rgba(124,58,237,.45); font-size:.9rem; color:#ffffff;
      text-shadow:0 1px 2px rgba(0,0,0,.35);
    }

    /* Listas tipo ranking (no tabulares) para Asset */
    .rank-section{ margin-top:12px; }
    .rank-title{ font-weight:800; margin-bottom:8px; color:#ffffff; }
    .rank-list{ list-style: none; padding-left:0; margin:0; }
    .rank-item{
      display:flex; justify-content:space-between; align-items:center;
      background:rgba(255,255,255,.10); border:1px solid rgba(255,255,255,.22);
      border-radius:12px; padding:10px 12px; margin-bottom:8px;
    }
    .rank-left{ display:flex; gap:10px; align-items:center; }
    .rank-badge{
      width:26px; height:26px; border-radius:999px; display:inline-flex; align-items:center; justify-content:center;
      background:linear-gradient(135deg, rgba(96,165,250,.38), rgba(34,211,238,.32));
      border:1px solid rgba(255,255,255,.28); font-weight:800; color:#0b1020;
    }
    .rank-name{ font-weight:800; color:#ffffff; }
    .rank-right{ font-variant-numeric: tabular-nums; color:#f1f5f9; }

    /* Tarjetas resumen deuda */
    .kpi-grid{display:grid; grid-template-columns: repeat(5, minmax(0,1fr)); gap:12px; margin: 6px 0 8px 0;}
    .kpi-card{
      background: linear-gradient(180deg, rgba(34,197,94,.20), rgba(2,6,23,.12)); /* base legible */
      border:1px solid rgba(34,197,94,.45);
      border-radius: 14px; padding: 12px 14px;
      box-shadow: 0 10px 28px rgba(0,0,0,.35);
    }
    .kpi-card:nth-child(2){ background:linear-gradient(180deg, rgba(59,130,246,.20), rgba(2,6,23,.12)); border-color:rgba(59,130,246,.45);}
    .kpi-card:nth-child(3){ background:linear-gradient(180deg, rgba(234,179,8,.22), rgba(2,6,23,.12)); border-color:rgba(234,179,8,.48);}
    .kpi-card:nth-child(4){ background:linear-gradient(180deg, rgba(236,72,153,.22), rgba(2,6,23,.12)); border-color:rgba(236,72,153,.48);}
    .kpi-card:nth-child(5){ background:linear-gradient(180deg, rgba(6,182,212,.22), rgba(2,6,23,.12)); border-color:rgba(6,182,212,.48);}
    .kpi-label{ font-size:.78rem; color:#e2e8f0; letter-spacing:.06em; text-transform:uppercase }
    .kpi-value{ font-size:1.45rem; font-weight:900; color:#ffffff; margin-top:4px }

    @media (max-width:1200px){
      .kpi-grid{ grid-template-columns: repeat(2, minmax(0,1fr)); }
    }
    @media (max-width:800px){
      .kpi-grid{ grid-template-columns: repeat(1, minmax(0,1fr)); }
    }
    </style>
    """
st.markdown(css_base_with_sidebar(), unsafe_allow_html=True)

# =========================
#  Sidebar (solo estilo)
# =========================
with st.sidebar:
    st.markdown('<div class="sb-card"><div class="sb-title">Parámetros</div>', unsafe_allow_html=True)
    ALIAS_CDM = st.text_input("Cliente (ALIAS_CDM)", value=DEFAULT_ALIAS)
    hoy = date.today()
    coly, colm = st.columns(2)
    with coly:
        y = st.number_input("Año", 2000, 2100, hoy.year, step=1)
    with colm:
        m = st.number_input("Mes", 1, 12, hoy.month, step=1)
    st.caption("Conexión por SID (igual que Colab). PWD segura por secrets/env.")
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="sb-card"><div class="sb-title">Filtros Deuda</div>', unsafe_allow_html=True)
    st.caption("Aplican solo a la pestaña Deuda (ID_CLIENTE / ID_PRODUCTO).")

# =========================
#  Fechas
# =========================
F_DIA_INI = pd.Timestamp(year=y, month=m, day=1)
F_DIA_FIN = F_DIA_INI + pd.offsets.MonthEnd(1)
F_DIA_FIN_NEXT = F_DIA_FIN + pd.Timedelta(days=1)
FECHA_ESTADISTICA = F_DIA_FIN.strftime("%Y-%m-%d")

# =========================
#  Conexión (SID + PWD desde secrets/env)
# =========================
def get_conn():
    if not PWD:
        raise RuntimeError("Falta ORACLE_PWD en secrets o variable de entorno.")
    dsn = oracledb.makedsn(HOST, PORT, sid=SID)
    oracledb.defaults.arraysize = 1000
    oracledb.defaults.prefetchrows = 1000
    return oracledb.connect(user=USER, password=PWD, dsn=dsn)

@st.cache_data(show_spinner=True)
def run_sql(sql: str, params: dict | None = None) -> pd.DataFrame:
    conn = get_conn()
    return pd.read_sql(sql, conn, params=params or {})

# =========================
#  Helpers
# =========================
def sanitize_int_list(lst):
    if lst is None: return []
    safe = []
    for x in lst:
        try:
            safe.append(int(str(x).strip()))
        except:
            pass
    return sorted(set(safe))

def sql_in_clause(colname: str, ints: list[int]) -> str:
    return "" if not ints else f"{colname} IN ({','.join(str(i) for i in ints)})"

def parse_pct_col(s):
    if isinstance(s, (int, float, np.number)): return float(s)
    if s is None or (isinstance(s, float) and math.isnan(s)): return np.nan
    x = str(s).strip().replace('%','').replace(' ',''); x = x.replace(',', '.') if (x.count(',')==1 and x.count('.')==0) else x
    try: return float(x)
    except: return np.nan

def parse_money_to_float(s):
    if isinstance(s, (int, float, np.number)): return float(s)
    if s is None or (isinstance(s, float) and math.isnan(s)): return 0.0
    x = str(s).strip().replace('$','').replace(',','').replace(' ', '').replace('−','-')
    try: return float(x)
    except: return 0.0

# =========================
#  Catálogos: Clientes y Productos (SOLO Deuda) — DISTINCT
# =========================
@st.cache_data(show_spinner=True)
def fetch_clientes(alias: str) -> pd.DataFrame:
    q = """
    SELECT DISTINCT c.ID_CLIENTE
    FROM SIAPII.V_M_CONTRATO_CDM c
    WHERE c.ALIAS_CDM = :alias
    ORDER BY c.ID_CLIENTE
    """
    df = run_sql(q, {"alias": alias})
    if df.empty:
        return pd.DataFrame(columns=["ID_CLIENTE", "ETIQUETA"])
    df["ETIQUETA"] = df["ID_CLIENTE"].apply(lambda x: f"Cliente {int(x)}")
    return df[["ID_CLIENTE","ETIQUETA"]]

@st.cache_data(show_spinner=True)
def fetch_productos_desde_his(alias: str, sel_id_clientes: list[int],
                              f_ini: pd.Timestamp, f_fin_next: pd.Timestamp,
                              fecha_estadistica: str) -> pd.DataFrame:
    if not sel_id_clientes:
        q_all = "SELECT DISTINCT ID_CLIENTE FROM SIAPII.V_M_CONTRATO_CDM WHERE ALIAS_CDM = :alias"
        df_all = run_sql(q_all, {"alias": alias})
        sel_id_clientes = sanitize_int_list(df_all["ID_CLIENTE"].tolist())

    id_cli_clause = sql_in_clause("h.ID_CLIENTE", sel_id_clientes)
    where_cli_h = (" AND " + id_cli_clause) if id_cli_clause else ""

    sql = f"""
    WITH PROD_HIS AS (
      SELECT DISTINCT h.ID_PRODUCTO
      FROM SIAPII.V_HIS_POSICION_CLIENTE h
      WHERE TRUNC(h.REGISTRO_CONTROL) >= TO_DATE(:f_ini,'YYYY-MM-DD')
        AND TRUNC(h.REGISTRO_CONTROL) <  TO_DATE(:f_fin,'YYYY-MM-DD')
        {where_cli_h}
    ),
    PRED AS (
      SELECT
        e.ID_PRODUCTO,
        e.ID_TIPO_ACTIVO,
        SUM(e.POSICION_TOTAL) AS MONTO,
        ROW_NUMBER() OVER (PARTITION BY e.ID_PRODUCTO ORDER BY SUM(e.POSICION_TOTAL) DESC NULLS LAST) AS RN
      FROM SIAPII.V_CLIENTE_ESTADISTICAS e
      JOIN SIAPII.V_M_CONTRATO_CDM c
        ON c.ID_CLIENTE = e.ID_CLIENTE
      WHERE c.ALIAS_CDM = :alias
        AND TRUNC(e.FECHA_ESTADISTICA) = TO_DATE(:fecha_est,'YYYY-MM-DD')
        {'AND ' + sql_in_clause('e.ID_CLIENTE', sel_id_clientes) if sel_id_clientes else ''}
      GROUP BY e.ID_PRODUCTO, e.ID_TIPO_ACTIVO
    )
    SELECT DISTINCT
      ph.ID_PRODUCTO,
      COALESCE(p.DESCRIPCION, 'SIN_DESCRIPCION') AS DESCRIPCION,
      CASE pred.ID_TIPO_ACTIVO
        WHEN 0 THEN 'No aplica'
        WHEN 1 THEN 'Deuda'
        WHEN 2 THEN 'Renta Variable'
        WHEN 3 THEN 'Notas Estructuradas'
        WHEN 4 THEN 'Alternativo'
        WHEN 5 THEN 'Productos'
        WHEN 6 THEN 'Todos los Activos'
        WHEN 7 THEN 'Derivados'
        ELSE 'Desconocido'
      END AS ACTIVO
    FROM PROD_HIS ph
    LEFT JOIN SIAPII.V_M_PRODUCTO p ON p.ID_PRODUCTO = ph.ID_PRODUCTO
    LEFT JOIN PRED pred ON pred.ID_PRODUCTO = ph.ID_PRODUCTO AND pred.RN = 1
    ORDER BY 2
    """
    params = {
        "alias": alias,
        "f_ini": f_ini.strftime("%Y-%m-%d"),
        "f_fin": f_fin_next.strftime("%Y-%m-%d"),
        "fecha_est": fecha_estadistica
    }
    df = run_sql(sql, params)
    df = df.drop_duplicates(subset=["ID_PRODUCTO"]).reset_index(drop=True)
    return df

# =========================
#  WHERE dinámico SOLO para Deuda
# =========================
def where_filters_for_his(alias: str, id_clientes: list[int], productos: list[int]) -> str:
    parts = ["c.ALIAS_CDM = :alias_up", "c.ID_CLIENTE = h.ID_CLIENTE"]
    if id_clientes:
        parts.append(sql_in_clause("h.ID_CLIENTE", sanitize_int_list(id_clientes)))
    if productos:
        parts.append(sql_in_clause("h.ID_PRODUCTO", sanitize_int_list(productos)))
    return "WHERE EXISTS ( SELECT 1 FROM SIAPII.V_M_CONTRATO_CDM c WHERE " + " AND ".join(parts) + " )"

# =========================
#  Queries
# =========================
CASE_ACTIVO = """
  CASE e.ID_TIPO_ACTIVO
    WHEN 0 THEN 'No aplica'
    WHEN 1 THEN 'Deuda'
    WHEN 2 THEN 'Renta Variable'
    WHEN 3 THEN 'Notas Estructuradas'
    WHEN 4 THEN 'Alternativo'
    WHEN 5 THEN 'Productos'
    WHEN 6 THEN 'Todos los Activos'
    WHEN 7 THEN 'Derivados'
    ELSE 'Desconocido'
  END
"""

def build_query_base_unfiltered(alias: str, fecha: str) -> str:
    return f"""
    SELECT
      COALESCE(p.DESCRIPCION, 'SIN_DESCRIPCION') AS PRODUCTO,
      {CASE_ACTIVO} AS ACTIVO,
      SUM(e.POSICION_TOTAL) AS MONTO
    FROM SIAPII.V_CLIENTE_ESTADISTICAS e
    LEFT JOIN SIAPII.V_M_PRODUCTO p ON p.ID_PRODUCTO = e.ID_PRODUCTO
    WHERE e.ALIAS_CDM = :alias
      AND TRUNC(e.FECHA_ESTADISTICA) = TO_DATE(:fecha, 'YYYY-MM-DD')
    GROUP BY COALESCE(p.DESCRIPCION, 'SIN_DESCRIPCION'), {CASE_ACTIVO}
    """

FALLBACK_IDS = [37, 3]  # 37=TIIE Fondeo, 3=CETES 182
ids_csv = ",".join(str(i) for i in FALLBACK_IDS)

DTYPE_Q = """
SELECT DATA_TYPE
FROM ALL_TAB_COLUMNS
WHERE OWNER = 'SIAPII'
  AND TABLE_NAME = 'V_TASAS_REFERENCIA'
  AND COLUMN_NAME = 'FECHA'
"""

@st.cache_data(show_spinner=True)
def build_snapshot_params(alias: str, f_ini: pd.Timestamp, f_fin_next: pd.Timestamp):
    params = {"alias_up": alias, "f_ini_dt": f_ini.strftime("%Y-%m-%d"), "f_fin_dt": f_fin_next.strftime("%Y-%m-%d")}
    dt = run_sql(DTYPE_Q).DATA_TYPE.iloc[0].strip().upper()
    if dt in ("DATE","TIMESTAMP","TIMESTAMP(6)","TIMESTAMP WITH TIME ZONE","TIMESTAMP WITH LOCAL TIME ZONE"):
        date_expr = "TRUNC(CAST(r.FECHA AS DATE))"
    else:
        date_expr = (
            "CASE\n"
            "  WHEN REGEXP_LIKE(r.FECHA,'^[0-9]{4}-[0-9]{2}-[0-9]{2}') THEN TRUNC(TO_DATE(SUBSTR(r.FECHA,1,10),'YYYY-MM-DD'))\n"
            "  WHEN REGEXP_LIKE(r.FECHA,'^[0-9]{2}/[0-9]{2}/[0-9]{4}') THEN TRUNC(TO_DATE(SUBSTR(r.FECHA,1,10),'DD/MM/YYYY'))\n"
            "  ELSE NULL\nEND"
        )
    return params, date_expr

@st.cache_data(show_spinner=True)
def query_snapshot(alias: str, f_ini: pd.Timestamp, f_fin_next: pd.Timestamp,
                   id_clientes: list[int], productos: list[int]) -> pd.DataFrame:
    params, DATE_EXPR = build_snapshot_params(alias, f_ini, f_fin_next)
    where_exists = where_filters_for_his(alias, id_clientes, productos)

    SQL_SNAPSHOT = f"""
WITH FECHA_C AS (
  SELECT MAX(TRUNC(h1.REGISTRO_CONTROL)) AS FECHA_CORTE
  FROM SIAPII.V_HIS_POSICION_CLIENTE h1
  WHERE TRUNC(h1.REGISTRO_CONTROL) >= TO_DATE(:f_ini_dt,'YYYY-MM-DD')
    AND TRUNC(h1.REGISTRO_CONTROL) <  TO_DATE(:f_fin_dt,'YYYY-MM-DD')
    AND EXISTS (
      SELECT 1 FROM SIAPII.V_M_CONTRATO_CDM c1
      WHERE c1.ALIAS_CDM = :alias_up
        AND c1.ID_CLIENTE = h1.ID_CLIENTE
    )
),
H_CORTE AS (
  SELECT h.*
  FROM SIAPII.V_HIS_POSICION_CLIENTE h
  JOIN FECHA_C fc ON TRUNC(h.REGISTRO_CONTROL) = fc.FECHA_CORTE
  {where_exists}
),
VTR_NORM AS (
  SELECT r.ID_TASA_REFERENCIA, r.TASA_REFERENCIA, r.TASA,
         {DATE_EXPR} AS FECHA_TRUNC
  FROM SIAPII.V_TASAS_REFERENCIA r
),
VTR_EXACT AS (
  SELECT v.ID_TASA_REFERENCIA, v.TASA, v.TASA_REFERENCIA
  FROM VTR_NORM v
  CROSS JOIN FECHA_C fc
  WHERE v.FECHA_TRUNC = fc.FECHA_CORTE
),
VTR_FALL AS (
  SELECT x.ID_TASA_REFERENCIA, x.TASA, x.TASA_REFERENCIA
  FROM (
    SELECT v.ID_TASA_REFERENCIA, v.TASA, v.TASA_REFERENCIA, v.FECHA_TRUNC,
           ROW_NUMBER() OVER (PARTITION BY v.ID_TASA_REFERENCIA ORDER BY v.FECHA_TRUNC DESC) AS RN
    FROM VTR_NORM v
    CROSS JOIN FECHA_C fc
    WHERE v.ID_TASA_REFERENCIA IN ({ids_csv})
      AND v.FECHA_TRUNC IS NOT NULL
      AND v.FECHA_TRUNC <= fc.FECHA_CORTE
  ) x
  WHERE x.RN = 1
),
VTR_REF AS (
  SELECT e.ID_TASA_REFERENCIA, e.TASA, e.TASA_REFERENCIA
  FROM VTR_EXACT e
  UNION ALL
  SELECT f.ID_TASA_REFERENCIA, f.TASA, f.TASA_REFERENCIA
  FROM VTR_FALL f
  WHERE NOT EXISTS (
    SELECT 1 FROM VTR_EXACT e WHERE e.ID_TASA_REFERENCIA = f.ID_TASA_REFERENCIA
  )
)
SELECT
    h.ID_PRODUCTO,
    e.ID_EMISORA,
    MAX(e.NOMBRE_EMISORA)           AS NOMBRE_EMISORA,
    MAX(e.TIPO_PAPEL)               AS TIPO_PAPEL,
    MAX(e.TIPO_INSTRUMENTO)         AS TIPO_INSTRUMENTO,
    MAX(e.PLAZO_CUPON)              AS PLAZO_CUPON,
    MAX(e.FECHA_VTO_EM)             AS FECHA_VTO_EM,
    MAX(e.ID_TASA_REFERENCIA)       AS ID_TASA_REFERENCIA,
    MAX(e.ID_DIVISA_TV)             AS ID_DIVISA_TV,
    MAX(h.CALIFICACION_HOMOLOGADA)  AS CALIFICACION_HOMOLOGADA,
    MAX(h.EMIS_TASA)                AS EMIS_TASA,
    SUM(h.VALOR_NOMINAL)            AS VALOR_NOMINAL,
    SUM(h.VALOR_REAL)               AS VALOR_REAL,
    CASE WHEN SUM(h.VALOR_REAL) IS NULL OR SUM(h.VALOR_REAL)=0 THEN NULL
         ELSE SUM(NVL(h.PLAZO_REPORTO,0) * h.VALOR_REAL) / SUM(h.VALOR_REAL)
    END                             AS DURACION_DIAS,
    TRUNC(MAX(e.FECHA_VTO_EM)) - TRUNC(MAX(h.REGISTRO_CONTROL)) AS DIAS_X_V,
    MAX(TRUNC(h.REGISTRO_CONTROL)) AS FECHA_CORTE,
    MAX(vtr.TASA)                   AS TASA_BASE,
    MAX(vtr.TASA_REFERENCIA)        AS TASA_REF_NAME
FROM H_CORTE h
LEFT JOIN SIAPII.V_M_EMISORA e
       ON e.ID_EMISORA = h.ID_EMISORA
LEFT JOIN VTR_REF vtr
       ON vtr.ID_TASA_REFERENCIA = e.ID_TASA_REFERENCIA
GROUP BY
  h.ID_PRODUCTO,
  e.ID_EMISORA
ORDER BY
  SUM(h.VALOR_REAL) DESC NULLS LAST,
  MAX(e.NOMBRE_EMISORA)
"""
    return run_sql(SQL_SNAPSHOT, params=params)

# =========================
#  Cálculos y helpers
# =========================
K = 360.0 / 365.0
def parse_rate_any(x):
    if pd.isna(x): return np.nan
    s = str(x).strip().replace('%','').replace(' ','')
    if s.count(',') == 1 and s.count('.') == 0: s = s.replace(',', '.')
    s = re.sub(r'(?<=\d),(?=\d{3}\b)', '', s)
    try: return float(s)
    except: return np.nan
def auto_to_decimal(series):
    vals = pd.to_numeric(series, errors='coerce'); med = vals.dropna().median()
    return vals if (pd.notna(med) and 0 < med < 1) else vals * 0.01
def fmt_pct(x):    return "—" if pd.isna(x) else f"{x*100:.2f}%"
def fmt_money0(x): return f"{x:,.0f}"
def fmt_money2(x): return f"${x:,.2f}"
def eq365(rate_dec, cap_series):
    base = 1.0 + (rate_dec / cap_series.replace(0, np.nan))
    base = pd.Series(base, index=cap_series.index).fillna(1.0)
    return (base.pow(cap_series / K) - 1.0) * K

@st.cache_data(show_spinner=True)
def build_df_final(df_snap: pd.DataFrame, inflacion_anual: float) -> pd.DataFrame:
    if df_snap is None or df_snap.empty:
        raise ValueError("No hay datos de Deuda para el periodo/alias/filtrado seleccionado.")
    df = df_snap.copy()
    ytm_dec   = auto_to_decimal(df['EMIS_TASA'].apply(parse_rate_any))
    tbase_dec = auto_to_decimal(df.get('TASA_BASE', pd.Series([np.nan]*len(df))).apply(parse_rate_any))
    f_vto = pd.to_datetime(df['FECHA_VTO_EM'], errors='coerce')
    f_corte = pd.to_datetime(df['FECHA_CORTE'], errors='coerce')
    dxv_bruto = (f_vto - f_corte).dt.days
    is_reporto = df['TIPO_PAPEL'].astype(str).str.contains('reporto', case=False, na=False) | \
                 df['TIPO_INSTRUMENTO'].astype(str).str.contains('reporto', case=False, na=False)
    is_cero = df['TIPO_INSTRUMENTO'].astype(str).str.contains('cero', case=False, na=False)
    dxv_mostrado = pd.Series(np.where(is_reporto, 1, dxv_bruto), index=df.index)
    plazo = pd.to_numeric(df['PLAZO_CUPON'], errors='coerce')
    dxv_sql = pd.to_numeric(df.get('DIAS_X_V', np.nan), errors='coerce')
    dxv_real = dxv_sql.where(dxv_sql.notna(), dxv_bruto)
    periodo_dias = pd.Series(np.where(is_reporto, 1,
                                      np.where(is_cero & dxv_real.notna() & (dxv_real > 0), dxv_real, plazo)),
                             index=df.index).fillna(28).clip(lower=1)
    cap = 360.0 / periodo_dias
    infl = float(inflacion_anual)
    es_real = (df['TIPO_INSTRUMENTO'].astype(str).str.contains('tasa real', case=False, na=False)) & \
              (pd.to_numeric(df['ID_DIVISA_TV'], errors='coerce') == 8)
    es_revisable = df['TIPO_INSTRUMENTO'].astype(str).str.contains('revis', case=False, na=False)
    mask_nominal = ~(es_real | es_revisable)
    t_eq_nominal   = eq365(ytm_dec, cap)
    t_in_revisable = tbase_dec.fillna(0.0) + ytm_dec.fillna(0.0)
    t_eq_revisable = eq365(t_in_revisable, cap)
    t_eq_real      = eq365(ytm_dec, cap)
    t_nom_real     = ((1.0 + (t_eq_real / K)) * (1.0 + (infl / K)) - 1.0) * K
    t_carry = pd.Series(np.nan, index=df.index, dtype=float)
    t_carry[mask_nominal] = t_eq_nominal[mask_nominal]
    t_carry[es_revisable] = t_eq_revisable[es_revisable]
    t_carry[es_real]      = t_nom_real[es_real]
    val_real = pd.to_numeric(df['VALOR_REAL'], errors='coerce').fillna(0.0)
    peso = (val_real / val_real.sum()) if val_real.sum() > 0 else pd.Series(0.0, index=df.index)
    val_nom_raw = pd.to_numeric(df['VALOR_NOMINAL'], errors='coerce').fillna(0.0) * 100.0
    val_nom_raw = np.where(is_reporto, 0.0, val_nom_raw)
    carry_total_pp = float((t_carry * peso).sum() * 100.0)
    dxv_total_pond = float((dxv_mostrado.fillna(0.0) * peso).sum())
    duracion_dias  = pd.to_numeric(df.get('DURACION_DIAS', np.nan), errors='coerce')
    dur_portafolio = float((duracion_dias.fillna(0.0) * peso).sum()) if 'DURACION_DIAS' in df else None

    df_final = pd.DataFrame({
        'Tipo de Papel'       : df['TIPO_PAPEL'].astype(str),
        'Tipo de instrumento' : df['TIPO_INSTRUMENTO'].astype(str),
        'Instrumento'         : df['NOMBRE_EMISORA'].astype(str),
        'Fecha vto'           : f_vto.dt.date,
        'DxV'                 : dxv_mostrado,
        'Duración (días)'     : (pd.to_numeric(duracion_dias, errors='coerce').round(0).astype('Int64')
                                  if 'DURACION_DIAS' in df else pd.Series([pd.NA]*len(df))),
        'Tasa valuacion'      : [fmt_pct(x) for x in ytm_dec],
        'Carry (365 d)'       : [fmt_pct(x) for x in t_carry],
        'Valor Nominal'       : [fmt_money0(v) for v in val_nom_raw],
        'Monto'               : val_real.map(fmt_money2),
        '% Cartera'           : (peso * 100).map(lambda x: f"{x:.2f}%"),
        'Tasa ref'            : df.get('TASA_REF_NAME', pd.Series(['']*len(df))).astype(str),
        'Tasa base'           : df.get('TASA_BASE', pd.Series([np.nan]*len(df))),
        'Calificación'        : df['CALIFICACION_HOMOLOGADA'].astype(str),
    })
    # Orden del detalle; TOTAL al final
    ord_tp = {'Reporto':1,'Gubernamental':2,'CuasiGuber':3,'Banca Comercial':4,'Privado':5}
    is_rep = df_final['Tipo de Papel'].str.contains('reporto', case=False, na=False) | \
             df_final['Tipo de instrumento'].str.contains('reporto', case=False, na=False)
    df_final['__ord__'] = np.where(is_rep, 1, df_final['Tipo de Papel'].map(ord_tp).fillna(98))
    df_final['__m__']   = df['VALOR_REAL'].fillna(0.0)
    df_detail = (df_final
                 .sort_values(['__ord__','__m__'], ascending=[True, False])
                 .drop(columns=['__ord__','__m__'])
                 .reset_index(drop=True))
    row_total = {
        'Tipo de Papel':'','Tipo de instrumento':'','Instrumento':'TOTAL','Fecha vto':'',
        'DxV':f"{dxv_total_pond:.0f}", 'Duración (días)':(f"{dur_portafolio:.0f}" if dur_portafolio is not None else ''),
        'Tasa valuacion':'', 'Carry (365 d)':f"{carry_total_pp:.2f}%",
        'Valor Nominal':'', 'Monto':f"${float(val_real.sum()):,.2f}",
        '% Cartera':"100.00%", 'Tasa ref':'', 'Tasa base':'', 'Calificación':''
    }
    return pd.concat([df_detail, pd.DataFrame([row_total])], ignore_index=True)

# =========================
#  Visual helpers
# =========================
def barh_percent_figure(series_pct: pd.Series, title: str) -> go.Figure:
    serie_ord = series_pct.sort_values(ascending=True)
    labels = serie_ord.index.astype(str).tolist(); vals = serie_ord.values
    xmax = max(20, int(math.ceil(np.nanmax(vals) / 20.0) * 20)) if len(vals) else 20
    fig = go.Figure()
    fig.add_trace(go.Bar(x=vals, y=labels, orientation='h',
                         marker=dict(color=vals, colorscale='Blues', showscale=False),
                         hovertemplate='%{y}: %{x:.2f}%<extra></extra>'))
    fig.update_layout(title=title,
        xaxis=dict(range=[0, xmax], tickmode='linear', dtick=20, title='% cartera', gridcolor='rgba(255,255,255,.22)'),
        yaxis=dict(title=''), margin=dict(l=10, r=10, t=40, b=10),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(255,255,255,.05)', font=dict(color='#f9fafb'), height=420)
    for y, v in zip(labels, vals):
        fig.add_annotation(x=v + xmax*0.01, y=y, text=f"{v:.2f}%", showarrow=False,
                           font=dict(size=12, color='#e2e8f0'), xanchor='left', yanchor='middle')
    return fig

def donut_figure(labels, values, title: str) -> go.Figure:
    if len(values) == 0 or float(np.nansum(values)) <= 0:
        labels, values = ["Sin datos"], [1]
    fig = go.Figure(data=[go.Pie(labels=list(labels), values=list(values), hole=.55, textinfo="percent",
                                 hoverinfo="label+percent+value")])
    fig.update_layout(title=title, showlegend=True,
        legend=dict(orientation="v", yanchor="top", y=1.0, xanchor="left", x=1.02, font=dict(color="#f1f5f9")),
        margin=dict(l=10, r=10, t=40, b=10),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(255,255,255,.05)", font=dict(color="#f9fafb"), height=440)
    return fig

def _interp_rgb(c1, c2, t):
    return tuple(int(round(a + (b - a) * t)) for a, b in zip(c1, c2))
def _hex_to_rgb(h): h=h.lstrip('#'); return tuple(int(h[i:i+2],16) for i in (0,2,4))
def _rgb_to_hex(rgb): return '#%02x%02x%02x' % rgb

def gradient_gyr(n:int):
    g = _hex_to_rgb("#22c55e")
    y = _hex_to_rgb("#fde047")
    r = _hex_to_rgb("#ef4444")
    if n <= 1:
        return ["#22c55e"]
    colors = []
    for i in range(n):
        t = i/(n-1)
        if t <= 0.5:
            tt = t/0.5
            rgb = _interp_rgb(g, y, tt)
        else:
            tt = (t-0.5)/0.5
            rgb = _interp_rgb(y, r, tt)
        colors.append(_rgb_to_hex(rgb))
    return colors

def risk_table_semaforo(r_df: pd.DataFrame, title: str = "Riesgo por Calificación (semáforo)") -> go.Figure:
    fig = go.Figure()
    escala_orden = ["AAA","AA+","AA","AA-","A+","A","A-",
                    "BBB+","BBB","BBB-","BB+","BB","BB-",
                    "B+","B","B-","CCC","CC","C","SD","D","NR"]
    r = r_df.copy()
    if r.empty:
        fig.update_layout(title=title, paper_bgcolor='rgba(0,0,0,0)', font=dict(color='#f9fafb'))
        return fig
    r['__ord__'] = r['Escala'].apply(lambda c: escala_orden.index(c) if c in escala_orden else len(escala_orden))
    r = r.sort_values(['__ord__','Escala']).drop(columns='__ord__').reset_index(drop=True)

    n = len(r)
    row_colors = gradient_gyr(n)
    fill_colors = [row_colors, row_colors]

    fig.add_trace(go.Table(
        header=dict(values=["Escala", "% Cartera"],
                    fill_color="rgba(255,255,255,0.10)", line_color="rgba(255,255,255,0.18)",
                    font=dict(color="#ffffff", size=12), align="center"),
        cells=dict(values=[r['Escala'], r['Pct'].map(lambda x: f"{float(x):.2f}%")],
                   fill_color=fill_colors,
                   line_color="rgba(0,0,0,0)",
                   font=dict(color="#0b1020", size=12),
                   align="center", height=28)
    ))
    fig.update_layout(
        title=title, margin=dict(l=10,r=10,t=40,b=10),
        paper_bgcolor='rgba(0,0,0,0)', font=dict(color='#f9fafb'),
        height=min(720, 140 + 28*max(4, len(r)))
    )
    return fig

# =========================
#  PIPELINE
# =========================
with st.spinner("Consultando Oracle y construyendo vistas..."):
    # --- Asset Allocation (SIN filtros de cliente/producto) ---
    QUERY_BASE_AA = build_query_base_unfiltered(ALIAS_CDM, FECHA_ESTADISTICA)
    base = run_sql(QUERY_BASE_AA, params={"alias": ALIAS_CDM, "fecha": FECHA_ESTADISTICA})
    base_proc = base.copy()
    if not base_proc.empty:
        base_proc["MONTO"] = pd.to_numeric(base_proc["MONTO"], errors="coerce").fillna(0.0)
        total_base = float(base_proc["MONTO"].sum())
        by_activo = (base_proc.groupby("ACTIVO", dropna=False)["MONTO"].sum().sort_values(ascending=False))
        by_producto = (base_proc.groupby("PRODUCTO", dropna=False)["MONTO"].sum().sort_values(ascending=False))
        df_aa_activo = (by_activo.reset_index()
                        .rename(columns={"MONTO":"Monto"})
                        .assign(Porcentaje=lambda d: (d["Monto"]/d["Monto"].sum()*100).round(2)))
        df_aa_producto = (by_producto.reset_index()
                          .rename(columns={"MONTO":"Monto"})
                          .assign(Porcentaje=lambda d: (d["Monto"]/d["Monto"].sum()*100).round(2)))
    else:
        by_activo = by_producto = pd.Series(dtype=float)
        total_base = 0.0
        df_aa_activo = pd.DataFrame(columns=["ACTIVO","Monto","Porcentaje"])
        df_aa_producto = pd.DataFrame(columns=["PRODUCTO","Monto","Porcentaje"])

    # --- Filtros Deuda (sidebar) ---
    df_cli = fetch_clientes(ALIAS_CDM)
    if df_cli.empty:
        sel_id_clientes = []
        opts_cli = []
    else:
        opts_cli = df_cli.apply(lambda r: f"{int(r.ID_CLIENTE)} — {r.ETIQUETA}", axis=1).tolist()
        id_map = {opt:int(df_cli.ID_CLIENTE.iloc[i]) for i,opt in enumerate(opts_cli)}
        sel_opts = st.sidebar.multiselect("Cliente(s) (ID_CLIENTE) — SOLO Deuda", opts_cli, default=opts_cli)
        sel_id_clientes = [id_map[o] for o in sel_opts]

    df_prod = fetch_productos_desde_his(ALIAS_CDM, sel_id_clientes, F_DIA_INI, F_DIA_FIN_NEXT, FECHA_ESTADISTICA)
    st.sidebar.markdown("**Producto(s) — SOLO Deuda**")
    if df_prod.empty:
        st.sidebar.warning("No se detectaron productos para los ID_CLIENTE seleccionados (en el mes). Puedes ingresar IDs manuales.")
        sel_prod_ids = []
    else:
        prod_options = df_prod.apply(
            lambda r: f"{int(r.ID_PRODUCTO)} — {r.DESCRIPCION} ({r.ACTIVO})", axis=1
        ).tolist()
        prod_id_map = {opt:int(df_prod.ID_PRODUCTO.iloc[i]) for i,opt in enumerate(prod_options)}
        sel_prod_opts = st.sidebar.multiselect("Selecciona producto(s)", prod_options, default=prod_options, key="ms_prod")
        sel_prod_ids = [prod_id_map[o] for o in sel_prod_opts]

    manual_ids_txt = st.sidebar.text_input("IDs de producto manuales (coma-separados) — SOLO Deuda", value="")
    if manual_ids_txt.strip():
        manual_ids = sanitize_int_list(manual_ids_txt.split(","))
        sel_prod_ids = sorted(set((sel_prod_ids or []) + manual_ids))

# =========================
#  Queries Deuda + DF final
# =========================
with st.spinner("Calculando Deuda…"):
    df_snap = query_snapshot(ALIAS_CDM, F_DIA_INI, F_DIA_FIN_NEXT, sel_id_clientes, sel_prod_ids)
    df_final = build_df_final(df_snap, INFLACION_ANUAL)

# =========================
#  TÍTULO
# =========================
st.title("Portafolio Deuda — Oracle")
st.markdown(
    f'<span class="chip">ALIAS: {ALIAS_CDM}</span>'
    f'<span class="chip">FECHA: {FECHA_ESTADISTICA}</span>'
    f'<span class="chip">ID_CLIENTE(s): {"Todos" if not sel_id_clientes else ", ".join(map(str, sel_id_clientes))}</span>'
    f'<span class="chip">ID_PRODUCTO(s): {"Todos" if not sel_prod_ids else ", ".join(map(str, sel_prod_ids))}</span>',
    unsafe_allow_html=True
)
st.markdown("<br>", unsafe_allow_html=True)

# =========================
#  TABS: AA / Deuda  (Exportar eliminado)
# =========================
tabAA, tabDeuda = st.tabs(["Asset Allocation", "Deuda"])

# ---------- TAB: ASSET ALLOCATION ----------
with tabAA:
    st.subheader("Distribución del Portafolio Total (sin filtros)")
    if len(df_aa_activo) == 0 and len(df_aa_producto) == 0:
        st.info("No hay información de Asset Allocation para la fecha seleccionada.")
    else:
        c1, c2 = st.columns((1,1))
        with c1:
            st.plotly_chart(
                donut_figure(df_aa_activo["ACTIVO"], df_aa_activo["Monto"], "Por Tipo de Activo (% sobre total)"),
                use_container_width=True, config={"displayModeBar": False}
            )
        with c2:
            top_n = st.slider("Top-N productos por monto", 5, 25, 10, 1, key="topn_aa")
            serie_top = (df_aa_producto
                         .sort_values("Monto", ascending=False)
                         .head(top_n)
                         .sort_values("Monto", ascending=True))
            fig_top = go.Figure()
            fig_top.add_trace(go.Bar(
                x=(serie_top["Monto"].values/1e6), y=list(serie_top["PRODUCTO"]), orientation="h",
                marker=dict(color=serie_top["Monto"].values, colorscale="Blues", showscale=False),
                hovertemplate="%{y}: $%{x:.2f} MM<extra></extra>"
            ))
            fig_top.update_layout(
                title=f"Top {top_n} productos por monto (MM)",
                xaxis=dict(title="Monto (millones)", gridcolor="rgba(255,255,255,.22)"),
                yaxis=dict(title=""),
                margin=dict(l=10, r=10, t=40, b=10),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(255,255,255,.05)",
                font=dict(color="#f9fafb"), height=440
            )
            st.plotly_chart(fig_top, use_container_width=True, config={"displayModeBar": False})

        # Listados tipo ranking
        def render_rank_list(df, name_col):
            if df.empty:
                st.info("Sin datos.")
                return
            html = ['<ul class="rank-list">']
            for i, r in enumerate(df.reset_index(drop=True).itertuples(index=False), start=1):
                name = getattr(r, name_col); monto = getattr(r, "Monto"); pct = getattr(r, "Porcentaje")
                html.append(
                    f'''<li class="rank-item">
                           <div class="rank-left">
                             <span class="rank-badge">{i}</span>
                             <span class="rank-name">{name}</span>
                           </div>
                           <div class="rank-right">${monto:,.2f} &nbsp;&nbsp; {pct:.2f}%</div>
                        </li>'''
                )
            html.append('</ul>')
            st.markdown("\n".join(html), unsafe_allow_html=True)

        st.markdown("<hr/>", unsafe_allow_html=True)
        st.markdown('<div class="rank-section"><div class="rank-title">Distribución por Tipo de Activo</div></div>',
                    unsafe_allow_html=True)
        render_rank_list(df_aa_activo.rename(columns={"ACTIVO":"Nombre"}), "Nombre")
        st.markdown('<div class="rank-section"><div class="rank-title">Distribución por Producto</div></div>',
                    unsafe_allow_html=True)
        render_rank_list(df_aa_producto.rename(columns={"PRODUCTO":"Nombre"}), "Nombre")

# ---------- TAB: DEUDA ----------
with tabDeuda:
    st.subheader("Deuda — Composición, Riesgo y Tabla")

    # Resumen (tarjetas)
    mask_det = df_final['Instrumento'].astype(str).str.upper() != 'TOTAL'
    df_det = df_final.loc[mask_det].copy()
    valor_mercado = df_det['Monto'].apply(parse_money_to_float).sum() if not df_det.empty else 0.0
    total_row = df_final.iloc[-1] if len(df_final) else None
    resumen_vals = {
        "Instrumentos": f"{int(mask_det.sum()):,}",
        "Valor de mercado": f"${valor_mercado:,.2f}",
        "Duración (días)": "" if total_row is None else str(total_row['Duración (días)']),
        "DxV (pond.)": "" if total_row is None else str(total_row['DxV']),
        "Rto. esperado 1 año": "" if total_row is None else str(total_row['Carry (365 d)']),
    }
    st.markdown('<div class="kpi-grid">' + "".join(
        [f'<div class="kpi-card"><div class="kpi-label">{k}</div><div class="kpi-value">{v}</div></div>'
         for k,v in resumen_vals.items()]
    ) + '</div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # 1) Composición por Tipo de Papel / Instrumento
    is_rep = df_det['Tipo de Papel'].str.contains('reporto', case=False, na=False) | \
             df_det['Tipo de instrumento'].str.contains('reporto', case=False, na=False)

    aux_tp = df_det.copy(); aux_tp.loc[is_rep, 'Tipo de Papel'] = 'Gubernamental'
    serie_tp = (aux_tp.groupby('Tipo de Papel')['% Cartera']
                    .apply(lambda s: pd.Series(parse_pct_col(x) for x in s).sum())).fillna(0.0)

    aux_ti = df_det.copy(); aux_ti.loc[is_rep, 'Tipo de instrumento'] = 'Reporto'
    serie_ti = (aux_ti.groupby('Tipo de instrumento')['% Cartera']
                    .apply(lambda s: pd.Series(parse_pct_col(x) for x in s).sum())).fillna(0.0)

    c6, c7 = st.columns(2)
    c6.plotly_chart(barh_percent_figure(serie_tp, "Composición por Tipo de Papel (Reporto → Gubernamental)"),
                    use_container_width=True, config={"displayModeBar": False})
    c7.plotly_chart(barh_percent_figure(serie_ti, "Composición por Tipo de Instrumento (incluye Reporto)"),
                    use_container_width=True, config={"displayModeBar": False})

    st.markdown("<br>", unsafe_allow_html=True)

    # 2) TABLA SEMÁFORO DE RIESGO
    r = (df_det.groupby('Calificación', dropna=False)['% Cartera']
              .apply(lambda s: pd.Series(parse_pct_col(x) for x in s).sum()).reset_index())
    r.columns = ['Escala','Pct']
    fig_semaforo = risk_table_semaforo(r, "Riesgo por Calificación (semáforo)")
    st.plotly_chart(fig_semaforo, use_container_width=True, config={"displayModeBar": False})

    st.markdown("<br>", unsafe_allow_html=True)

    # 3) Tabla general (detalle + TOTAL al final)
    st.subheader("Tabla detallada")
    q = st.text_input("Buscar (instrumento / papel / calificación)", "")
    df_detail = df_final.iloc[:-1].copy()
    df_total  = df_final.iloc[[-1]].copy()
    if q:
        mask_q = (
            df_detail['Instrumento'].str.contains(q, case=False, na=False) |
            df_detail['Tipo de Papel'].str.contains(q, case=False, na=False) |
            df_detail['Calificación'].str.contains(q, case=False, na=False)
        )
        df_detail = df_detail[mask_q]
    df_view = pd.concat([df_detail, df_total], ignore_index=True)
    st.dataframe(df_view, use_container_width=True, height=560)
    st.caption("Orden del detalle: Reporto primero; después por Tipo de Papel y Monto. La fila TOTAL permanece al final.")

# ---------- FOOTER ----------
st.markdown("<hr/><div style='text-align:center;opacity:.85'><small>Asset Allocation (sin filtros). Deuda: filtros por ID_CLIENTE e ID_PRODUCTO desde HIS.</small></div>", unsafe_allow_html=True)
