
import os
import numpy as np
import pandas as pd
import streamlit as st
import oracledb
import plotly.graph_objects as go

st.set_page_config(
    page_title="Radar Generacional | Columbus",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
/* Sidebar */
[data-testid="stSidebar"]{background:#0F1923}
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] .stMarkdown,
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span:not([data-baseweb]){color:#94A3B8!important}
[data-testid="stSidebar"] h2{color:#E2E8F0!important;font-size:.72rem;letter-spacing:.1em;text-transform:uppercase;margin-top:1.2rem}
[data-testid="stSidebar"] hr{border-color:#1E3A5F}
[data-testid="stSidebar"] .stMultiSelect [data-baseweb="tag"]{background:#1E3A5F!important}

/* Botones */
.stButton>button{
    background:#1E3A5F;color:#fff;border:none;
    border-radius:6px;font-weight:600;width:100%;
    padding:9px;font-size:.84rem;transition:background .15s
}
.stButton>button:hover{background:#2563EB}

/* Tabs */
.stTabs [data-baseweb="tab-list"]{gap:0;border-bottom:2px solid #E2E8F0}
.stTabs [data-baseweb="tab"]{border-radius:6px 6px 0 0;font-weight:600;font-size:.84rem;
    color:#94A3B8;padding:10px 22px;background:transparent}
.stTabs [data-baseweb="tab"]:hover{color:#1E3A5F;background:#F8FAFC}
.stTabs [aria-selected="true"]{color:#1E3A5F!important;border-bottom:2px solid #1E3A5F;background:#fff!important}

/* Tablas */
.stDataFrame{border-radius:8px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.07)}

/* Tipografía */
h1,h2,h3{color:#0F172A!important}

/* Lista header */
.list-header{
    background:#1E3A5F;color:#fff;
    border-radius:8px 8px 0 0;
    padding:14px 20px;margin-bottom:0
}
.list-header .title{font-size:1rem;font-weight:700;margin:0}
.list-header .subtitle{font-size:.78rem;opacity:.75;margin:3px 0 0}

/* Definición de campo */
.field-def{
    background:#F0F6FF;border-left:3px solid #2563EB;
    border-radius:0 6px 6px 0;padding:10px 14px;
    font-size:.8rem;color:#1E3A5F;line-height:1.6;margin-bottom:12px
}

/* KPI card */
.kpi{
    background:#fff;border-left:3px solid #1E3A5F;
    border-radius:0 8px 8px 0;padding:12px 16px;
    box-shadow:0 1px 3px rgba(0,0,0,.06);
    position:relative;overflow:visible
}
.kpi .lbl{font-size:.65rem;color:#64748B;text-transform:uppercase;letter-spacing:.05em;font-weight:600}
.kpi .val{font-size:1.35rem;font-weight:700;color:#0F172A;margin-top:2px}
.kpi.blue  {border-left-color:#1E3A5F}
.kpi.slate {border-left-color:#64748B}
.kpi.green {border-left-color:#16A34A}
.kpi.amber {border-left-color:#D97706}
.kpi.red   {border-left-color:#DC2626}

/* KPI tooltip */
.kpi-tip{
    display:inline-block;margin-left:4px;cursor:help;
    color:#94A3B8;font-size:.7rem;font-style:normal;
    position:relative;vertical-align:middle
}
.kpi-tip::after{
    content:attr(data-tip);
    display:none;
    position:absolute;bottom:calc(100% + 6px);left:50%;
    transform:translateX(-50%);
    background:#1E3A5F;color:#fff;
    padding:7px 11px;border-radius:6px;
    font-size:.72rem;font-weight:400;line-height:1.5;
    white-space:normal;width:230px;
    text-transform:none;letter-spacing:0;
    z-index:9999;box-shadow:0 4px 12px rgba(0,0,0,.2)
}
.kpi-tip::before{
    content:'';display:none;
    position:absolute;bottom:calc(100% + 1px);left:50%;
    transform:translateX(-50%);
    border:5px solid transparent;border-top-color:#1E3A5F;
    z-index:9999
}
.kpi-tip:hover::after,.kpi-tip:hover::before{display:block}

/* Badge sin contacto */
.badge-no-contact{
    background:#FEF2F2;color:#991B1B;
    border:1px solid #FECACA;border-radius:4px;
    padding:2px 7px;font-size:.72rem;font-weight:600;
    white-space:nowrap
}
.badge-ok-contact{
    background:#F0FDF4;color:#166534;
    border:1px solid #BBF7D0;border-radius:4px;
    padding:2px 7px;font-size:.72rem;font-weight:600
}

/* Header cliente */
.client-header{
    background:linear-gradient(135deg,#1E3A5F 0%,#2563EB 100%);
    border-radius:10px;padding:18px 24px;color:#fff;margin-bottom:16px
}
.client-header .name{font-size:1.4rem;font-weight:700;margin:2px 0 8px}
.client-header .meta{font-size:.84rem;opacity:.8;display:flex;gap:28px;flex-wrap:wrap}
</style>
""", unsafe_allow_html=True)

# ── Configuración ─────────────────────────────────────────────────────────────
SCHEMA = "SIAPII"
HOST = st.secrets.get("ORACLE_HOST", os.getenv("ORACLE_HOST"))
PORT = int(st.secrets.get("ORACLE_PORT", os.getenv("ORACLE_PORT", 1521)))
SID  = st.secrets.get("ORACLE_SID",  os.getenv("ORACLE_SID"))
USER = st.secrets.get("ORACLE_USER", os.getenv("ORACLE_USER"))
PWD  = st.secrets.get("ORACLE_PWD",  os.getenv("ORACLE_PWD"))

# ── Helpers ───────────────────────────────────────────────────────────────────
def normalize_text(x):
    if pd.isna(x): return None
    return str(x).strip().upper()

def fmt_mdp(v):
    if pd.isna(v) or v == 0: return "$0"
    if abs(v) >= 1e9:  return f"${v/1e9:,.1f}B"
    if abs(v) >= 1e6:  return f"${v/1e6:,.1f}M"
    if abs(v) >= 1e3:  return f"${v/1e3:,.0f}K"
    return f"${v:,.0f}"

def coverage_color_cls(v):
    if v >= 0.75: return "green"
    if v >= 0.40: return "amber"
    return "red"

def kpi_card(col, label, value, cls="blue", tip=None):
    if tip:
        safe_tip = tip.replace('"', "&#34;").replace("'", "&#39;")
        tip_html = f'<span class="kpi-tip" data-tip="{safe_tip}">&#9432;</span>'
    else:
        tip_html = ""
    col.markdown(
        f'<div class="kpi {cls}"><div class="lbl">{label}{tip_html}</div>'
        f'<div class="val">{value}</div></div>',
        unsafe_allow_html=True,
    )

def contact_badge(tiene_tel, tiene_mail):
    if not tiene_tel and not tiene_mail:
        return '<span class="badge-no-contact">Sin contacto</span>'
    return '<span class="badge-ok-contact">Contactable</span>'

# ── Pool Oracle ───────────────────────────────────────────────────────────────
@st.cache_resource
def get_pool():
    dsn = oracledb.makedsn(HOST, PORT, sid=SID)
    return oracledb.create_pool(user=USER, password=PWD, dsn=dsn, min=1, max=4)

# ── Carga principal ───────────────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner="Cargando datos…")
def load_base_data() -> pd.DataFrame:
    sql = (
        "WITH POS_ULT AS ("
        "    SELECT ID_CLIENTE, VALOR_REAL,"
        "           ROW_NUMBER() OVER (PARTITION BY ID_CLIENTE"
        "               ORDER BY REGISTRO_CONTROL DESC) AS RN"
        "    FROM " + SCHEMA + ".V_HIS_POSICION_CLIENTE WHERE VALOR_REAL > 0"
        ") "
        "SELECT b.OFICINA, b.CVE_PROMOTOR, b.PROMOTOR,"
        "       b.REFERIDOR, b.NOMBRE_REFERIDOR, b.CUSTODIO,"
        "       b.ID_CDM, b.ALIAS_CLIENTE, b.NOMBRE_CLIENTE, b.SEXO,"
        "       b.TIPO_CONTRATO, b.ID_CLIENTE, b.CONTRATO,"
        "       b.ID_PERSONA_RELACIONADA, b.ROL,"
        "       b.NOMBRE_BENEFICIARIO, b.PERSONA, b.GENERO,"
        "       b.FECHA_NACIMIENTO AS FECHA_NACIMIENTO_BEN,"
        "       b.EDAD2, b.PARENTESCO,"
        "       b.CURP AS CURP_BENEFICIARIO,"
        "       b.PORCENTAJE_BENEFICIARIO AS PORCENTAJE,"
        "       b.CELULAR_BENEFICIARIO AS TELEFONO,"
        "       b.MAIL_BENEFICIARIO AS CORREO,"
        "       ccli.FECHA_NACIMIENTO AS FECHA_NACIMIENTO_CLIENTE,"
        "       ccli.FECHA_INGRESO,"
        "       CASE WHEN cben.ID_CDM IS NOT NULL THEN 1 ELSE 0 END AS ES_CLIENTE_BENEFICIARIO,"
        "       NVL(pos.VALOR_REAL, 0) AS VALOR_CONTRATO_ACTUAL"
        " FROM " + SCHEMA + ".V_B_BENEFICIARIOS_CLIENTE b"
        " LEFT JOIN " + SCHEMA + ".V_C_IDENTIFICA_CLIENTE ccli ON b.ID_CDM = ccli.ID_CDM"
        " LEFT JOIN " + SCHEMA + ".V_C_IDENTIFICA_CLIENTE cben"
        "       ON REPLACE(REPLACE(UPPER(TRIM(b.CURP)),' ',''),'-','')"
        "        = REPLACE(REPLACE(UPPER(TRIM(cben.CURP)),' ',''),'-','')"
        " LEFT JOIN POS_ULT pos ON b.ID_CLIENTE = pos.ID_CLIENTE AND pos.RN = 1"
    )
    with get_pool().acquire() as conn:
        return pd.read_sql(sql, conn)

# ── Historial bajo demanda ────────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner="Cargando historial…")
def load_history(id_cliente: str) -> pd.DataFrame:
    sql = (
        "SELECT ID_CLIENTE,"
        "       TRUNC(REGISTRO_CONTROL,'MM') AS MES,"
        "       MAX(VALOR_REAL) KEEP (DENSE_RANK LAST ORDER BY REGISTRO_CONTROL) AS VALOR_REAL"
        " FROM " + SCHEMA + ".V_HIS_POSICION_CLIENTE"
        " WHERE ID_CLIENTE = :id"
        "   AND REGISTRO_CONTROL >= ADD_MONTHS(TRUNC(SYSDATE),-60)"
        " GROUP BY ID_CLIENTE, TRUNC(REGISTRO_CONTROL,'MM')"
        " ORDER BY MES"
    )
    with get_pool().acquire() as conn:
        return pd.read_sql(sql, conn, params={"id": id_cliente})

# ── Modelo base ───────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def build_model(df_raw: pd.DataFrame) -> pd.DataFrame:  # v2
    df = df_raw.copy()
    df.columns = [c.upper() for c in df.columns]

    df["OFICINA"] = df["OFICINA"].map(normalize_text)
    for col in ("PROMOTOR","REFERIDOR","NOMBRE_REFERIDOR","CUSTODIO",
                "TIPO_CONTRATO","PARENTESCO","GENERO"):
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()

    today = pd.Timestamp.today().normalize()
    df["FECHA_NACIMIENTO_CLIENTE"] = pd.to_datetime(df.get("FECHA_NACIMIENTO_CLIENTE"), errors="coerce")
    df["FECHA_NACIMIENTO_BEN"]     = pd.to_datetime(df.get("FECHA_NACIMIENTO_BEN"),     errors="coerce")
    df["FECHA_INGRESO"]            = pd.to_datetime(df.get("FECHA_INGRESO"),            errors="coerce")
    df["EDAD_CLIENTE"]      = ((today - df["FECHA_NACIMIENTO_CLIENTE"]).dt.days / 365.25).round()
    df["EDAD_BENEFICIARIO"] = ((today - df["FECHA_NACIMIENTO_BEN"]).dt.days / 365.25).round()

    df["VALOR_CONTRATO_ACTUAL"] = pd.to_numeric(df["VALOR_CONTRATO_ACTUAL"], errors="coerce").fillna(0)
    df["PORCENTAJE"]            = pd.to_numeric(df["PORCENTAJE"],            errors="coerce").fillna(0)
    df["VALOR_ASIGNADO"]        = df["VALOR_CONTRATO_ACTUAL"] * (df["PORCENTAJE"] / 100.0)

    df["TELEFONO"] = df["TELEFONO"].replace("", np.nan)
    df["CORREO"]   = df["CORREO"].replace("", np.nan)
    df["TIENE_TELEFONO"] = df["TELEFONO"].notna()
    df["TIENE_CORREO"]   = df["CORREO"].notna()
    df["CONTACTABLE"]    = df["TIENE_TELEFONO"] | df["TIENE_CORREO"]

    df["ES_CLIENTE"]      = df["ES_CLIENTE_BENEFICIARIO"].fillna(0).astype(int).eq(1)
    df["ESTATUS_CLIENTE"] = np.where(df["ES_CLIENTE"], "Cliente", "No cliente")
    df["ES_MUJER"]        = df["GENERO"].str.upper().str.strip().isin(["FEMENINO","F","MUJER"])
    df["CURP_VACIO"]      = df["CURP_BENEFICIARIO"].isna() | (df["CURP_BENEFICIARIO"].astype(str).str.strip() == "")

    # Vectorized — computed once here instead of 3×apply in render_radar
    df["CONTACTO"] = np.select(
        [~df["CONTACTABLE"],
         df["TIENE_TELEFONO"] & df["TIENE_CORREO"],
         df["TIENE_TELEFONO"]],
        ["Sin contacto", "Tel. y correo", "Telefono"],
        default="Correo",
    )
    return df

# ── Sidebar — solo filtros clave para el asesor ───────────────────────────────
def sidebar_filters(df: pd.DataFrame) -> pd.DataFrame:
    with st.sidebar:
        st.markdown("## Filtros")

        oficinas   = st.multiselect("Oficina",   sorted(df["OFICINA"].dropna().unique()))
        promotores = st.multiselect("Promotor",  sorted(df["PROMOTOR"].dropna().unique()))

        st.markdown("---")
        aplicar = st.button("Aplicar filtros", use_container_width=True)
        if st.button("Limpiar filtros", use_container_width=True):
            st.session_state.pop("filtered_df", None)
            st.rerun()

    if not aplicar and "filtered_df" in st.session_state:
        return st.session_state["filtered_df"]

    b = df.copy()
    if oficinas:   b = b[b["OFICINA"].isin(oficinas)]
    if promotores: b = b[b["PROMOTOR"].isin(promotores)]

    st.session_state["filtered_df"] = b
    return b

# ── Función auxiliar: tabla de acción ─────────────────────────────────────────
def render_action_table(df_list: pd.DataFrame, cols_display: list,
                        col_rename: dict, fmt: dict,
                        key: str, height: int = 500) -> None:
    """Renderiza una tabla de trabajo con badge de contacto embebido."""
    show = df_list[cols_display].copy().rename(columns=col_rename)

    # Badge de contacto como columna de texto (no HTML — st.dataframe no renderiza HTML)
    # Se usa texto plano con símbolo para mantener legibilidad ejecutiva
    if "CONTACTO" in show.columns:
        show["CONTACTO"] = show["CONTACTO"].apply(
            lambda x: "Sin contacto" if x == "Sin contacto" else x
        )

    styled = show.style.format(fmt, na_rep="—")

    # Resaltar filas sin contacto en rojo suave
    def _highlight_no_contact(row):
        if "Contacto" in row.index and row["Contacto"] == "Sin contacto":
            return ["background-color:#FFF5F5"] * len(row)
        return [""] * len(row)

    if "Contacto" in show.columns:
        styled = styled.apply(_highlight_no_contact, axis=1)

    st.dataframe(styled, use_container_width=True, height=height, hide_index=True)

# ── TAB 1: Radar ──────────────────────────────────────────────────────────────
def render_radar(b: pd.DataFrame) -> None:

    # ── KPIs ejecutivos ───────────────────────────────────────────────────────
    total_clientes   = b["ID_CDM"].nunique()
    total_contratos  = b["CONTRATO"].nunique()
    total_ben        = len(b)
    ben_no_cli       = int((~b["ES_CLIENTE"]).sum())
    sin_curp         = int(b["CURP_VACIO"].sum())
    sin_contacto     = int((~b["CONTACTABLE"]).sum())
    coverage         = int(b["ES_CLIENTE"].sum()) / total_ben if total_ben else 0

    c1,c2,c3,c4,c5,c6,c7 = st.columns(7)
    kpi_card(c1, "Clientes",              f"{total_clientes:,}",  "blue",
             tip="Clientes únicos (ID_CDM) en el universo filtrado.")
    kpi_card(c2, "Contratos",             f"{total_contratos:,}", "blue",
             tip="Contratos únicos activos en el universo filtrado.")
    kpi_card(c3, "Beneficiarios totales", f"{total_ben:,}",       "slate",
             tip="Total de filas de beneficiarios. Un cliente puede tener múltiples beneficiarios en distintos contratos.")
    kpi_card(c4, "No clientes",           f"{ben_no_cli:,}",      "amber",
             tip="Beneficiarios cuyo CURP no coincide con ningún cliente registrado en Columbus. Son prospectos potenciales.")
    kpi_card(c5, "Sin CURP registrado",   f"{sin_curp:,}",        "red",
             tip="Beneficiarios sin CURP capturado. Sin CURP no es posible cruzarlos contra la base de clientes.")
    kpi_card(c6, "Sin datos de contacto", f"{sin_contacto:,}",    "red",
             tip="Beneficiarios que no tienen ni teléfono ni correo electrónico registrado en el sistema.")
    kpi_card(c7, "Coverage generacional", f"{coverage:.1%}",      coverage_color_cls(coverage),
             tip="Porcentaje de beneficiarios que ya son clientes de Columbus. Fórmula: Beneficiarios-clientes ÷ Total beneficiarios.")

    st.markdown("<div style='margin-top:32px'></div>", unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════════
    # LISTA A — Beneficiarios sin identificar
    # ══════════════════════════════════════════════════════════════════════════
    st.markdown("""
    <div class="list-header">
      <div class="title">Beneficiarios sin identificar</div>
      <div class="subtitle">
        Beneficiarios cuyo CURP no está registrado en el sistema.
        No es posible determinar si ya son clientes de Columbus.
        Ordenados por valor del contrato del titular, de mayor a menor.
      </div>
    </div>""", unsafe_allow_html=True)

    st.markdown("""
    <div class="field-def">
      <strong>CURP:</strong> Clave Unica de Registro de Poblacion. Es el identificador
      que permite cruzar al beneficiario contra la base de clientes de Columbus para
      determinar si ya tiene una relacion comercial con la firma.
      Sin CURP, no es posible saber si el beneficiario es cliente o prospecto.
      <br><strong>Accion recomendada:</strong> Solicitar el CURP del beneficiario
      al cliente titular en la proxima interaccion.
    </div>""", unsafe_allow_html=True)

    lista_a = (
        b[b["CURP_VACIO"]]
        .sort_values("VALOR_CONTRATO_ACTUAL", ascending=False)
    )

    col_a1, col_a2, col_a3 = st.columns(3)
    kpi_card(col_a1, "Beneficiarios sin CURP",    f"{len(lista_a):,}",
             "red",  tip="Total de beneficiarios sin CURP registrado en el filtro actual.")
    kpi_card(col_a2, "Valor total de contratos",  fmt_mdp(lista_a["VALOR_CONTRATO_ACTUAL"].sum()),
             "blue", tip="Suma del valor de mercado actual de los contratos de los titulares de esta lista.")
    kpi_card(col_a3, "Sin datos de contacto",     f"{int((lista_a['CONTACTO']=='Sin contacto').sum()):,}",
             "red",  tip="Beneficiarios de esta lista sin teléfono ni correo registrado.")

    st.markdown("<div style='margin-top:10px'></div>", unsafe_allow_html=True)

    if lista_a.empty:
        st.info("No hay beneficiarios sin CURP con los filtros actuales.")
    else:
        cols_a   = ["PROMOTOR","NOMBRE_CLIENTE","CONTRATO","TIPO_CONTRATO",
                    "VALOR_CONTRATO_ACTUAL","NOMBRE_BENEFICIARIO","PARENTESCO",
                    "EDAD_BENEFICIARIO","TELEFONO","CORREO","CONTACTO"]
        rename_a = {"PROMOTOR":"Promotor","NOMBRE_CLIENTE":"Titular",
                    "CONTRATO":"Contrato","TIPO_CONTRATO":"Tipo",
                    "VALOR_CONTRATO_ACTUAL":"Valor contrato",
                    "NOMBRE_BENEFICIARIO":"Beneficiario","PARENTESCO":"Parentesco",
                    "EDAD_BENEFICIARIO":"Edad benef.","TELEFONO":"Telefono",
                    "CORREO":"Correo","CONTACTO":"Contacto"}
        fmt_a    = {"Valor contrato": "{:,.0f}", "Edad benef.": "{:.0f}"}

        def _style_a(row):
            if row.get("Contacto") == "Sin contacto":
                return ["background-color:#FFF5F5"] * len(row)
            return [""] * len(row)

        show_a = lista_a[[c for c in cols_a if c in lista_a.columns]].rename(columns=rename_a)
        st.dataframe(
            show_a.style.format(fmt_a, na_rep="—").apply(_style_a, axis=1),
            use_container_width=True, height=380, hide_index=True,
        )
        st.download_button(
            "Exportar lista A",
            show_a.to_csv(index=False).encode("utf-8"),
            "sin_identificar.csv", "text/csv",
            key="dl_a",
        )

    st.markdown("<div style='margin-top:36px'></div>", unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════════
    # LISTA B — Captacion prioritaria
    # ══════════════════════════════════════════════════════════════════════════
    st.markdown("""
    <div class="list-header">
      <div class="title">Captacion prioritaria</div>
      <div class="subtitle">
        Beneficiarios con CURP registrado que no son clientes de Columbus.
        Son los prospectos de mayor certeza: sabemos quienes son pero aun no
        tienen una relacion comercial con la firma.
        Ordenados por valor del contrato del titular, de mayor a menor.
      </div>
    </div>""", unsafe_allow_html=True)

    st.markdown("""
    <div class="field-def">
      <strong>Valor del contrato:</strong> Valor de mercado actual del portafolio
      del cliente titular. Refleja el tamano del patrimonio en juego en caso de
      transferencia generacional.<br>
      <strong>Valor asignado:</strong> Porcion del contrato que le corresponde al
      beneficiario segun el porcentaje registrado. Indica cuanto capital ingresaria
      a Columbus si el beneficiario se convierte en cliente.<br>
      <strong>Accion recomendada:</strong> Contactar al beneficiario o solicitarle
      al titular que facilite la introduccion.
    </div>""", unsafe_allow_html=True)

    lista_b = (
        b[~b["CURP_VACIO"] & ~b["ES_CLIENTE"]]
        .sort_values("VALOR_CONTRATO_ACTUAL", ascending=False)
    )

    col_b1, col_b2, col_b3, col_b4 = st.columns(4)
    kpi_card(col_b1, "Prospectos identificados",  f"{len(lista_b):,}",
             "amber", tip="Beneficiarios con CURP registrado que NO son clientes de Columbus. Identidad confirmada pero sin relación comercial.")
    kpi_card(col_b2, "Valor total de contratos",  fmt_mdp(lista_b["VALOR_CONTRATO_ACTUAL"].sum()),
             "blue",  tip="Suma del valor de mercado actual de los contratos de los titulares de esta lista.")
    kpi_card(col_b3, "Valor asignado total",      fmt_mdp(lista_b["VALOR_ASIGNADO"].sum()),
             "blue",  tip="Capital total asignado a estos prospectos. Fórmula: Σ(Valor contrato × % beneficiario ÷ 100).")
    kpi_card(col_b4, "Sin datos de contacto",     f"{int((lista_b['CONTACTO']=='Sin contacto').sum()):,}",
             "red",   tip="Prospectos identificados sin teléfono ni correo registrado.")

    st.markdown("<div style='margin-top:10px'></div>", unsafe_allow_html=True)

    if lista_b.empty:
        st.info("No hay prospectos identificados con los filtros actuales.")
    else:
        cols_b   = ["PROMOTOR","NOMBRE_CLIENTE","EDAD_CLIENTE","CONTRATO","TIPO_CONTRATO",
                    "VALOR_CONTRATO_ACTUAL","NOMBRE_BENEFICIARIO","PARENTESCO",
                    "EDAD_BENEFICIARIO","PORCENTAJE","VALOR_ASIGNADO",
                    "TELEFONO","CORREO","CONTACTO"]
        rename_b = {"PROMOTOR":"Promotor","NOMBRE_CLIENTE":"Titular",
                    "EDAD_CLIENTE":"Edad titular","CONTRATO":"Contrato",
                    "TIPO_CONTRATO":"Tipo","VALOR_CONTRATO_ACTUAL":"Valor contrato",
                    "NOMBRE_BENEFICIARIO":"Beneficiario","PARENTESCO":"Parentesco",
                    "EDAD_BENEFICIARIO":"Edad benef.","PORCENTAJE":"%",
                    "VALOR_ASIGNADO":"Valor asignado",
                    "TELEFONO":"Telefono","CORREO":"Correo","CONTACTO":"Contacto"}
        fmt_b    = {"Valor contrato":"{:,.0f}","Valor asignado":"{:,.0f}",
                    "Edad titular":"{:.0f}","Edad benef.":"{:.0f}","%":"{:.1f}"}

        def _style_b(row):
            if row.get("Contacto") == "Sin contacto":
                return ["background-color:#FFF5F5"] * len(row)
            return [""] * len(row)

        show_b = lista_b[[c for c in cols_b if c in lista_b.columns]].rename(columns=rename_b)
        st.dataframe(
            show_b.style.format(fmt_b, na_rep="—").apply(_style_b, axis=1),
            use_container_width=True, height=420, hide_index=True,
        )
        st.download_button(
            "Exportar lista B",
            show_b.to_csv(index=False).encode("utf-8"),
            "captacion_prioritaria.csv", "text/csv",
            key="dl_b",
        )

    st.markdown("<div style='margin-top:36px'></div>", unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════════
    # LISTA C — Beneficiarios silent gen
    # ══════════════════════════════════════════════════════════════════════════
    st.markdown("""
    <div class="list-header">
      <div class="title">Beneficiarios silent gen</div>
      <div class="subtitle">
        Beneficiarios no clientes cuyo titular tiene 80 anos o mas.
        El riesgo de transferencia generacional es inmediato.
        Ordenados por valor del contrato del titular, de mayor a menor.
      </div>
    </div>""", unsafe_allow_html=True)

    st.markdown("""
    <div class="field-def">
      <strong>Silent generation:</strong> Clientes titulares de 80 anos o mas.
      En caso de fallecimiento, el patrimonio se transfiere a los beneficiarios registrados.
      Si estos no son clientes de Columbus, el capital sale de la firma.<br>
      <strong>Edad del titular:</strong> Calculada a partir de la fecha de nacimiento
      registrada en el sistema.<br>
      <strong>Accion recomendada:</strong> Contacto inmediato con el beneficiario.
      Priorizar sobre cualquier otro prospecto.
    </div>""", unsafe_allow_html=True)

    lista_c = (
        b[~b["ES_CLIENTE"] & (b["EDAD_CLIENTE"].fillna(0) >= 80)]
        .sort_values("VALOR_CONTRATO_ACTUAL", ascending=False)
    )

    col_c1, col_c2, col_c3, col_c4 = st.columns(4)
    kpi_card(col_c1, "Beneficiarios en riesgo",   f"{len(lista_c):,}",
             "red",  tip="Beneficiarios NO clientes cuyo titular tiene 80 años o más (Silent Generation). Riesgo de transferencia generacional inmediato.")
    kpi_card(col_c2, "Contratos en riesgo",       f"{lista_c['CONTRATO'].nunique():,}",
             "red",  tip="Contratos únicos con titulares ≥80 años que tienen beneficiarios aún no captados.")
    kpi_card(col_c3, "Valor total de contratos",  fmt_mdp(lista_c["VALOR_CONTRATO_ACTUAL"].sum()),
             "blue", tip="Suma del valor de mercado actual de los contratos de titulares Silent Gen.")
    kpi_card(col_c4, "Sin datos de contacto",     f"{int((lista_c['CONTACTO']=='Sin contacto').sum()):,}",
             "red",  tip="Beneficiarios Silent Gen sin teléfono ni correo registrado. Máxima urgencia de actualización.")

    st.markdown("<div style='margin-top:10px'></div>", unsafe_allow_html=True)

    if lista_c.empty:
        st.info("No hay beneficiarios silent gen con los filtros actuales.")
    else:
        cols_c   = ["PROMOTOR","NOMBRE_CLIENTE","EDAD_CLIENTE","CONTRATO","TIPO_CONTRATO",
                    "VALOR_CONTRATO_ACTUAL","NOMBRE_BENEFICIARIO","PARENTESCO",
                    "EDAD_BENEFICIARIO","PORCENTAJE","VALOR_ASIGNADO",
                    "CURP_VACIO","TELEFONO","CORREO","CONTACTO"]
        rename_c = {"PROMOTOR":"Promotor","NOMBRE_CLIENTE":"Titular",
                    "EDAD_CLIENTE":"Edad titular","CONTRATO":"Contrato",
                    "TIPO_CONTRATO":"Tipo","VALOR_CONTRATO_ACTUAL":"Valor contrato",
                    "NOMBRE_BENEFICIARIO":"Beneficiario","PARENTESCO":"Parentesco",
                    "EDAD_BENEFICIARIO":"Edad benef.","PORCENTAJE":"%",
                    "VALOR_ASIGNADO":"Valor asignado","CURP_VACIO":"Sin CURP",
                    "TELEFONO":"Telefono","CORREO":"Correo","CONTACTO":"Contacto"}
        fmt_c    = {"Valor contrato":"{:,.0f}","Valor asignado":"{:,.0f}",
                    "Edad titular":"{:.0f}","Edad benef.":"{:.0f}","%":"{:.1f}"}

        def _style_c(row):
            styles = [""] * len(row)
            if row.get("Contacto") == "Sin contacto":
                return ["background-color:#FFF5F5"] * len(row)
            return styles

        show_c = lista_c[[c for c in cols_c if c in lista_c.columns]].rename(columns=rename_c)
        # Reemplazar booleano por texto legible
        if "Sin CURP" in show_c.columns:
            show_c["Sin CURP"] = show_c["Sin CURP"].map({True:"Sin CURP", False:""})

        st.dataframe(
            show_c.style.format(fmt_c, na_rep="—").apply(_style_c, axis=1),
            use_container_width=True, height=420, hide_index=True,
        )
        st.download_button(
            "Exportar lista C",
            show_c.to_csv(index=False).encode("utf-8"),
            "silent_gen.csv", "text/csv",
            key="dl_c",
        )

# ── TAB 2: Detalle Cliente ────────────────────────────────────────────────────
def render_detail(b: pd.DataFrame) -> None:
    st.markdown("### Detalle Cliente")

    clientes = (b[["NOMBRE_CLIENTE","ALIAS_CLIENTE"]]
                .drop_duplicates("NOMBRE_CLIENTE")
                .sort_values("NOMBRE_CLIENTE"))
    if clientes.empty:
        st.info("Sin clientes disponibles.")
        return

    nombres = clientes["NOMBRE_CLIENTE"].tolist()
    presel  = st.session_state.get("detalle_nombre", nombres[0])
    if presel not in nombres: presel = nombres[0]

    nombre_sel = st.selectbox("Buscar cliente por nombre", nombres,
                              index=nombres.index(presel))
    st.session_state.pop("detalle_nombre", None)

    d_cliente = b[b["NOMBRE_CLIENTE"] == nombre_sel].copy()
    if d_cliente.empty:
        st.info("Sin datos.")
        return

    head             = d_cliente.iloc[0]
    contratos_list   = sorted(d_cliente["CONTRATO"].dropna().unique().tolist())
    n_contratos      = len(contratos_list)
    edad_v           = head.get("EDAD_CLIENTE", 0)
    edad_str         = f"{int(edad_v)} anos" if pd.notna(edad_v) and edad_v else "—"
    valor_total      = d_cliente.drop_duplicates("CONTRATO")["VALOR_CONTRATO_ACTUAL"].sum()
    valor_dentro     = d_cliente.loc[d_cliente["ES_CLIENTE"],"VALOR_ASIGNADO"].sum()
    tb               = len(d_cliente)
    cov              = int(d_cliente["ES_CLIENTE"].sum()) / tb if tb else 0

    # Header
    st.markdown(f"""
    <div class="client-header">
      <div style="font-size:.72rem;opacity:.7;text-transform:uppercase;letter-spacing:.08em">Cliente</div>
      <div class="name">{nombre_sel}</div>
      <div class="meta">
        <span>{head.get("OFICINA","")}</span>
        <span>{head.get("PROMOTOR","")}</span>
        <span>{edad_str}</span>
        <span>{n_contratos} contrato{"s" if n_contratos!=1 else ""}</span>
      </div>
    </div>""", unsafe_allow_html=True)

    # KPIs globales
    k1,k2,k3,k4,k5 = st.columns(5)
    kpi_card(k1, "Contratos",             str(n_contratos),
             "blue",  tip="Número de contratos activos del cliente seleccionado.")
    kpi_card(k2, "Valor total portafolio",fmt_mdp(valor_total),
             "blue",  tip="Suma del valor de mercado actual de todos los contratos del cliente.")
    kpi_card(k3, "Beneficiarios totales", str(tb),
             "slate", tip="Total de beneficiarios registrados en todos los contratos del cliente.")
    kpi_card(k4, "Valor dentro",          fmt_mdp(valor_dentro),
             "green", tip="Valor asignado a beneficiarios que ya son clientes de Columbus. Fórmula: Σ(Valor × % benef.) para beneficiarios-clientes.")
    kpi_card(k5, "Coverage total",        f"{cov:.1%}",
             coverage_color_cls(cov), tip="Porcentaje de beneficiarios del cliente que ya son clientes de Columbus. Fórmula: Beneficiarios-clientes ÷ Total beneficiarios.")

    st.markdown("<div style='margin-top:24px'></div>", unsafe_allow_html=True)
    st.markdown("### Contratos")

    for contrato in contratos_list:
        dc = d_cliente[d_cliente["CONTRATO"] == contrato].copy()
        if dc.empty: continue

        h             = dc.iloc[0]
        val_c         = h.get("VALOR_CONTRATO_ACTUAL", 0)
        val_dentro_c  = dc.loc[dc["ES_CLIENTE"],"VALOR_ASIGNADO"].sum()
        ben_c         = len(dc)
        cov_c         = int(dc["ES_CLIENTE"].sum()) / ben_c if ben_c else 0
        id_cliente_c  = h.get("ID_CLIENTE")

        with st.expander(
            f"{contrato}  ·  {h.get('TIPO_CONTRATO','')}  ·  "
            f"{fmt_mdp(val_c)}  ·  Coverage {cov_c:.0%}",
            expanded=(n_contratos == 1),
        ):
            ck1,ck2,ck3,ck4 = st.columns(4)
            kpi_card(ck1, "Valor del contrato",  fmt_mdp(val_c),
                     "blue",  tip="Valor de mercado actual del contrato según el último registro de posición.")
            kpi_card(ck2, "Beneficiarios",        str(ben_c),
                     "slate", tip="Número de beneficiarios registrados en este contrato.")
            kpi_card(ck3, "Valor dentro",         fmt_mdp(val_dentro_c),
                     "green", tip="Valor asignado a beneficiarios que ya son clientes de Columbus. Fórmula: Σ(Valor contrato × % benef.) para beneficiarios-clientes.")
            kpi_card(ck4, "Coverage",             f"{cov_c:.1%}",
                     coverage_color_cls(cov_c), tip="Porcentaje de beneficiarios de este contrato que ya son clientes de Columbus.")

            st.markdown("<div style='margin-top:12px'></div>", unsafe_allow_html=True)
            st.markdown("**Evolucion patrimonial — ultimos 5 anos**")

            hist = load_history(str(id_cliente_c))
            if not hist.empty:
                hist.columns   = [c.upper() for c in hist.columns]
                hist["MES"]        = pd.to_datetime(hist["MES"],       errors="coerce")
                hist["VALOR_REAL"] = pd.to_numeric(hist["VALOR_REAL"], errors="coerce")
                hist = hist.sort_values("MES")
                fig = go.Figure(go.Scatter(
                    x=hist["MES"], y=hist["VALOR_REAL"],
                    mode="lines+markers",
                    line=dict(color="#1E3A5F", width=2.5),
                    marker=dict(size=5, color="#1E3A5F",
                                line=dict(color="white", width=1.5)),
                    fill="tozeroy", fillcolor="rgba(30,58,95,0.06)",
                    hovertemplate="<b>%{x|%b %Y}</b><br>$%{y:,.0f}<extra></extra>",
                ))
                fig.update_layout(
                    yaxis=dict(tickformat="$,.0f", gridcolor="#F1F5F9"),
                    xaxis=dict(gridcolor="#F1F5F9", dtick="M6", tickformat="%b %Y"),
                    hovermode="x unified", height=250,
                    plot_bgcolor="white", paper_bgcolor="white",
                    font=dict(family="Inter, system-ui, sans-serif", size=12),
                    margin=dict(t=20, b=10, l=0, r=0),
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Sin historial disponible.")

            st.markdown("**Beneficiarios**")
            show = dc[["NOMBRE_BENEFICIARIO","GENERO","PARENTESCO","EDAD_BENEFICIARIO",
                        "PORCENTAJE","VALOR_ASIGNADO","ESTATUS_CLIENTE",
                        "CURP_BENEFICIARIO","CURP_VACIO","TELEFONO","CORREO"]].copy()
            show["CURP_VACIO"] = show["CURP_VACIO"].map({True:"Sin CURP", False:""})
            show = show.rename(columns={
                "NOMBRE_BENEFICIARIO":"Beneficiario","GENERO":"Genero",
                "PARENTESCO":"Parentesco","EDAD_BENEFICIARIO":"Edad",
                "PORCENTAJE":"%","VALOR_ASIGNADO":"Valor asignado",
                "ESTATUS_CLIENTE":"Estatus","CURP_BENEFICIARIO":"CURP",
                "CURP_VACIO":"Sin CURP","TELEFONO":"Telefono","CORREO":"Correo",
            }).sort_values("Valor asignado", ascending=False)

            def _style_ben(row):
                if row.get("Estatus") == "No cliente":
                    return ["background-color:#EFF6FF"] * len(row)
                return [""] * len(row)

            st.dataframe(
                show.style
                    .format({"Valor asignado":"{:,.0f}","%":"{:.1f}","Edad":"{:.0f}"}, na_rep="—")
                    .apply(_style_ben, axis=1),
                use_container_width=True,
                height=min(100 + len(dc) * 38, 380),
                hide_index=True,
            )

# ── TAB 3: Oficinas ───────────────────────────────────────────────────────────
def render_oficinas(b: pd.DataFrame) -> None:
    st.markdown("### Resumen por Oficina")
    st.markdown("""
    <div class="field-def">
      <strong>Coverage generacional:</strong> Porcentaje de beneficiarios de la oficina
      que ya son clientes de Columbus. Un coverage bajo indica mayor exposicion al riesgo
      de salida de capital por transferencia generacional.<br>
      <strong>Sin CURP:</strong> Beneficiarios cuya identidad no ha podido ser verificada
      por falta de CURP registrado.
    </div>""", unsafe_allow_html=True)

    if b.empty:
        st.info("Sin datos con los filtros actuales.")
        return

    agg = (b.groupby("OFICINA", as_index=False)
            .agg(
                CLIENTES         =("ID_CDM",               "nunique"),
                CONTRATOS        =("CONTRATO",              "nunique"),
                BENEFICIARIOS    =("NOMBRE_BENEFICIARIO",   "count"),
                BEN_CLIENTES     =("ES_CLIENTE",            "sum"),
                BEN_NO_CLIENTES  =("ES_CLIENTE",            lambda x: (~x).sum()),
                SIN_CURP         =("CURP_VACIO",            "sum"),
                SIN_CONTACTO     =("CONTACTABLE",           lambda x: (~x).sum()),
                VALOR_CONTRATOS  =("VALOR_CONTRATO_ACTUAL", lambda x:
                                   b.loc[x.index].drop_duplicates("CONTRATO")["VALOR_CONTRATO_ACTUAL"].sum()),
                VALOR_DENTRO     =("VALOR_ASIGNADO",        lambda x:
                                   x[b.loc[x.index,"ES_CLIENTE"]].sum()),
            )
            .assign(COVERAGE=lambda d: d["BEN_CLIENTES"] / d["BENEFICIARIOS"].replace(0, np.nan))
            .sort_values("VALOR_CONTRATOS", ascending=False)
    )

    def _style_oficinas(row):
        cov = row.get("Coverage", 0)
        if pd.isna(cov) or cov < 0.40:
            return ["background-color:#FFF5F5"] * len(row)
        return [""] * len(row)

    show = agg.rename(columns={
        "OFICINA":"Oficina","CLIENTES":"Clientes","CONTRATOS":"Contratos",
        "BENEFICIARIOS":"Beneficiarios","BEN_CLIENTES":"Ben. clientes",
        "BEN_NO_CLIENTES":"Ben. no clientes","SIN_CURP":"Sin CURP",
        "SIN_CONTACTO":"Sin contacto","VALOR_CONTRATOS":"Valor contratos",
        "VALOR_DENTRO":"Valor dentro","COVERAGE":"Coverage",
    })

    st.dataframe(
        show.style
            .format({"Valor contratos":"{:,.0f}","Valor dentro":"{:,.0f}",
                     "Coverage":"{:.1%}"}, na_rep="—")
            .apply(_style_oficinas, axis=1),
        use_container_width=True,
        height=min(120 + len(agg) * 38, 600),
        hide_index=True,
    )

    st.download_button(
        "Exportar tabla de oficinas",
        show.to_csv(index=False).encode("utf-8"),
        "resumen_oficinas.csv", "text/csv",
        key="dl_oficinas",
    )

# ── MAIN ──────────────────────────────────────────────────────────────────────
st.markdown("""
<div style="border-bottom:2px solid #E2E8F0;padding-bottom:14px;margin-bottom:20px">
  <div style="font-size:1.5rem;font-weight:700;color:#0F172A;letter-spacing:-.01em">
    Radar Generacional
  </div>
  <div style="font-size:.84rem;color:#64748B;margin-top:2px">
    Columbus de Mexico &nbsp;·&nbsp; Herramienta de captacion generacional
  </div>
</div>
""", unsafe_allow_html=True)

try:
    raw_df = load_base_data()
except Exception as e:
    st.error(f"Error al conectar con Oracle: {e}")
    st.stop()

benef_df = build_model(raw_df)

if benef_df.empty:
    st.warning("No se encontraron datos.")
    st.stop()

benef_f = sidebar_filters(benef_df)

active_tab = st.session_state.pop("active_tab", 0)

tabs = st.tabs(["Radar", "Detalle Cliente", "Oficinas"])
with tabs[0]: render_radar(benef_f)
with tabs[1]: render_detail(benef_f)
with tabs[2]: render_oficinas(benef_f)

if active_tab > 0:
    st.markdown(
        f"<script>window.parent.document.querySelectorAll('[data-baseweb=\"tab\"]')"
        f"[{active_tab}].click();</script>",
        unsafe_allow_html=True,
    )
