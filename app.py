import re, math, os
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import html
import streamlit.components.v1 as components
import oracledb
from datetime import date
from pathlib import Path
# =========================
#  CONFIG: ORACLE / POSTGRES
# =========================
HOST = st.secrets.get("ORACLE_HOST", os.getenv("ORACLE_HOST", "34.134.141.229"))
PORT = int(st.secrets.get("ORACLE_PORT", os.getenv("ORACLE_PORT", "1522")))
SID  = st.secrets.get("ORACLE_SID",  os.getenv("ORACLE_SID",  "DESA2"))
USER = st.secrets.get("ORACLE_USER", os.getenv("ORACLE_USER", "HUB_USER"))
PWD  = st.secrets.get("ORACLE_PWD",  os.getenv("ORACLE_PWD",  ""))

PG_HOST = st.secrets.get("PG_HOST", os.getenv("PG_HOST", "34.134.141.229"))
PG_PORT = int(st.secrets.get("PG_PORT", os.getenv("PG_PORT", "6543")))
PG_DB   = st.secrets.get("PG_DB",   os.getenv("PG_DB",   "columbus_databroker_prod"))
PG_USER = st.secrets.get("PG_USER", os.getenv("PG_USER", "columbus_databroker_user"))
PG_PWD  = st.secrets.get("PG_PWD",  os.getenv("PG_PWD",  ""))

DEFAULT_ALIAS   = st.secrets.get("DEFAULT_ALIAS", os.getenv("DEFAULT_ALIAS", "UNIB"))
DEFAULT_INFL    = float(st.secrets.get("INFLACION_ANUAL", os.getenv("INFLACION_ANUAL", "0.035")))

# Productos de reporto que deben contabilizarse como RV
REPORTO_RV_PRODUCTS = [144, 149]
REPORTO_RV_CSV = ",".join(str(i) for i in REPORTO_RV_PRODUCTS)

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"

BENCH_FILES = {
    "PIP":    DATA_DIR / "Indices Pip.xlsx",
    "RV":     DATA_DIR / "Indices RV.xlsx",
    "BOLSAS": DATA_DIR / "Indices Bolsas.xlsx",
    "SP":     DATA_DIR / "Indices SP.xlsx",
}
BENCH_MAP_FILE = DATA_DIR / "Mapa_Benchmarks.xlsx"
BENCH_SHEET_DEFAULT = "indices"  # índices

def add_datapoints_to_fig(fig, decimals=1):
    """
    Agrega datapoints arriba de cada punto o barra sin romper Bar / Scatter.
    """
    if fig is None:
        return fig

    for tr in fig.data:
        # =========================
        # BARRAS
        # =========================
        if isinstance(tr, go.Bar):
            if tr.y is not None:
                tr.text = [f"{v:.{decimals}f}%" if v is not None else "" for v in tr.y]
                tr.textposition = "outside"

        # =========================
        # LÍNEAS / SCATTER
        # =========================
        elif isinstance(tr, go.Scatter):
            if tr.y is not None:
                tr.text = [f"{v:.{decimals}f}%" if v is not None else "" for v in tr.y]
                tr.textposition = "top center"

    return fig

def html_escape(s: str) -> str:
    return html.escape(str(s), quote=True)

# =========================
#  PLACEHOLDERS (para linters / Pylance)
# =========================
NOMBRE_CORTO_FOCUS: str = ""  # se sobreescribe en sidebar cuando seleccionas contrato

# Backward-compat: versiones previas llamaban a get_bench_map_rows()
def get_bench_map_rows(bm: pd.DataFrame, alias_cdm: str, nombre_corto_focus: str | None,
                       producto: str | None = None, modo: str | None = None) -> pd.DataFrame:
    """Filtra filas del Mapa_Benchmarks para (alias, contrato) y opcionalmente producto.
    `modo` aquí es el MODO del mapa (p.ej. BLEND / MULTI), NO es 'ANUALIZADO/EFECTIVO'.
    """
    rows = get_bench_rows(bm, alias_cdm, nombre_corto_focus, producto)
    if rows is None or len(rows) == 0:
        return pd.DataFrame()
    if modo:
        m = str(modo).strip().upper()
        if "MODO" in rows.columns:
            rows = rows[rows["MODO"].astype(str).str.upper().eq(m)].copy()
    return rows

# =========================
#  PAGE + CSS
# =========================
st.set_page_config(page_title="Reportes Institucionales", layout="wide")

# Dispara impresión desde el área principal (el botón vive en sidebar)
if st.session_state.get('DO_PRINT'):
    components.html("<script>window.parent.print();</script>", height=0)
    st.session_state['DO_PRINT'] = False


def css_global():
    return """
    <style>

    /* Fuentes (deployment Streamlit mantiene diseño) */
    @import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=Nunito+Sans:wght@300;400;600;700&display=swap');

    :root{
      --bg1:#f8fafc; --bg2:#e5e7eb;
      --ink:#0f172a; --ink-weak:#334155;
      --cardbg: rgba(0,0,0,.03); --cardbd: rgba(0,0,0,.08);
    }

    html, body, .stApp{
      font-family:'Nunito Sans', sans-serif !important;
      color:var(--ink);
      background: linear-gradient(135deg, var(--bg1), var(--bg2));
    }

    h1, h2, h3 {
      font-family:'DM Serif Display', serif !important;
    }

    header[data-testid="stHeader"]{
      background:#ffffff;
      color:var(--ink);
      border-bottom:1px solid var(--cardbd);
    }
    section[data-testid="stSidebar"]{
      color: var(--ink);
      background:#ffffff;
      border-right: 1px solid var(--cardbd);
    }

    .sb-card{
      background: var(--cardbg);
      border:1px solid var(--cardbd);
      border-radius: 14px;
      padding: 12px;
      margin: 8px 0;
    }
    .sb-title{
      font-size:.9rem;
      color:var(--ink);
      letter-spacing:.06em;
      text-transform:uppercase;
      margin-bottom:6px;
    }

    .kpi-grid{
      display:grid;
      grid-template-columns: repeat(5, minmax(0,1fr));
      gap:12px;
      margin: 6px 0 8px 0;
    }
    .kpi-card{
      background: linear-gradient(180deg, rgba(34,197,94,.10), rgba(2,6,23,.00));
      border:1px solid rgba(34,197,94,.25);
      border-radius: 14px;
      padding: 10px 12px;
    }
    .kpi-label{
      font-size:.72rem;
      color:var(--ink-weak);
      letter-spacing:.06em;
      text-transform:uppercase;
    }
    .kpi-value{
      font-size:1.25rem;
      font-weight:800;
      color:var(--ink);
      margin-top:2px;
    }

    .chip{
      display:inline-block;
      padding:.24rem .52rem;
      border-radius:999px;
      margin:2px 6px 8px 0;
      background:linear-gradient(90deg, rgba(124,58,237,.18), rgba(34,211,238,.16));
      border:1px solid rgba(124,58,237,.35);
      font-size:.84rem;
      color:var(--ink);
    }

    .chip-date{
      display:inline-block;
      padding:.24rem .52rem;
      border-radius:999px;
      margin:2px 6px 8px 0;
      background:rgba(30,58,138,.08);
      border:1px solid rgba(30,58,138,.55);
      font-size:.84rem;
      color:#1e3a8a;
      font-weight:600;
    }

    /* =========================
       TABLAS EN PANTALLA
       ========================= */

    /* Encabezados centrados en st.dataframe */
    [data-testid="stDataFrame"] div[role="columnheader"],
    [data-testid="stDataFrame"] div[role="columnheader"] *{
      text-align: center !important;
      justify-content: center !important;
      align-items: center !important;
    }

    /* Celdas y encabezados (todas las tablas st.dataframe en pantalla) */
    [data-testid="stDataFrame"] div[role="gridcell"],
    [data-testid="stDataFrame"] div[role="columnheader"]{
      font-size: 12px !important;
      line-height: 1.3 !important;
      padding: 4px 8px !important;
      white-space: nowrap !important;
      overflow: hidden !important;
      text-overflow: ellipsis !important;
    }

    /* Tablas HTML generadas por pandas (tiny_table_print, etc.) */
    table.dataframe th,
    table.dataframe td{
      text-align: center !important;
      padding: 4px 8px !important;
      white-space: nowrap !important;
      overflow: hidden !important;
      text-overflow: ellipsis !important;
      font-size: 11px !important;
    }

    /* TABLA DETALLE DEUDA — compacta (se mantiene igual) */
    .deuda-detail-table [data-testid="stDataFrame"] div[role="columnheader"],
    .deuda-detail-table [data-testid="stDataFrame"] div[role="gridcell"]{
      font-size: 8px !important;
      line-height: 1.05 !important;
      padding: 1px 3px !important;
    }

    /* TABLA DEUDA RESUMEN (semaforo de riesgo) compacta */
    .deuda-resumen-table table,
    .deuda-resumen-table table.dataframe{
      border-collapse: collapse !important;
      width: auto !important;
    }
    .deuda-resumen-table th,
    .deuda-resumen-table td{
      font-size: 9px !important;
      padding: 2px 4px !important;
      text-align: center !important;
      white-space: nowrap !important;
      overflow: hidden !important;
      text-overflow: ellipsis !important;
    }

    /* Clase para forzar salto de página explícito */
    @media print {
      .page-break-after{
        page-break-after: always;
      }
    }

    /* =========================
       VISTA IMPRESIÓN
       ========================= */
    @media print {
      @page { size: letter landscape; margin: 0.45in; }
      body, .stApp{
        background:#ffffff !important;
        -webkit-print-color-adjust: exact !important;
        print-color-adjust: exact !important;
      }

      [data-testid="stSidebar"],
      [data-testid="stToolbar"],
      [data-testid="stStatusWidget"]{
        display: none !important;
      }

      .tabs-normal { display: none !important; }
      .print-container { display: block !important; }
      .block-container { padding: 0 !important; }

      h1, h2, h3{
        margin-top: 0.25in !important;
        page-break-after: avoid;
        page-break-before: avoid;
      }

      .element-container,
      .plotly,
      .stPlotlyChart,
      [data-testid="stDataFrame"]{
        break-inside: avoid;
      }

      /* TABLAS st.dataframe en impresión: fuente 18 */
      [data-testid="stDataFrame"]{
        page-break-after: always !important;
        break-after: always !important;
      }

      [data-testid="stDataFrame"] div[role="columnheader"],
      [data-testid="stDataFrame"] div[role="gridcell"]{
        font-size: 18px !important;
        line-height: 1.2 !important;
        padding: 4px 8px !important;
        text-align: center !important;
        justify-content: center !important;
        align-items: center !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
      }

      /* Tablas HTML (tiny_table_print) en impresión: fuente 18 + salto de página */
      .table-print{
        page-break-after: always !important;
        break-after: always !important;
      }

      .table-print table.dataframe th,
      .table-print table.dataframe td{
        font-size: 18px !important;
        line-height: 1.2 !important;
        padding: 4px 8px !important;
        text-align: center !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
      }

      /* DETALLE DEUDA — se mantiene compacto también al imprimir */
      .deuda-detail-table [data-testid="stDataFrame"] div[role="columnheader"],
      .deuda-detail-table [data-testid="stDataFrame"] div[role="gridcell"]{
        font-size: 8px !important;
        line-height: 1.0 !important;
        padding: 1px 3px !important;
      }

      /* TABLA DEUDA RESUMEN compacta al imprimir (solo tamaño, sin romper la lógica anterior) */
      .deuda-resumen-table th,
      .deuda-resumen-table td{
        font-size: 9px !important;
        padding: 2px 3px !important;
      }

      /* OCULTAR SELECTORES EN IMPRESIÓN */
      [data-testid="stWidget"],
      [data-testid="stSelectbox"],
      [data-testid="stMultiSelect"],
      [data-testid="stRadio"],
      [data-testid="stSlider"],
      [data-testid="stDateInput"],
      [data-testid="stNumberInput"],
      [data-testid="stTextInput"],
      [data-testid="stForm"],
      .stSelectbox,
      .stMultiSelect,
      .stRadio,
      .stSlider,
      .stDateInput,
      .stNumberInput,
      .stTextInput,
      [role="radiogroup"],
      [role="combobox"],
      input[type="checkbox"],
      input[type="radio"],
      select,
      textarea{
        display: none !important;
      }

      .page-break {
        page-break-after: always !important;
        break-after: always !important;
      }

      /* Cada sección de pestaña grande (AA, Deuda, RV) en página nueva */
      .print-section{
        page-break-before: always !important;
        break-before: always !important;
      }
          /* === BLOQUE IMPRESIÓN: título + gráfica NO se separan === */
      .print-block{
        break-inside: avoid !important;
        page-break-inside: avoid !important;
        margin: 0 0 10px 0 !important;
      }
      .print-title{
        font-family:'DM Serif Display', serif !important;
        font-size: 18pt !important;
        font-weight: 600 !important;
        margin: 0 0 8px 0 !important;
        page-break-after: avoid !important;
        break-after: avoid !important;
      }

      /* Plotly: tamaño real legible */
      .stPlotlyChart, .js-plotly-plot, .plotly{
        width: 100% !important;
        height: auto !important;
        break-inside: avoid !important;
        page-break-inside: avoid !important;
      }

      /* Salto de página después de cada gráfica (controlado por helper) */
      .page-break{
        page-break-after: always !important;
        break-after: always !important;
      }
    }
    
  /* --- Benchmark ficha: lista con wrap --- */
  .bench-ficha-items{display:flex;flex-direction:column;gap:.25rem;margin-top:.25rem;}
  .bench-item{display:flex;align-items:flex-start;gap:.5rem;}
  .bench-name{white-space:normal;overflow-wrap:anywhere;line-height:1.25;}
  .bench-ficha-muted{opacity:.7;font-size:.95rem;}
    </style>
    """

st.markdown(css_global(), unsafe_allow_html=True)

# Helper para tablas mini en impresión (con bordes + salto de página al final)
def tiny_table_print(df: pd.DataFrame):
    html = df.to_html(index=False, border=0, classes="dataframe")
    st.markdown(f'<div class="table-print">{html}</div>', unsafe_allow_html=True)

def _month_end_from_anio_mes(df: pd.DataFrame, anio_col="ANIO", mes_col="MES", out_col="FECHA") -> pd.DataFrame:
    d = df.copy()
    d[anio_col] = pd.to_numeric(d[anio_col], errors="coerce")
    d[mes_col] = pd.to_numeric(d[mes_col], errors="coerce")
    d = d.dropna(subset=[anio_col, mes_col]).copy()

    dt = pd.to_datetime(
        d[anio_col].astype(int).astype(str) + "-" + d[mes_col].astype(int).astype(str).str.zfill(2) + "-01",
        errors="coerce"
    )
    d[out_col] = (dt + pd.offsets.MonthEnd(0)).dt.normalize()
    return d

def _get_cutoff_month_end() -> pd.Timestamp:
    """Cierre de mes según parámetros aplicados del sidebar (Y_APPLIED/M_APPLIED)."""
    hoy = date.today()
    y = int(st.session_state.get("Y_APPLIED", hoy.year))
    m = int(st.session_state.get("M_APPLIED", hoy.month))
    return (pd.Timestamp(y, m, 1) + pd.offsets.MonthEnd(0)).normalize()

def _fix_month_end_shift_if_needed(
    d: pd.DataFrame,
    end_ref: pd.Timestamp,
    date_col: str = "FECHA"
) -> pd.DataFrame:
    """
    Si la serie mensual viene 1 mes adelantada (max(FECHA) > end_ref ~ 1 mes),
    corrige restando 1 cierre de mes a toda la serie.
    """
    if d is None or d.empty or date_col not in d.columns:
        return d

    out = d.copy()
    out[date_col] = pd.to_datetime(out[date_col], errors="coerce")
    out = out.dropna(subset=[date_col])
    if out.empty:
        return d

    max_fecha = out[date_col].max()
    end_ref = pd.to_datetime(end_ref, errors="coerce")

    if pd.isna(end_ref):
        return d

    # si viene 1 mes adelantado (típico: 28-31 días)
    delta_days = (max_fecha - end_ref).days
    if delta_days >= 20 and delta_days <= 40:
        out[date_col] = (out[date_col] - pd.offsets.MonthEnd(1)).dt.normalize()
        return out

    return d

def _month_end_spine(end_ref: pd.Timestamp, n: int = 12) -> pd.DatetimeIndex:
    """Espina de cierres de mes (month-end) que termina en `end_ref` (incluye `end_ref`)."""
    end_ref = pd.to_datetime(end_ref, errors="coerce")
    if pd.isna(end_ref):
        end_ref = (pd.Timestamp.today() + pd.offsets.MonthEnd(0)).normalize()
    end_ref = (end_ref + pd.offsets.MonthEnd(0)).normalize()
    return pd.date_range(end=end_ref, periods=int(n), freq="M").normalize()


def _reindex_to_month_spine(df: pd.DataFrame, spine: pd.DatetimeIndex, date_col: str = "FECHA") -> pd.DataFrame:
    """Normaliza `date_col` a cierre de mes y reindexa a `spine` (mantiene columnas)."""
    out = df.copy()
    out[date_col] = pd.to_datetime(out[date_col], errors="coerce")
    out = out.dropna(subset=[date_col]).copy()
    out[date_col] = (out[date_col] + pd.offsets.MonthEnd(0)).dt.normalize()
    out = out.sort_values(date_col)
    out = out.drop_duplicates(subset=[date_col], keep="last")
    out = out.set_index(date_col).reindex(spine).reset_index().rename(columns={"index": date_col})
    return out


def _clip_monthly_df(df: pd.DataFrame, end_ref: pd.Timestamp, date_col: str = "FECHA") -> pd.DataFrame:
    """Recorta a `<= end_ref` (cierre de mes) y normaliza fecha."""
    out = df.copy()
    out[date_col] = pd.to_datetime(out[date_col], errors="coerce")
    out = out.dropna(subset=[date_col]).copy()
    end_ref = (pd.to_datetime(end_ref) + pd.offsets.MonthEnd(0)).normalize()
    out[date_col] = (out[date_col] + pd.offsets.MonthEnd(0)).dt.normalize()
    return out[out[date_col] <= end_ref].copy()

def _style_time_xaxis(fig: go.Figure, n_points: int, print_mode: bool):
    """
    FIX definitivo para gráficas mensuales:
    - Bloquea ticks exactamente a los meses existentes en los datos
    - Bloquea el rango para que Plotly NO muestre el mes siguiente (ej. agosto)
    """

    # rotación
    angle = 45 if (n_points > 8 or (print_mode and n_points > 6)) else 0

    # --- recolecta todos los X de todos los traces ---
    xs = []
    for tr in fig.data:
        try:
            if getattr(tr, "x", None) is not None:
                xs.extend(list(tr.x))
        except Exception:
            pass

    xdt = pd.to_datetime(pd.Series(xs), errors="coerce").dropna()
    if xdt.empty:
        # fallback
        fig.update_xaxes(
            tickformat="%b-%Y",
            tickangle=angle,
            tickmode="auto",
            nticks=6,
            showgrid=True,
            ticks="outside",
            title=None
        )
        return

    # normaliza a cierre de mes y ordena
    xuniq = (
        pd.to_datetime(pd.Index(xdt.unique()))
        .to_period("M").to_timestamp("M")
        .sort_values()
    )

    tickvals = xuniq.tolist()
    ticktext = [d.strftime("%b-%y") for d in xuniq]

    # rango EXACTO (pequeño padding visual para que no corte)
    pad_days = 12 if n_points <= 10 else 16
    x_min = xuniq.min() - pd.Timedelta(days=pad_days)
    x_max = xuniq.max() + pd.Timedelta(days=pad_days)


    fig.update_xaxes(
        type="date",
        tickmode="array",
        tickvals=tickvals,
        ticktext=ticktext,
        range=[x_min, x_max],
        tickangle=angle,
        showgrid=True,
        ticks="outside",
        title=None
    )

def _style_fig_for_mode(fig: go.Figure, print_mode: bool):
    """Aplica estilos base y etiquetas de datos (1 decimal) a las gráficas."""
    fig.update_layout(
        height=420 if not print_mode else 380,
        margin=dict(l=40, r=20, t=50, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )

    # Puntos + etiquetas
    try:
        fig.update_traces(
            selector=dict(type="scatter"),
            mode="lines+markers+text",
            texttemplate="%{y:.1f}%",
            hovertemplate="%{y:.2f}%<extra></extra>",
        )
    except Exception:
        pass

    try:
        fig.update_traces(
            selector=dict(type="bar"),
            texttemplate="%{y:.1f}%",
            hovertemplate="%{y:.2f}%<extra></extra>",
        )
    except Exception:
        pass

        # ✅ Headroom para que no se corte el texto fuera de las barras
    try:
        # si el usuario ya fijó un range, no lo tocamos
        yr = getattr(fig.layout.yaxis, "range", None)
        if not yr:
            y_vals = []
            for tr in fig.data:
                if getattr(tr, "type", None) == "bar" and getattr(tr, "y", None) is not None:
                    y_vals.extend(list(tr.y))

            y_ser = pd.to_numeric(pd.Series(y_vals), errors="coerce").dropna()
            if not y_ser.empty:
                ymin = float(y_ser.min())
                ymax = float(y_ser.max())

                # padding arriba (10%) + un mínimo visual
                pad = max(abs(ymax) * 0.10, 0.5)

                if ymin >= 0:
                    fig.update_yaxes(range=[0, ymax + pad])
                else:
                    fig.update_yaxes(range=[ymin - pad, ymax + pad])
    except Exception:
        pass

        # ✅ HEADROOM: evita que se corte el texto cuando la barra llega arriba
    try:
        y_vals = []
        for tr in fig.data:
            if getattr(tr, "type", None) == "bar" and getattr(tr, "y", None) is not None:
                y_vals.extend(list(tr.y))
        y_ser = pd.to_numeric(pd.Series(y_vals), errors="coerce").dropna()

        if not y_ser.empty:
            ymin = float(y_ser.min())
            ymax = float(y_ser.max())

            # padding (8% arriba). Si todo es positivo, ancla en 0.
            pad = (abs(ymax) * 0.08) if ymax != 0 else 1.0

            if ymin >= 0:
                fig.update_yaxes(range=[0, ymax + pad])
            else:
                fig.update_yaxes(range=[ymin - pad, ymax + pad])
    except Exception:
        pass

    fig.update_layout(uniformtext_minsize=10, uniformtext_mode="hide")
    return fig


def render_print_block(title: str, fig: go.Figure, print_mode: bool, break_after: bool = True, footer_md: str | None = None):
    """
    - En impresión: título + gráfica juntos + salto de página después
    - En normal: st.subheader + chart
    """
    if print_mode:
        st.markdown(f'<div class="print-block"><div class="print-title">{title}</div>', unsafe_allow_html=True)
        add_datapoints_to_fig(fig, decimals=1)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        if footer_md:
            st.markdown(footer_md)
        st.markdown('</div>', unsafe_allow_html=True)
        if break_after:
            st.markdown('<div class="page-break"></div>', unsafe_allow_html=True)
    else:
        st.subheader(title)
        add_datapoints_to_fig(fig, decimals=1)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# =========================
#  HELPER: CONTRATOS POR ALIAS
# =========================
@st.cache_data(ttl=600, show_spinner=False)
def get_contratos_por_alias(alias: str) -> pd.DataFrame:
    """
    Regresa un DataFrame con los contratos del alias:
    - ID_CLIENTE
    - NOMBRE_CORTO

    Se usa para poblar el multiselect de 'Contrato' mostrando NOMBRE_CORTO,
    pero la lógica interna sigue trabajando con ID_CLIENTE.
    """
    alias = (alias or "").strip()
    if not alias or not PWD:
        return pd.DataFrame(columns=["ID_CLIENTE", "NOMBRE_CORTO"])

    try:
        dsn = oracledb.makedsn(HOST, PORT, sid=SID)
        conn = oracledb.connect(user=USER, password=PWD, dsn=dsn)
        df = pd.read_sql(
            """
            SELECT DISTINCT ID_CLIENTE, NOMBRE_CORTO
            FROM SIAPII.V_M_CONTRATO_CDM
            WHERE ALIAS_CDM = :alias
            ORDER BY NOMBRE_CORTO
            """,
            conn,
            params={"alias": alias},
        )
        conn.close()
    except Exception:
        return pd.DataFrame(columns=["ID_CLIENTE", "NOMBRE_CORTO"])

    df["ID_CLIENTE"] = df["ID_CLIENTE"].astype("Int64")
    df["NOMBRE_CORTO"] = df["NOMBRE_CORTO"].fillna("").astype(str)
    return df

# =========================
#  SIDEBAR (parámetros)
# =========================
hoy = date.today()

# ---- Defaults de session_state (una sola vez) ----
st.session_state.setdefault("ALIAS_APPLIED", DEFAULT_ALIAS)
st.session_state.setdefault("Y_APPLIED", hoy.year)
st.session_state.setdefault("M_APPLIED", hoy.month)
st.session_state.setdefault("INFL_APPLIED", DEFAULT_INFL)
st.session_state.setdefault("CONTRATOS_APPLIED", [])            # IDs
st.session_state.setdefault("CONTRATOS_LABELS_APPLIED", [])     # Labels (NOMBRE_CORTO)
st.session_state.setdefault("NOMBRE_CORTO_FOCUS", "")           # Label foco (aplicado)
st.session_state.setdefault("PRINT_MODE", False)

# ---- Sidebar UI ----
with st.sidebar:
    st.markdown(
        """
        <div class="sb-card">
          <div class="sb-title">Parámetros del reporte</div>
        """,
        unsafe_allow_html=True,
    )

    # (A) Modo impresión (no depende del submit)
    print_mode = st.checkbox(
        "Modo impresión",
        value=bool(st.session_state.get("PRINT_MODE", False)),
        help="Optimiza el diseño para imprimir o exportar a PDF (fondo blanco, márgenes y tipografías).",
    )
    st.session_state["PRINT_MODE"] = print_mode

    # (B) Form con “Aplicar”
    with st.form("param_form", clear_on_submit=False):
        alias_input = st.text_input(
            "Cliente (ALIAS_CDM)",
            value=str(st.session_state.get("ALIAS_APPLIED", DEFAULT_ALIAS)),
            help="Alias del cliente tal como viene en V_M_CONTRATO_CDM (ALIAS_CDM).",
        ).strip().upper()

        # Traer contratos del alias escrito (labels + ids)
        df_ctos = get_contratos_por_alias(alias_input)

        if df_ctos.empty:
            opciones_labels = []
            label_to_id = {}
        else:
            df_ctos = df_ctos.copy()
            df_ctos["NOMBRE_CORTO"] = df_ctos["NOMBRE_CORTO"].astype(str)
            df_ctos["ID_CLIENTE"] = df_ctos["ID_CLIENTE"].astype(int)

            opciones_labels = df_ctos["NOMBRE_CORTO"].tolist()
            label_to_id = dict(zip(df_ctos["NOMBRE_CORTO"], df_ctos["ID_CLIENTE"]))

        # Defaults del multiselect basados en LO APLICADO
        applied_labels = st.session_state.get("CONTRATOS_LABELS_APPLIED", [])
        applied_ids = st.session_state.get("CONTRATOS_APPLIED", [])

        # Reconstruir labels desde IDs si cambió el alias o no hay labels guardados
        ids_to_label = {v: k for k, v in label_to_id.items()}
        if (not applied_labels) and applied_ids:
            applied_labels = [ids_to_label[i] for i in applied_ids if i in ids_to_label]

        # Si no hay nada aplicado válido, default = todos los del alias
        default_labels = [l for l in applied_labels if l in opciones_labels] if applied_labels else opciones_labels

        contrato_sel_labels = st.multiselect(
            "Contrato",
            options=opciones_labels,
            default=default_labels,
            help="Selecciona uno o varios contratos (NOMBRE_CORTO).",
        )

        coly, colm = st.columns(2)
        with coly:
            y_input = st.number_input(
                "Año",
                min_value=2000,
                max_value=2100,
                value=int(st.session_state.get("Y_APPLIED", hoy.year)),
                step=1,
            )
        with colm:
            m_input = st.number_input(
                "Mes",
                min_value=1,
                max_value=12,
                value=int(st.session_state.get("M_APPLIED", hoy.month)),
                step=1,
            )

        infl_input = st.number_input(
            "Inflación anual (dec)",
            min_value=0.0,
            max_value=1.0,
            value=float(st.session_state.get("INFL_APPLIED", DEFAULT_INFL)),
            step=0.001,
            format="%.3f",
        )

        aplicar = st.form_submit_button("Actualizar")

        if aplicar:
            # Guardar “aplicado”
            st.session_state["ALIAS_APPLIED"] = alias_input or DEFAULT_ALIAS
            st.session_state["Y_APPLIED"] = int(y_input)
            st.session_state["M_APPLIED"] = int(m_input)
            st.session_state["INFL_APPLIED"] = float(infl_input)

            # Convertir labels → IDs aplicados
            contrato_sel_ids = [label_to_id[l] for l in contrato_sel_labels if l in label_to_id]

            # Si no seleccionan nada => todos
            if contrato_sel_ids:
                st.session_state["CONTRATOS_APPLIED"] = contrato_sel_ids
                st.session_state["CONTRATOS_LABELS_APPLIED"] = contrato_sel_labels
            else:
                all_ids = df_ctos["ID_CLIENTE"].dropna().astype(int).tolist() if not df_ctos.empty else []
                st.session_state["CONTRATOS_APPLIED"] = all_ids
                st.session_state["CONTRATOS_LABELS_APPLIED"] = opciones_labels

            # Foco SOLO al aplicar
            st.session_state["NOMBRE_CORTO_FOCUS"] = (
                st.session_state["CONTRATOS_LABELS_APPLIED"][0]
                if st.session_state["CONTRATOS_LABELS_APPLIED"]
                else ""
            )

    st.markdown("</div>", unsafe_allow_html=True)  # cierra sb-card


# =========================
#  PARÁMETROS ACTIVOS (USADOS EN EL REPORTE)
# =========================
ALIAS_CDM = st.session_state.get("ALIAS_APPLIED", DEFAULT_ALIAS)
y = int(st.session_state.get("Y_APPLIED", hoy.year))
m = int(st.session_state.get("M_APPLIED", hoy.month))
INFLACION_ANUAL = float(st.session_state.get("INFL_APPLIED", DEFAULT_INFL))

CONTRATOS_SELECCIONADOS = st.session_state.get("CONTRATOS_APPLIED", [])
CONTRATOS_KEY = tuple(sorted(CONTRATOS_SELECCIONADOS))  # para cache

NOMBRE_CORTO_FOCUS = st.session_state.get("NOMBRE_CORTO_FOCUS", "")

print_mode = bool(st.session_state.get("PRINT_MODE", False))


# =========================
#  FECHAS Y CONSTANTES VISUALES
# =========================
F_DIA_INI = pd.Timestamp(year=y, month=m, day=1)
F_DIA_FIN = F_DIA_INI + pd.offsets.MonthEnd(1)
F_DIA_FIN_NEXT = F_DIA_FIN + pd.Timedelta(days=1)
FECHA_ESTADISTICA = F_DIA_FIN.strftime("%Y-%m-%d")

CHART_H = 360
BARH_H  = 320
TICKANGLE = 0 if print_mode else 45
LEGEND_RIGHT = dict(orientation="v", yanchor="top", y=1.0, xanchor="left", x=1.02)

# =========================
#  BENCHMARKS: LOAD + BUILD
# =========================

import unicodedata

REQUIRED_MAP_COLS = [
    "ALIAS_CDM", "NOMBRE_CORTO", "PRODUCTO",
    "BENCHMARK_LABEL", "FILE_KEY", "SHEET_NAME", "COL_NAME",
    "PESO", "MODO"
]

def _norm_colname(s: str) -> str:
    """
    Normaliza headers del Excel:
    - strip
    - upper
    - sin acentos
    - espacios/guiones -> _
    - colapsa __
    """
    if s is None:
        return ""
    s = str(s).strip()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))  # quita acentos
    s = s.upper()
    for ch in [" ", "-", ".", "/", "\\", "(", ")", "[", "]", "{", "}", ":"]:
        s = s.replace(ch, "_")
    while "__" in s:
        s = s.replace("__", "_")
    return s.strip("_")

def load_bench_map(map_path: Path, sheet_name=None) -> pd.DataFrame:
    """
    Carga Mapa_Benchmarks.xlsx tolerando headers "sucios".
    - Normaliza nombres de columna
    - Acepta sinónimos comunes
    - Luego aplica tus normalizaciones de valores
    """
    _ensure_file(map_path, "Mapa_Benchmarks.xlsx")
    df = pd.read_excel(map_path, sheet_name=sheet_name) if sheet_name else pd.read_excel(map_path)
    df = df.copy()

    # 1) Normaliza headers
    orig_cols = list(df.columns)
    df.columns = [_norm_colname(c) for c in df.columns]

    # 2) Sinónimos / variantes (ajusta aquí si tu archivo usa otros nombres)
    synonyms = {
        # alias / contrato
        "ALIAS": "ALIAS_CDM",
        "ALIASCDM": "ALIAS_CDM",
        "ALIAS_CDM_": "ALIAS_CDM",

        "NOMBRECORTO": "NOMBRE_CORTO",
        "NOMBRE_CORTO_": "NOMBRE_CORTO",
        "CONTRATO": "NOMBRE_CORTO",

        # producto
        "ESTRATEGIA": "PRODUCTO",
        "PRODUCTO_": "PRODUCTO",

        # benchmark
        "BENCHMARK": "BENCHMARK_LABEL",
        "BENCHMARKS": "BENCHMARK_LABEL",
        "BENCHMARK_LABEL_": "BENCHMARK_LABEL",
        "INDICE": "BENCHMARK_LABEL",
        "INDICE_LABEL": "BENCHMARK_LABEL",

        # file
        "ARCHIVO": "FILE_KEY",
        "FILE": "FILE_KEY",
        "FILEKEY": "FILE_KEY",

        # sheet/col
        "HOJA": "SHEET_NAME",
        "SHEET": "SHEET_NAME",
        "SHEETNAME": "SHEET_NAME",

        "COLUMNA": "COL_NAME",
        "COL": "COL_NAME",
        "COLNAME": "COL_NAME",

        # peso/modo
        "WEIGHT": "PESO",
        "PESOS": "PESO",

        "TIPO": "MODO",
    }

    # Aplica synonyms SOLO si la columna destino no existe ya
    rename_map = {}
    for c in df.columns:
        if c in synonyms and synonyms[c] not in df.columns:
            rename_map[c] = synonyms[c]
    if rename_map:
        df = df.rename(columns=rename_map)

    # 3) Valida requeridas
    missing = [c for c in REQUIRED_MAP_COLS if c not in df.columns]
    if missing:
        # Debug útil: muestra qué columnas sí detectó
        raise ValueError(
            "[BENCH] Mapa_Benchmarks no trae columnas requeridas.\n"
            f"Faltan: {missing}\n"
            f"Columnas detectadas (normalizadas): {list(df.columns)}\n"
            f"Columnas originales: {orig_cols}"
        )

    # 4) Normalizaciones de valores (igual que ya tenías)
    df["ALIAS_CDM"] = df["ALIAS_CDM"].apply(_norm_upper)
    df["NOMBRE_CORTO"] = df["NOMBRE_CORTO"].apply(_norm_str)
    df["PRODUCTO"] = df["PRODUCTO"].apply(_norm_str)
    df["BENCHMARK_LABEL"] = df["BENCHMARK_LABEL"].apply(_norm_str)
    df["FILE_KEY"] = df["FILE_KEY"].apply(_norm_upper)
    df["SHEET_NAME"] = df["SHEET_NAME"].apply(_norm_str)
    df["COL_NAME"] = df["COL_NAME"].apply(_norm_str)
    df["MODO"] = df["MODO"].apply(_norm_upper)
    df["PESO"] = pd.to_numeric(df["PESO"], errors="coerce").fillna(0.0)

    return df


def _norm_str(x):
    return "" if pd.isna(x) else str(x).strip()

def _norm_upper(x):
    return _norm_str(x).upper()

def _ensure_file(path: Path, label: str):
    if path is None:
        raise FileNotFoundError(f"[BENCH] Path None para {label}")
    if not Path(path).exists():
        raise FileNotFoundError(f"[BENCH] No existe el archivo {label}: {path}")

def _read_index_file(file_path: Path, sheet_name: str):
    """
    Lee archivo de índices (xlsx/xlsb) y devuelve DF con:
      - columna 'FECHA' (datetime)
      - columnas de índices numéricas (float)
    """
    _ensure_file(file_path, f"bench file {file_path.name}")

    suffix = file_path.suffix.lower()

    if suffix == ".xlsb":
        df = pd.read_excel(file_path, sheet_name=sheet_name, engine="pyxlsb")
    else:
        df = pd.read_excel(file_path, sheet_name=sheet_name)

    if df.shape[1] < 2:
        raise ValueError(f"[BENCH] Hoja {sheet_name} en {file_path.name} no tiene columnas suficientes.")

    # Primera columna es FECHA (diaria)
    fecha_col = df.columns[0]
    df = df.rename(columns={fecha_col: "FECHA"}).copy()
    df["FECHA"] = pd.to_datetime(df["FECHA"], errors="coerce")
    df = df.dropna(subset=["FECHA"]).sort_values("FECHA")
    df = df.drop_duplicates(subset=["FECHA"], keep="last")

    # Convertir columnas de índices a numérico
    for c in df.columns[1:]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    return df

def get_bench_rows(df_map: pd.DataFrame, alias_cdm: str, nombre_corto: str, producto: str | None = None) -> pd.DataFrame:
    """
    Filtra filas del mapa para un contrato (ALIAS_CDM + NOMBRE_CORTO) y opcional PRODUCTO.
    - Si producto es None: trae todas las filas del contrato (útil para benchmark de portafolio).
    - Si producto se pasa: filtra por ese producto.
    """
    alias_u = _norm_upper(alias_cdm)
    nombre = _norm_str(nombre_corto)

    sub = df_map[(df_map["ALIAS_CDM"] == alias_u) & (df_map["NOMBRE_CORTO"] == nombre)].copy()

    if producto is not None:
        prod = _norm_str(producto)
        sub = sub[sub["PRODUCTO"] == prod].copy()

    return sub

def build_benchmark_series(df_map_rows: pd.DataFrame, bench_files: dict) -> pd.DataFrame:
    """
    Construye serie benchmark (compuesta por pesos) a partir de las filas del mapa ya filtradas.
    Devuelve DF:
      FECHA, BENCH (compuesto), y columnas individuales opcionales (por BENCHMARK_LABEL)
    """
    if df_map_rows.empty:
        return pd.DataFrame(columns=["FECHA", "BENCH"])

    # Validación: FILE_KEY debe existir en BENCH_FILES
    missing_keys = sorted(set(df_map_rows["FILE_KEY"]) - set([k.upper() for k in bench_files.keys()]))
    if missing_keys:
        raise KeyError(f"[BENCH] FILE_KEY no existe en BENCH_FILES: {missing_keys}")

    # Cargar archivos necesarios (cacheable por archivo+hoja)
    # Nota: aquí lo hacemos simple. En Streamlit, cachea _read_index_file.
    loaded = {}  # (FILE_KEY, SHEET_NAME) -> DF indices

    parts = []
    for _, r in df_map_rows.iterrows():
        file_key = _norm_upper(r["FILE_KEY"])
        sheet = _norm_str(r["SHEET_NAME"]) or "indices"
        col = _norm_str(r["COL_NAME"])
        label = _norm_str(r["BENCHMARK_LABEL"]) or col
        peso = float(r["PESO"])

        file_path = bench_files[file_key] if file_key in bench_files else bench_files[file_key.upper()]
        k = (file_key, sheet)

        if k not in loaded:
            loaded[k] = _read_index_file(Path(file_path), sheet)

        df_idx = loaded[k]

        if col not in df_idx.columns:
            # A veces el encabezado trae espacios raros: intentamos match por strip
            cols_strip = {str(c).strip(): c for c in df_idx.columns}
            if col in cols_strip:
                col_real = cols_strip[col]
            else:
                raise KeyError(
                    f"[BENCH] COL_NAME '{col}' no existe en {file_key}:{Path(file_path).name} hoja '{sheet}'. "
                    f"Ejemplo columnas: {list(df_idx.columns)[:8]}"
                )
        else:
            col_real = col

        tmp = df_idx[["FECHA", col_real]].rename(columns={col_real: label}).copy()
        tmp[label] = tmp[label].astype(float)
        tmp["_PESO_"] = peso
        tmp["_LABEL_"] = label
        parts.append(tmp)

    # Unir por FECHA todas las series individuales
    # Creamos un DF master con fechas
    df_all = None
    for tmp in parts:
        label = tmp["_LABEL_"].iloc[0]
        tmp2 = tmp[["FECHA", label]].copy()
        df_all = tmp2 if df_all is None else df_all.merge(tmp2, on="FECHA", how="outer")

    df_all = df_all.sort_values("FECHA")

    # Cálculo del BENCH compuesto por pesos:
    # - Si hay MULTI con varias líneas 100, se suman (equivalente a promediar o sumar? -> aquí blend por pesos)
    # - Si pesos no suman 100, normalizamos por suma de pesos > 0.
    weights = {}
    for _, r in df_map_rows.iterrows():
        label = _norm_str(r["BENCHMARK_LABEL"]) or _norm_str(r["COL_NAME"])
        weights[label] = weights.get(label, 0.0) + float(r["PESO"])

    # normaliza pesos
    total_w = sum(w for w in weights.values() if w > 0)
    if total_w <= 0:
        # si todo viene en 0 (error de mapa), devolvemos vacío
        df_all["BENCH"] = np.nan
        return df_all[["FECHA", "BENCH"]]

    for k in list(weights.keys()):
        weights[k] = weights[k] / total_w

    # BENCH = suma(w_i * serie_i)
    bench = None
    for label, w in weights.items():
        if label not in df_all.columns:
            # por si label era col_name pero en df_all se guardó con BENCHMARK_LABEL
            continue
        s = df_all[label]
        bench = (s * w) if bench is None else (bench + s * w)

    df_all["BENCH"] = bench

    return df_all[["FECHA", "BENCH"] + [c for c in df_all.columns if c not in ["FECHA", "BENCH"]]]

def _is_portafolio_total(x: str) -> bool:
    return str(x or "").strip().upper() == "PORTAFOLIO TOTAL"

def build_bench_pack_from_map(
    bench_map_df: pd.DataFrame,
    alias_cdm: str,
    nombre_corto: str,
    producto: str | None,
    bench_files: dict,
) -> pd.DataFrame:
    """
    Devuelve DF mensual a cierre de mes con:
      FECHA (month-end), ANIO, MES, BENCH_M, BENCH_YTD, BENCH_M_ANUAL, BENCH_YTD_ANUAL

    producto:
      - None => usa SOLO filas del mapa con PRODUCTO tipo 'PORTAFOLIO TOTAL'
      - str  => usa SOLO filas del mapa con PRODUCTO = <producto> (y excluye portafolio total)
    """

    def _is_portafolio_total(x: str) -> bool:
        s = str(x).strip().upper()
        return s in ("PORTAFOLIO TOTAL", "PORTAFOLIO", "TOTAL", "TOTAL PORTAFOLIO")

    # base checks
    if bench_map_df is None or bench_map_df.empty:
        return pd.DataFrame(columns=["FECHA","ANIO","MES","BENCH_M","BENCH_YTD","BENCH_M_ANUAL","BENCH_YTD_ANUAL"])

    a = str(alias_cdm).strip().upper()
    nc = str(nombre_corto).strip()

    dfm = bench_map_df.copy()

    # normaliza columnas relevantes
    for c in ["ALIAS_CDM", "NOMBRE_CORTO", "PRODUCTO", "FILE_KEY", "SHEET_NAME", "COL_NAME", "MODO"]:
        if c in dfm.columns:
            dfm[c] = dfm[c].astype(str).str.strip()

    if "ALIAS_CDM" in dfm.columns:
        dfm["ALIAS_CDM"] = dfm["ALIAS_CDM"].str.upper()
    if "FILE_KEY" in dfm.columns:
        dfm["FILE_KEY"] = dfm["FILE_KEY"].str.upper()
    if "MODO" in dfm.columns:
        dfm["MODO"] = dfm["MODO"].str.upper()

    # 1) filtra por alias + nombre_corto
    rows = dfm[(dfm["ALIAS_CDM"] == a) & (dfm["NOMBRE_CORTO"] == nc)].copy()
    if rows.empty:
        return pd.DataFrame(columns=["FECHA","ANIO","MES","BENCH_M","BENCH_YTD","BENCH_M_ANUAL","BENCH_YTD_ANUAL"])

    # 2) filtra por producto según regla
    if producto is None:
        rows = rows[rows["PRODUCTO"].apply(_is_portafolio_total)].copy()
    else:
        prod_u = str(producto).strip().upper()
        rows = rows[~rows["PRODUCTO"].apply(_is_portafolio_total)].copy()
        rows["__PROD_U__"] = rows["PRODUCTO"].astype(str).str.strip().str.upper()
        rows = rows[rows["__PROD_U__"] == prod_u].copy()
        rows = rows.drop(columns=["__PROD_U__"], errors="ignore")

    # ===============================
    # BENCH_LABEL (post-filtro producto)
    # ===============================
    def _compact_label(labels, max_len=42):
        labels = [str(x).strip() for x in labels if str(x).strip().lower() != "nan"]
        labels = list(dict.fromkeys(labels))  # unique, mantiene orden
        if not labels:
            return "Benchmark"
        if len(labels) == 1:
            return labels[0]
        txt = " + ".join(labels)
        if len(txt) <= max_len:
            return txt
        return f"{labels[0]} + {len(labels)-1} más"

    if "BENCHMARK_LABEL" in rows.columns:
        labs = rows["BENCHMARK_LABEL"].astype(str).tolist()
    elif "COL_NAME" in rows.columns:
        labs = rows["COL_NAME"].astype(str).tolist()
    else:
        labs = []

    bench_label = _compact_label(labs)

    # ===============================
    # BENCH_LABEL para leyenda (post-filtro por producto)
    # - Si hay varios benchmarks: mostrar TODOS con su peso
    # ===============================
    def _build_label_with_weights(rows_: pd.DataFrame) -> str:
        if rows_ is None or rows_.empty:
            return "Benchmark"

        # label base
        if "BENCHMARK_LABEL" in rows_.columns:
            lab_ser = rows_["BENCHMARK_LABEL"].astype(str).str.strip()
        elif "COL_NAME" in rows_.columns:
            lab_ser = rows_["COL_NAME"].astype(str).str.strip()
        else:
            lab_ser = pd.Series(["Benchmark"] * len(rows_))

        # pesos
        if "PESO" in rows_.columns:
            w = pd.to_numeric(rows_["PESO"], errors="coerce")
        else:
            w = pd.Series([np.nan] * len(rows_))

        tmp = pd.DataFrame({"lab": lab_ser, "w": w})
        tmp = tmp[tmp["lab"].str.lower().ne("nan") & tmp["lab"].str.len().gt(0)].copy()

        if tmp.empty:
            return "Benchmark"

        # orden por peso desc (si existe), si no, mantiene orden original
        if tmp["w"].notna().any():
            tmp = tmp.sort_values("w", ascending=False)

        parts = []
        for _, r in tmp.iterrows():
            if pd.notna(r["w"]):
                parts.append(f'{r["lab"]} ({r["w"]:.0f}%)')
            else:
                parts.append(f'{r["lab"]}')

        # separador legible en leyenda (sin "+ n más")
        return " · ".join(parts)

    bench_label = _build_label_with_weights(rows)

    if rows.empty:
        return pd.DataFrame(columns=["FECHA","ANIO","MES","BENCH_M","BENCH_YTD","BENCH_M_ANUAL","BENCH_YTD_ANUAL"])

    # 3) validar FILE_KEY exista
    fks = sorted(rows["FILE_KEY"].dropna().astype(str).str.upper().unique().tolist())
    missing_fk = [k for k in fks if k not in bench_files]
    if missing_fk:
        # opcional: loguea warning
        return pd.DataFrame(columns=["FECHA","ANIO","MES","BENCH_M","BENCH_YTD","BENCH_M_ANUAL","BENCH_YTD_ANUAL"])

    # 4) construir niveles diarios compuestos
    bench_levels = build_benchmark_series(rows, bench_files)  # FECHA diaria, BENCH nivel
    if bench_levels is None or bench_levels.empty or "BENCH" not in bench_levels.columns:
        return pd.DataFrame(columns=["FECHA","ANIO","MES","BENCH_M","BENCH_YTD","BENCH_M_ANUAL","BENCH_YTD_ANUAL"])

    b = bench_levels.copy()
    b["FECHA"] = pd.to_datetime(b["FECHA"], errors="coerce")
    b = b.dropna(subset=["FECHA"]).sort_values("FECHA")
    b["MES"] = b["FECHA"].dt.to_period("M").dt.to_timestamp("M")  # month-end

    # 5) último nivel de cada mes (cierre de mes)
    me = (b.groupby("MES", as_index=False)["BENCH"].last()
            .dropna(subset=["BENCH"])
            .sort_values("MES"))

    # 6) rendimientos
    me["BENCH_M"] = me["BENCH"].pct_change()
    me["ANIO"] = me["MES"].dt.year
    me["MES_N"] = me["MES"].dt.month

    first_y = me.groupby("ANIO")["BENCH"].transform("first")
    me["BENCH_YTD"] = (me["BENCH"] / first_y) - 1.0

    # anualizados para toggle
    me["BENCH_M_ANUAL"] = (1.0 + me["BENCH_M"])**12 - 1.0
    me["N_MES_EN_ANIO"] = me.groupby("ANIO").cumcount() + 1
    me["BENCH_YTD_ANUAL"] = (1.0 + me["BENCH_YTD"])**(12.0 / me["N_MES_EN_ANIO"]) - 1.0

    out = me.rename(columns={"MES": "FECHA", "MES_N": "MES"})[
        ["FECHA", "ANIO", "MES", "BENCH_M", "BENCH_YTD", "BENCH_M_ANUAL", "BENCH_YTD_ANUAL"]
    ].copy()

    # asegurar month-end y sin duplicados
    out["FECHA"] = pd.to_datetime(out["FECHA"], errors="coerce")
    out = out.dropna(subset=["FECHA"])
    out["FECHA"] = out["FECHA"].dt.to_period("M").dt.to_timestamp("M")
    out = out.sort_values("FECHA").drop_duplicates(subset=["FECHA"], keep="last")
    out["BENCH_LABEL"] = bench_label
    
    return out

def get_bench_ficha_rows(alias_cdm: str, nombre_corto_focus: str | None, producto: str | None, modo: str | None = None) -> pd.DataFrame:
    """Devuelve las filas del Mapa_Benchmarks para construir la ficha del benchmark.
    - Para contrato (portafolio): producto=None
    - Para producto: producto=<nombre producto>
    """
    try:
        bm = load_bench_map(BENCH_MAP_FILE)
    except Exception:
        return pd.DataFrame()
    return get_bench_map_rows(bm, alias_cdm, nombre_corto_focus, producto, modo)

def calc_kpis_vs_benchmark(
    prod_m: pd.Series,
    prod_ytd: pd.Series,
    bench_m: pd.Series,
    bench_ytd: pd.Series
) -> dict:
    """KPIs comparativos (producto/contrato vs benchmark) en puntos porcentuales."""
    out = {}
    def _last(s: pd.Series):
        s = pd.to_numeric(s, errors="coerce").dropna()
        return None if s.empty else float(s.iloc[-1])
    pm = _last(prod_m); py = _last(prod_ytd)
    bm = _last(bench_m); by = _last(bench_ytd)
    if pm is not None and bm is not None:
        out["m_prod"] = pm * 100.0
        out["m_bench"] = bm * 100.0
        out["m_delta_pp"] = (pm - bm) * 100.0
    if py is not None and by is not None:
        out["ytd_prod"] = py * 100.0
        out["ytd_bench"] = by * 100.0
        out["ytd_delta_pp"] = (py - by) * 100.0
    return out

def render_benchmark_ficha(df_rows: pd.DataFrame, modo: str, title: str = "Benchmark"):
    """Ficha compacta del benchmark (composición) para poner debajo de las gráficas.

    Espera columnas (al menos):
      - NOMBRE_BENCH (o BENCH_NAME)
      - PESO (en %)
      - TIPO (Nivel / Portafolio / Producto) [opcional]
    """
    if df_rows is None or getattr(df_rows, "empty", True):
        return

    df_show = df_rows.copy()

    # Normalizar nombres de columnas
    if "NOMBRE_BENCH" not in df_show.columns and "BENCH_NAME" in df_show.columns:
        df_show["NOMBRE_BENCH"] = df_show["BENCH_NAME"]

    if "PESO" not in df_show.columns:
        df_show["PESO"] = None

    # Header
    st.markdown(f"**{title}**")

    # Lista (wrap natural)
    items = []
    for _, r in df_show.iterrows():
        nombre = str(r.get("NOMBRE_BENCH", "")).strip()
        peso = r.get("PESO", None)
        tipo = str(r.get("TIPO", "")).strip()

        peso_txt = ""
        try:
            if pd.notna(peso):
                peso_txt = f"{float(peso):.1f}% — "
        except Exception:
            pass

        tipo_txt = f" <span style='opacity:.70'>({tipo})</span>" if tipo else ""
        items.append(f"<li><span style='font-weight:600'>{peso_txt}</span>{nombre}{tipo_txt}</li>")

    html = "<ul style='margin-top:.25rem;margin-bottom:.25rem; padding-left:1.2rem'>" + "".join(items) + "</ul>"
    st.markdown(html, unsafe_allow_html=True)

    # Tabla opcional en expander
    with st.expander("Ver detalle de composición", expanded=False):
        df_tab = df_show[[c for c in ["NOMBRE_BENCH", "PESO", "TIPO"] if c in df_show.columns]].copy()
        if "PESO" in df_tab.columns:
            df_tab["PESO"] = df_tab["PESO"].apply(lambda x: "" if pd.isna(x) else f"{float(x):.1f}%")
        st.dataframe(df_tab, use_container_width=True, hide_index=True)


# -------------------------------------------------------------------
#  Benchmark footer (texto bajo gráfica)
# -------------------------------------------------------------------
BENCH_DISCLAIMER_MD = (
    "> **Nota:** En `Mapa_Benchmarks.xlsx`, la columna **MODO** se refiere al tipo de benchmark "
    "(p.ej. **BLEND** / **MULTI**).\n"
    "> La convención **anualizado vs efectivo** se define en el script: "
    "Portafolio y Deuda se presentan **anualizados**, y Renta Variable se presenta **efectiva**."
)

def bench_ficha_to_markdown(df_rows: pd.DataFrame, title: str = "Benchmark", include_disclaimer: bool = True) -> str:
    """Convierte las filas del mapa (BENCHMARK_LABEL + PESO + MODO) a markdown legible.
    Se usa como texto bajo la gráfica (no renderiza tabla, solo texto).
    """
    if df_rows is None or df_rows.empty:
        md = f"**{title}:** _Sin benchmark mapeado_"
        if include_disclaimer:
            md += "\n\n" + BENCH_DISCLAIMER_MD
        return md

    dfp = df_rows.copy()
    # columnas esperadas: BENCHMARK_LABEL, PESO, MODO
    label_col = "BENCHMARK_LABEL" if "BENCHMARK_LABEL" in dfp.columns else None
    if label_col is None:
        # fallback por si se llama distinto
        for c in dfp.columns:
            if "LABEL" in c.upper():
                label_col = c
                break

    if label_col is None:
        md = f"**{title}:** _Benchmark mapeado pero sin columna de label_"
        if include_disclaimer:
            md += "\n\n" + BENCH_DISCLAIMER_MD
        return md

    # arma lista de bullets con peso
    lines = [f"**{title}:**"]
    # MODO (blend/multi) como meta
    modo_val = None
    if "MODO" in dfp.columns:
        vals = dfp["MODO"].dropna().astype(str).unique().tolist()
        if len(vals) == 1:
            modo_val = vals[0]
    if modo_val:
        lines.append(f"- _Modo:_ **{modo_val}**")

    for _, r in dfp.iterrows():
        lab = str(r.get(label_col, "")).strip()
        if not lab:
            continue
        peso = r.get("PESO", None)
        if peso is None or (isinstance(peso, float) and pd.isna(peso)):
            lines.append(f"- {lab}")
        else:
            try:
                p = float(peso)
                lines.append(f"- {lab} — **{p:.0f}%**")
            except Exception:
                lines.append(f"- {lab} — **{peso}**")

    if include_disclaimer:
        lines.append("")
        lines.append(BENCH_DISCLAIMER_MD)

    return "\n".join(lines)

def levels_to_returns(df_levels_m: pd.DataFrame) -> pd.DataFrame:
    """
    Entrada: DF mensual con FECHA, BENCH_LEVEL
    Salida: DF mensual con FECHA y retornos:
      - RET_M: rendimiento mensual simple
      - RET_M_ACUM: acumulado desde inicio
    """
    if df_levels_m is None or df_levels_m.empty:
        return pd.DataFrame(columns=["FECHA", "RET_M", "RET_M_ACUM"])

    df = df_levels_m.copy().sort_values("FECHA")
    df["BENCH_LEVEL"] = pd.to_numeric(df["BENCH_LEVEL"], errors="coerce")
    df = df.dropna(subset=["BENCH_LEVEL"])

    df["RET_M"] = df["BENCH_LEVEL"].pct_change()
    first = df["BENCH_LEVEL"].iloc[0]
    df["RET_M_ACUM"] = df["BENCH_LEVEL"] / first - 1.0

    return df[["FECHA", "RET_M", "RET_M_ACUM"]]

def add_annualized_cols(df: pd.DataFrame, col_month: str, col_acum: str,
                        out_month_ann: str, out_acum_ann: str) -> pd.DataFrame:
    """
    Anualiza:
    - mensual: (1+r)^12 - 1
    - acumulado: (1+R_acum)^(12/n) - 1, donde n es #meses desde inicio
    """
    df = df.copy().sort_values("FECHA")
    df[col_month] = pd.to_numeric(df[col_month], errors="coerce")
    df[col_acum] = pd.to_numeric(df[col_acum], errors="coerce")

    df[out_month_ann] = (1.0 + df[col_month])**12 - 1.0

    n = np.arange(1, len(df) + 1, dtype=float)
    df[out_acum_ann] = (1.0 + df[col_acum])**(12.0 / n) - 1.0

    return df

def benchmark_returns_pack(df_bench_levels: pd.DataFrame) -> pd.DataFrame:
    """
    Convierte niveles diarios del benchmark compuesto a formato 'rendimientos' compatible con Oracle:
      FECHA (cierre de mes),
      TASA, TASA_ACUMULADO,
      TASA_EFECTIVA, TASA_EFECTIVA_ACUMULADO,
      + anualizados
    """
    m_levels = bench_to_month_end_levels(df_bench_levels)
    rets = levels_to_returns(m_levels)

    out = rets.rename(columns={"RET_M": "TASA", "RET_M_ACUM": "TASA_ACUMULADO"}).copy()

    # Compatibilidad: si tu negocio no distingue "efectiva" para bench, igualamos
    out["TASA_EFECTIVA"] = out["TASA"]
    out["TASA_EFECTIVA_ACUMULADO"] = out["TASA_ACUMULADO"]

    # Anualizados (para tu toggle)
    out = add_annualized_cols(out, "TASA", "TASA_ACUMULADO", "TASA_ANUALIZADA", "TASA_ACUM_ANUALIZADA")
    out = add_annualized_cols(out, "TASA_EFECTIVA", "TASA_EFECTIVA_ACUMULADO",
                              "TASA_EFECTIVA_ANUALIZADA", "TASA_EFECTIVA_ACUM_ANUALIZADA")
    return out

def ensure_month_end_fecha(df: pd.DataFrame, anio_col="ANIO", mes_col="MES", fecha_col="FECHA") -> pd.DataFrame:
    df = df.copy()
    if fecha_col in df.columns:
        df[fecha_col] = pd.to_datetime(df[fecha_col], errors="coerce")
        return df

    if anio_col in df.columns and mes_col in df.columns:
        df[anio_col] = pd.to_numeric(df[anio_col], errors="coerce").astype("Int64")
        df[mes_col] = pd.to_numeric(df[mes_col], errors="coerce").astype("Int64")
        d = pd.to_datetime(df[anio_col].astype(str) + "-" + df[mes_col].astype(str).str.zfill(2) + "-01", errors="coerce")
        df[fecha_col] = (d + pd.offsets.MonthEnd(0))
        return df

    raise ValueError("No puedo construir FECHA: falta FECHA o columnas ANIO/MES.")


def _norm_prod_key(x: str) -> str:
    return _norm_str(x).strip().upper()

PORT_TOT_KEY = "PORTAFOLIO TOTAL"

def bench_levels_to_monthly_returns(df_levels: pd.DataFrame) -> pd.DataFrame:
    """
    Entrada: df_levels con FECHA diaria y columnas numéricas (BENCH y/o labels individuales)
    Salida: DF mensual cierre de mes con:
      FECHA (month-end), y para cada serie X:
        X_M   (mensual efectivo)
        X_YTD (acumulado YTD efectivo)
    """
    if df_levels is None or df_levels.empty:
        return pd.DataFrame()

    df = df_levels.copy()
    df["FECHA"] = pd.to_datetime(df["FECHA"], errors="coerce")
    df = df.dropna(subset=["FECHA"]).sort_values("FECHA")

    # columnas numéricas (todas excepto FECHA)
    val_cols = [c for c in df.columns if c != "FECHA"]
    if not val_cols:
        return pd.DataFrame()

    # month-end bucket y último nivel del mes
    df["MES"] = df["FECHA"].dt.to_period("M").dt.to_timestamp("M")  # month-end
    last = df.groupby("MES")[val_cols].last().reset_index().rename(columns={"MES": "FECHA"})
    last = last.dropna(subset=val_cols, how="all").sort_values("FECHA")

    # returns
    out = last[["FECHA"]].copy()
    out["ANIO"] = out["FECHA"].dt.year
    out["MES"]  = out["FECHA"].dt.month

    for c in val_cols:
        # mensual
        out[f"{c}_M"] = last[c].pct_change()

        # YTD
        first_y = last.groupby(last["FECHA"].dt.year)[c].transform("first")
        out[f"{c}_YTD"] = (last[c] / first_y) - 1.0

    return out

def get_bench_rows_scope(
    df_map: pd.DataFrame,
    alias_cdm: str,
    nombre_corto: str,
    producto: str | None
) -> pd.DataFrame:
    """
    - producto == None: trae TODO el contrato (raro, normalmente no lo usamos)
    - producto == 'PORTAFOLIO TOTAL': trae solo esas filas
    - producto == '<nombre producto>': trae solo ese producto
    """
    sub = get_bench_rows(df_map, alias_cdm, nombre_corto, producto=None)
    if sub.empty:
        return sub

    if producto is None:
        return sub

    pkey = _norm_prod_key(producto)
    sub["_PRODKEY_"] = sub["PRODUCTO"].apply(_norm_prod_key)
    return sub[sub["_PRODKEY_"] == pkey].drop(columns=["_PRODKEY_"], errors="ignore")

@st.cache_data(show_spinner=False)
def bench_monthly_pack_cached(
    alias_cdm: str,
    nombre_corto: str,
    producto_scope: str
) -> pd.DataFrame:
    """
    producto_scope:
      - 'PORTAFOLIO TOTAL'  -> benchmark para Resumen (contrato)
      - '<PRODUCTO>'        -> benchmark para rendimientos por producto
    Devuelve DF con FECHA month-end + columnas tipo:
      BENCH_M, BENCH_YTD, <label>_M, <label>_YTD, etc.
    """
    rows = get_bench_rows_scope(bench_map_df, alias_cdm, nombre_corto, producto_scope)
    if rows.empty:
        return pd.DataFrame()

    df_levels = build_benchmark_series(rows, BENCH_FILES)  # FECHA + BENCH + labels individuales
    if df_levels.empty:
        return pd.DataFrame()

    df_pack = bench_levels_to_monthly_returns(df_levels)
    return df_pack

def get_conn():
    if not PWD:
        raise RuntimeError("Falta ORACLE_PWD en secrets o variable de entorno.")
    dsn = oracledb.makedsn(HOST, PORT, sid=SID)
    oracledb.defaults.arraysize = 1000
    oracledb.defaults.prefetchrows = 1000
    return oracledb.connect(user=USER, password=PWD, dsn=dsn)

@st.cache_data(ttl=600, show_spinner=True)

def bench_to_month_end_levels(df_levels: pd.DataFrame) -> pd.DataFrame:
    """Niveles diarios -> niveles a cierre de mes (month-end)."""
    if df_levels is None or df_levels.empty:
        return pd.DataFrame(columns=["FECHA", "LEVEL"])
    df = df_levels.copy()
    df["FECHA"] = pd.to_datetime(df["FECHA"])
    df = df.sort_values("FECHA")
    df["FECHA_ME"] = df["FECHA"] + pd.offsets.MonthEnd(0)
    out = (df.groupby("FECHA_ME", as_index=False)
             .agg(LEVEL=("LEVEL", "last"))
             .rename(columns={"FECHA_ME": "FECHA"}))
    return out


def run_sql(sql: str, params: dict | None = None) -> pd.DataFrame:
    conn = get_conn()
    return pd.read_sql(sql, conn, params=params or {})

@st.cache_data(ttl=600, show_spinner=True)
def pg_run_sql(sql: str, params: dict | None = None) -> pd.DataFrame:
    import psycopg2
    from psycopg2 import OperationalError
    try:
        conn = psycopg2.connect(host=PG_HOST, port=PG_PORT, database=PG_DB, user=PG_USER, password=PG_PWD)
    except OperationalError as e:
        raise RuntimeError(f"Error PG: {e}")
    try:
        df = pd.read_sql(sql, conn, params=params or {})
    finally:
        conn.close()
    return df

def money_to_float_series(serie: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(serie):
        return serie.astype(float).fillna(0.0)
    s = serie.astype(str).str.replace('−', '-', regex=False)
    s = s.str.replace(r'[^\d\.,\-]+', '', regex=True).str.replace(',', '', regex=False)
    return pd.to_numeric(s, errors='coerce').fillna(0.0)

def fmt_pct(x):    return "—" if pd.isna(x) else f"{x*100:.2f}%"
def fmt_money2(x): return f"${x:,.2f}"
def fmt_mm(x):     return f"{x/1e6:.2f} MM"

CASE_ACTIVO = f"""
  CASE 
    WHEN e.ID_PRODUCTO IN ({REPORTO_RV_CSV}) THEN 'Renta Variable'
    ELSE CASE e.ID_TIPO_ACTIVO
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
  END
"""

# =========================
#  HELPER CONTRATO → SQL
# =========================
def build_contrato_filter_sql(contratos, col_qualified: str, param_prefix: str):
    """
    Construye fragmento 'AND col_qualified IN (:p0, :p1, ...)' + diccionario de parámetros
    a partir de la lista de contratos seleccionados.
    """
    if not contratos:
        return "", {}
    # Valores únicos y como int
    unique = []
    seen = set()
    for c in contratos:
        try:
            v = int(c)
        except Exception:
            continue
        if v in seen:
            continue
        seen.add(v)
        unique.append(v)
    if not unique:
        return "", {}
    placeholders = []
    params = {}
    for i, cid in enumerate(unique):
        key = f"{param_prefix}{i}"
        placeholders.append(f":{key}")
        params[key] = cid
    clause = f" AND {col_qualified} IN ({', '.join(placeholders)}) "
    return clause, params

# =========================
#  UTILIDADES EXTRA
# =========================
@st.cache_data(ttl=900, show_spinner=True)
def get_num_contratos(alias: str) -> int:
    q = """SELECT COUNT(DISTINCT ID_CLIENTE) AS N FROM SIAPII.V_M_CONTRATO_CDM WHERE ALIAS_CDM = :a"""
    df = run_sql(q, {"a": alias})
    return int(df.iloc[0,0]) if not df.empty else 0

def _col_exists(owner:str, table:str, col:str) -> bool:
    q = """
    SELECT COUNT(*) AS N
    FROM ALL_TAB_COLUMNS
    WHERE OWNER = :o AND TABLE_NAME = :t AND COLUMN_NAME = :c
    """
    df = run_sql(q, {"o": owner.upper(), "t": table.upper(), "c": col.upper()})
    return (not df.empty) and (int(df.iloc[0,0]) > 0)

def _to_dec(x):
    if pd.isna(x): return np.nan
    s = str(x).strip().replace('%','').replace(' ','')
    if s.count(',') == 1 and s.count('.') == 0:
        s = s.replace(',', '.')
    s = re.sub(r'(?<=\d),(?=\d{3}\b)', '', s)
    try:
        v = float(s)
        return v if 0 <= v <= 1 else v/100.0
    except:
        return np.nan

def build_yearly_accum_series_from_bench_pack(
    bench_pack: pd.DataFrame,
    y_ref: int,
    m_ref: int,
    n_years: int = 5
):
    """
    Devuelve (x_labels, y_vals) usando BENCH_YTD del bench_pack.
    - Para cada año, toma el último BENCH_YTD disponible <= m_ref (o diciembre si m_ref=12).
    """
    if bench_pack is None or bench_pack.empty:
        return [], []

    bp = bench_pack.copy()
    bp["FECHA"] = pd.to_datetime(bp["FECHA"], errors="coerce")
    bp = bp.dropna(subset=["FECHA"])
    if bp.empty:
        return [], []

    bp["ANIO"] = bp["FECHA"].dt.year
    bp["MES"] = bp["FECHA"].dt.month

    years = list(range(y_ref - (n_years - 1), y_ref + 1))
    x_labels, y_vals = [], []

    for yy in years:
        sub = bp[bp["ANIO"] == yy].copy()
        if sub.empty:
            x_labels.append(str(yy))
            y_vals.append(np.nan)
            continue

        # hasta el mes de corte si existe; si no, usa el último mes disponible
        sub = sub[sub["MES"] <= m_ref] if (sub["MES"] <= m_ref).any() else sub

        row = sub.sort_values(["MES", "FECHA"]).iloc[-1]
        v = row.get("BENCH_YTD")

        x_labels.append(str(yy))
        y_vals.append(float(v) * 100.0 if pd.notna(v) else np.nan)

    return x_labels, y_vals

def build_yearly_accum_series(
    df: pd.DataFrame,
    modo: str,
    y_ref: int,
    m_ref: int,
    n_years: int = 5,
    producto: str | None = None
):
    if df is None or df.empty:
        return [], []

    d = df.copy()

    # filtro producto robusto
    if producto is not None and "PRODUCTO" in d.columns:
        prod_u = str(producto).strip().upper()
        d["__PROD__"] = d["PRODUCTO"].astype(str).str.strip().str.upper()
        d = d[d["__PROD__"] == prod_u].copy()
        if d.empty:
            return [], []

    col = "TASA_ACUM_ANUAL" if modo == "Anualizado" else "TASA_ACUM_EFEC"
    if col not in d.columns:
        return [], []

    d[col] = pd.to_numeric(d[col], errors="coerce")

    years = list(range(int(y_ref) - (n_years - 1), int(y_ref) + 1))
    x_labels = [str(y) for y in years]
    y_vals = []

    for yy in years:
        sub = d[d["ANIO"] == yy].copy()
        if sub.empty:
            y_vals.append(np.nan)
            continue

        # año actual: último mes <= m_ref; años pasados: dic si existe, si no último mes
        if yy == int(y_ref):
            sub = sub[sub["MES"] <= int(m_ref)].copy()
            if sub.empty:
                y_vals.append(np.nan)
                continue
            row = sub.sort_values("MES").iloc[-1]
        else:
            if (sub["MES"] == 12).any():
                row = sub[sub["MES"] == 12].sort_values("MES").iloc[-1]
            else:
                row = sub.sort_values("MES").iloc[-1]

        v = row.get(col)
        y_vals.append(float(v) * 100.0 if pd.notna(v) else np.nan)

    return x_labels, y_vals

# =========================
#  Rendimientos contrato 12m
# =========================
@st.cache_data(ttl=900, show_spinner=True)
def rend_bruto_contrato_hist_12m(alias: str, anio: int, mes: int, contratos_key: tuple[int, ...] | None = None) -> pd.DataFrame:
    ref = pd.Timestamp(year=int(anio), month=int(mes), day=1)
    start = (ref - pd.DateOffset(months=11)).replace(day=1)
    end   = (ref + pd.offsets.MonthEnd(0))

    filtro_cts, extra_params = build_contrato_filter_sql(contratos_key, "ID_CLIENTE", "cid_rc")

    sql = f"""
    WITH CTS AS (
      SELECT ID_CLIENTE
      FROM SIAPII.V_M_CONTRATO_CDM
      WHERE ALIAS_CDM = :alias
      {filtro_cts}
    )
    SELECT
        r.ANIO,
        r.MES,
        r.TASA,
        r.TASA_ACUMULADO,
        r.TASA_EFECTIVA,
        r.TASA_EFECTIVA_ACUMULADO
    FROM SIAPII.V_RENDIMIENTO_CTO r
    JOIN CTS c ON c.ID_CLIENTE = r.ID_CLIENTE
    WHERE UPPER(r.TIPO_RENDIMIENTO) LIKE 'GESTION BRUTA'
      AND r.NIVEL = 'CONTRATO'
      AND TRUNC(TO_DATE(r.ANIO || '-' || LPAD(r.MES,2,'0') || '-01', 'YYYY-MM-DD'))
          BETWEEN TO_DATE(:d_ini,'YYYY-MM-DD') AND TO_DATE(:d_fin,'YYYY-MM-DD')
    """
    params = {
        "alias": alias,
        "d_ini": start.strftime("%Y-%m-%d"),
        "d_fin": end.strftime("%Y-%m-%d"),
    }
    params.update(extra_params)

    df = run_sql(sql, params)
    if df.empty:
        return pd.DataFrame(columns=[
            "ANIO","MES",
            "TASA_M_ANUAL","TASA_ACUM_ANUAL",
            "TASA_M_EFEC","TASA_ACUM_EFEC"
        ])
    df = df.sort_values(["ANIO","MES"]).groupby(["ANIO","MES"], as_index=False).last()
    df["TASA_M_ANUAL"]    = df["TASA"].apply(_to_dec)
    df["TASA_ACUM_ANUAL"] = df["TASA_ACUMULADO"].apply(_to_dec)
    df["TASA_M_EFEC"]     = df["TASA_EFECTIVA"].apply(_to_dec)
    df["TASA_ACUM_EFEC"]  = df["TASA_EFECTIVA_ACUMULADO"].apply(_to_dec)
    return df[[
        "ANIO","MES",
        "TASA_M_ANUAL","TASA_ACUM_ANUAL",
        "TASA_M_EFEC","TASA_ACUM_EFEC"
    ]]

# =========================
#  Rendimientos por producto 12m (V_RENDIMIENTO_PROD)
# =========================
@st.cache_data(ttl=900, show_spinner=True)
def rend_bruto_producto_hist_12m(alias: str, anio: int, mes: int, contratos_key: tuple[int, ...] | None = None) -> pd.DataFrame:
    ref = pd.Timestamp(year=int(anio), month=int(mes), day=1)
    start = (ref - pd.DateOffset(months=11)).replace(day=1)
    end = (ref + pd.offsets.MonthEnd(0))
    tiene_nivel_prod = _col_exists('SIAPII', 'V_RENDIMIENTO_PROD', 'NIVEL_PRODUCTO')
    filtro_nivel = "AND r.NIVEL_PRODUCTO = 'SI'" if tiene_nivel_prod else ""

    has_idcdm_cto = _col_exists('SIAPII', 'V_M_CONTRATO_CDM', 'ID_CDM')
    has_idcdm_rp  = _col_exists('SIAPII', 'V_RENDIMIENTO_PROD', 'ID_CDM')

    if has_idcdm_cto and has_idcdm_rp:
        filtro_cts, extra_params = build_contrato_filter_sql(contratos_key, "ID_CLIENTE", "cid_rp1")
        sql = f"""
        WITH CTS AS (
            SELECT DISTINCT ID_CDM
            FROM SIAPII.V_M_CONTRATO_CDM
            WHERE ALIAS_CDM = :alias
            {filtro_cts}
        )
        SELECT
            r.ANIO,
            r.MES,
            r.ID_PRODUCTO,
            COALESCE(p.DESCRIPCION, 'SIN_DESCRIPCION') AS PRODUCTO,
            r.TASA,
            r.TASA_EFECTIVA,
            r.TASA_ACUMULADO,
            r.TASA_EFECTIVA_ACUMULADO
        FROM SIAPII.V_RENDIMIENTO_PROD r
        JOIN CTS c
          ON c.ID_CDM = r.ID_CDM
        LEFT JOIN SIAPII.V_M_PRODUCTO p
          ON p.ID_PRODUCTO = r.ID_PRODUCTO
        WHERE UPPER(r.TIPO_RENDIMIENTO) = 'GESTION BRUTA'
          {filtro_nivel}
          AND TRUNC(TO_DATE(r.ANIO || '-' || LPAD(r.MES,2,'0') || '-01', 'YYYY-MM-DD'))
              BETWEEN TO_DATE(:d_ini,'YYYY-MM-DD') AND TO_DATE(:d_fin,'YYYY-MM-DD')
        """
        params = {
            "alias": alias,
            "d_ini": start.strftime("%Y-%m-%d"),
            "d_fin": end.strftime("%Y-%m-%d"),
        }
        params.update(extra_params)
    else:
        filtro_pa, extra_params = build_contrato_filter_sql(contratos_key, "c.ID_CLIENTE", "cid_rp2")
        sql = f"""
        WITH PROD_ALIAS AS (
            SELECT DISTINCT e.ID_PRODUCTO
            FROM SIAPII.V_CLIENTE_ESTADISTICAS e
            JOIN SIAPII.V_M_CONTRATO_CDM c
              ON c.ID_CLIENTE = e.ID_CLIENTE
            WHERE c.ALIAS_CDM = :alias
              {filtro_pa}
        )
        SELECT
            r.ANIO,
            r.MES,
            r.ID_PRODUCTO,
            COALESCE(p.DESCRIPCION, 'SIN_DESCRIPCION') AS PRODUCTO,
            r.TASA,
            r.TASA_EFECTIVA,
            r.TASA_ACUMULADO,
            r.TASA_EFECTIVA_ACUMULADO
        FROM SIAPII.V_RENDIMIENTO_PROD r
        JOIN PROD_ALIAS pa
          ON pa.ID_PRODUCTO = r.ID_PRODUCTO
        LEFT JOIN SIAPII.V_M_PRODUCTO p
          ON p.ID_PRODUCTO = r.ID_PRODUCTO
        WHERE UPPER(r.TIPO_RENDIMIENTO) = 'GESTION BRUTA'
          {filtro_nivel}
          AND TRUNC(TO_DATE(r.ANIO || '-' || LPAD(r.MES,2,'0') || '-01', 'YYYY-MM-DD'))
              BETWEEN TO_DATE(:d_ini,'YYYY-MM-DD') AND TO_DATE(:d_fin,'YYYY-MM-DD')
        """
        params = {
            "alias": alias,
            "d_ini": start.strftime("%Y-%m-%d"),
            "d_fin": end.strftime("%Y-%m-%d"),
        }
        params.update(extra_params)

    df = run_sql(sql, params)
    if df.empty:
        return pd.DataFrame(columns=[
            "ANIO","MES","ID_PRODUCTO","PRODUCTO",
            "TASA_M_ANUAL","TASA_ACUM_ANUAL",
            "TASA_M_EFEC","TASA_ACUM_EFEC"
        ])
    df = (
        df.sort_values(["ANIO", "MES", "ID_PRODUCTO"])
          .groupby(["ANIO", "MES", "ID_PRODUCTO", "PRODUCTO"], as_index=False)
          .last()
    )
    df["TASA_M_ANUAL"]    = df["TASA"].apply(_to_dec)
    df["TASA_M_EFEC"]     = df["TASA_EFECTIVA"].apply(_to_dec)
    df["TASA_ACUM_ANUAL"] = df["TASA_ACUMULADO"].apply(_to_dec)
    df["TASA_ACUM_EFEC"]  = df["TASA_EFECTIVA_ACUMULADO"].apply(_to_dec)
    return df[[
        "ANIO","MES","ID_PRODUCTO","PRODUCTO",
        "TASA_M_ANUAL","TASA_ACUM_ANUAL",
        "TASA_M_EFEC","TASA_ACUM_EFEC"
    ]]

# =========================
#  Rendimientos 5 años (para acumulado anual por año)
# =========================
@st.cache_data(ttl=900, show_spinner=True)
def rend_bruto_contrato_hist_n_years(alias: str, anio: int, mes: int, n_years: int = 5,
                                    contratos_key: tuple[int, ...] | None = None) -> pd.DataFrame:
    ref = pd.Timestamp(year=int(anio), month=int(mes), day=1)
    start = pd.Timestamp(year=int(anio) - (n_years - 1), month=1, day=1)
    end   = (ref + pd.offsets.MonthEnd(0))

    filtro_cts, extra_params = build_contrato_filter_sql(contratos_key, "ID_CLIENTE", "cid_rc5")

    sql = f"""
    WITH CTS AS (
      SELECT ID_CLIENTE
      FROM SIAPII.V_M_CONTRATO_CDM
      WHERE ALIAS_CDM = :alias
      {filtro_cts}
    )
    SELECT
        r.ANIO,
        r.MES,
        r.TASA,
        r.TASA_ACUMULADO,
        r.TASA_EFECTIVA,
        r.TASA_EFECTIVA_ACUMULADO
    FROM SIAPII.V_RENDIMIENTO_CTO r
    JOIN CTS c ON c.ID_CLIENTE = r.ID_CLIENTE
    WHERE UPPER(r.TIPO_RENDIMIENTO) LIKE 'GESTION BRUTA'
      AND r.NIVEL = 'CONTRATO'
      AND TRUNC(TO_DATE(r.ANIO || '-' || LPAD(r.MES,2,'0') || '-01', 'YYYY-MM-DD'))
          BETWEEN TO_DATE(:d_ini,'YYYY-MM-DD') AND TO_DATE(:d_fin,'YYYY-MM-DD')
    """
    params = {"alias": alias, "d_ini": start.strftime("%Y-%m-%d"), "d_fin": end.strftime("%Y-%m-%d")}
    params.update(extra_params)

    df = run_sql(sql, params)
    if df.empty:
        return pd.DataFrame(columns=[
            "ANIO","MES",
            "TASA_M_ANUAL","TASA_ACUM_ANUAL",
            "TASA_M_EFEC","TASA_ACUM_EFEC"
        ])

    df = df.sort_values(["ANIO","MES"]).groupby(["ANIO","MES"], as_index=False).last()
    df["TASA_M_ANUAL"]    = df["TASA"].apply(_to_dec)
    df["TASA_ACUM_ANUAL"] = df["TASA_ACUMULADO"].apply(_to_dec)
    df["TASA_M_EFEC"]     = df["TASA_EFECTIVA"].apply(_to_dec)
    df["TASA_ACUM_EFEC"]  = df["TASA_EFECTIVA_ACUMULADO"].apply(_to_dec)
    return df[["ANIO","MES","TASA_M_ANUAL","TASA_ACUM_ANUAL","TASA_M_EFEC","TASA_ACUM_EFEC"]]


@st.cache_data(ttl=900, show_spinner=True)
def rend_bruto_producto_hist_n_years(alias: str, anio: int, mes: int, n_years: int = 5,
                                     contratos_key: tuple[int, ...] | None = None) -> pd.DataFrame:
    ref = pd.Timestamp(year=int(anio), month=int(mes), day=1)
    start = pd.Timestamp(year=int(anio) - (n_years - 1), month=1, day=1)
    end   = (ref + pd.offsets.MonthEnd(0))

    tiene_nivel_prod = _col_exists('SIAPII', 'V_RENDIMIENTO_PROD', 'NIVEL_PRODUCTO')
    filtro_nivel = "AND r.NIVEL_PRODUCTO = 'SI'" if tiene_nivel_prod else ""

    has_idcdm_cto = _col_exists('SIAPII', 'V_M_CONTRATO_CDM', 'ID_CDM')
    has_idcdm_rp  = _col_exists('SIAPII', 'V_RENDIMIENTO_PROD', 'ID_CDM')

    if has_idcdm_cto and has_idcdm_rp:
        filtro_cts, extra_params = build_contrato_filter_sql(contratos_key, "ID_CLIENTE", "cid_rp5a")
        sql = f"""
        WITH CTS AS (
            SELECT DISTINCT ID_CDM
            FROM SIAPII.V_M_CONTRATO_CDM
            WHERE ALIAS_CDM = :alias
            {filtro_cts}
        )
        SELECT
            r.ANIO,
            r.MES,
            r.ID_PRODUCTO,
            COALESCE(p.DESCRIPCION, 'SIN_DESCRIPCION') AS PRODUCTO,
            r.TASA,
            r.TASA_EFECTIVA,
            r.TASA_ACUMULADO,
            r.TASA_EFECTIVA_ACUMULADO
        FROM SIAPII.V_RENDIMIENTO_PROD r
        JOIN CTS c
          ON c.ID_CDM = r.ID_CDM
        LEFT JOIN SIAPII.V_M_PRODUCTO p
          ON p.ID_PRODUCTO = r.ID_PRODUCTO
        WHERE UPPER(r.TIPO_RENDIMIENTO) = 'GESTION BRUTA'
          {filtro_nivel}
          AND TRUNC(TO_DATE(r.ANIO || '-' || LPAD(r.MES,2,'0') || '-01', 'YYYY-MM-DD'))
              BETWEEN TO_DATE(:d_ini,'YYYY-MM-DD') AND TO_DATE(:d_fin,'YYYY-MM-DD')
        """
        params = {"alias": alias, "d_ini": start.strftime("%Y-%m-%d"), "d_fin": end.strftime("%Y-%m-%d")}
        params.update(extra_params)
    else:
        filtro_pa, extra_params = build_contrato_filter_sql(contratos_key, "c.ID_CLIENTE", "cid_rp5b")
        sql = f"""
        WITH PROD_ALIAS AS (
            SELECT DISTINCT e.ID_PRODUCTO
            FROM SIAPII.V_CLIENTE_ESTADISTICAS e
            JOIN SIAPII.V_M_CONTRATO_CDM c
              ON c.ID_CLIENTE = e.ID_CLIENTE
            WHERE c.ALIAS_CDM = :alias
              {filtro_pa}
        )
        SELECT
            r.ANIO,
            r.MES,
            r.ID_PRODUCTO,
            COALESCE(p.DESCRIPCION, 'SIN_DESCRIPCION') AS PRODUCTO,
            r.TASA,
            r.TASA_EFECTIVA,
            r.TASA_ACUMULADO,
            r.TASA_EFECTIVA_ACUMULADO
        FROM SIAPII.V_RENDIMIENTO_PROD r
        JOIN PROD_ALIAS pa
          ON pa.ID_PRODUCTO = r.ID_PRODUCTO
        LEFT JOIN SIAPII.V_M_PRODUCTO p
          ON p.ID_PRODUCTO = r.ID_PRODUCTO
        WHERE UPPER(r.TIPO_RENDIMIENTO) = 'GESTION BRUTA'
          {filtro_nivel}
          AND TRUNC(TO_DATE(r.ANIO || '-' || LPAD(r.MES,2,'0') || '-01', 'YYYY-MM-DD'))
              BETWEEN TO_DATE(:d_ini,'YYYY-MM-DD') AND TO_DATE(:d_fin,'YYYY-MM-DD')
        """
        params = {"alias": alias, "d_ini": start.strftime("%Y-%m-%d"), "d_fin": end.strftime("%Y-%m-%d")}
        params.update(extra_params)

    df = run_sql(sql, params)
    if df.empty:
        return pd.DataFrame(columns=[
            "ANIO","MES","ID_PRODUCTO","PRODUCTO",
            "TASA_M_ANUAL","TASA_ACUM_ANUAL",
            "TASA_M_EFEC","TASA_ACUM_EFEC"
        ])

    df = (
        df.sort_values(["ANIO","MES","ID_PRODUCTO"])
          .groupby(["ANIO","MES","ID_PRODUCTO","PRODUCTO"], as_index=False)
          .last()
    )
    df["TASA_M_ANUAL"]    = df["TASA"].apply(_to_dec)
    df["TASA_M_EFEC"]     = df["TASA_EFECTIVA"].apply(_to_dec)
    df["TASA_ACUM_ANUAL"] = df["TASA_ACUMULADO"].apply(_to_dec)
    df["TASA_ACUM_EFEC"]  = df["TASA_EFECTIVA_ACUMULADO"].apply(_to_dec)
    return df[["ANIO","MES","ID_PRODUCTO","PRODUCTO","TASA_M_ANUAL","TASA_ACUM_ANUAL","TASA_M_EFEC","TASA_ACUM_EFEC"]]


def _annualize_from_effective(tef_dec, plazo_dias):
    tef = pd.to_numeric(pd.Series(tef_dec), errors='coerce')
    plazo = pd.to_numeric(pd.Series(plazo_dias), errors='coerce')
    mask = (plazo > 0)
    out = pd.Series(np.nan, index=tef.index, dtype=float)
    out[mask] = (1.0 + tef[mask])**(360.0/plazo[mask]) - 1.0
    return out

@st.cache_data(ttl=900, show_spinner=True)
def rend_bruto_contrato_y_producto(alias: str, anio: int, mes: int, contratos_key: tuple[int, ...] | None = None):
    ids = run_sql("""
        SELECT ID_CLIENTE FROM SIAPII.V_M_CONTRATO_CDM
        WHERE ALIAS_CDM = :alias
    """, {"alias": alias})
    if ids.empty:
        return np.nan, np.nan, pd.DataFrame(columns=["Producto","Mensual Anualizado","Acum Anualizado"])

    has_id_producto = _col_exists('SIAPII','V_RENDIMIENTO_CTO','ID_PRODUCTO')
    has_desc_producto = _col_exists('SIAPII','V_RENDIMIENTO_CTO','DESCRIPCION_PRODUCTO')

    sel_cols = """
        r.ANIO, r.MES, r.ID_CDM, r.ID_CLIENTE,
        r.MODALIDAD, r.NIVEL, r.PERIODO, r.MONEDA_ORIGEN, r.NIVEL_PRODUCTO,
        r.TIPO_RENDIMIENTO,
        r.TASA_EFECTIVA, r.PLAZO,
        r.TASA_EFECTIVA_ACUMULADO, r.PLAZO_ACUMULADO
    """
    if has_id_producto:
        sel_cols += ", r.ID_PRODUCTO"
    if has_desc_producto:
        sel_cols += ", r.DESCRIPCION_PRODUCTO"

    filtro_cts, extra_params = build_contrato_filter_sql(contratos_key, "ID_CLIENTE", "cid_rcp")

    base_sql = f"""
        WITH CTS AS (
          SELECT ID_CLIENTE
          FROM SIAPII.V_M_CONTRATO_CDM
          WHERE ALIAS_CDM = :alias
          {filtro_cts}
        )
        SELECT {sel_cols}
        FROM SIAPII.V_RENDIMIENTO_CTO r
        JOIN CTS c ON c.ID_CLIENTE = r.ID_CLIENTE
        WHERE r.ANIO = :anio
          AND r.MES  = :mes
          AND UPPER(r.TIPO_RENDIMIENTO) LIKE 'GESTION BRUTA'
    """
    params = {"alias": alias, "anio": int(anio), "mes": int(mes)}
    params.update(extra_params)

    df = run_sql(base_sql, params)
    if df.empty:
        return np.nan, np.nan, pd.DataFrame(columns=["Producto","Mensual Anualizado","Acum Anualizado"])

    df_cto = df[df["NIVEL"].astype(str).str.upper()=="CONTRATO"].copy()
    if not df_cto.empty:
        df_cto_m = df_cto.dropna(subset=["TASA_EFECTIVA","PLAZO"]).head(1)
        cto_m_anual = _annualize_from_effective(
            _to_dec(df_cto_m["TASA_EFECTIVA"].iloc[0]),
            df_cto_m["PLAZO"].iloc[0]
        ).iloc[0]
        if df_cto.dropna(subset=["TASA_EFECTIVA_ACUMULADO","PLAZO_ACUMULADO"]).empty:
            cto_ytd_anual = np.nan
        else:
            row = df_cto.dropna(subset=["TASA_EFECTIVA_ACUMULADO","PLAZO_ACUMULADO"]).head(1).iloc[0]
            cto_ytd_anual = _annualize_from_effective(
                _to_dec(row["TASA_EFECTIVA_ACUMULADO"]),
                row["PLAZO_ACUMULADO"]
            ).iloc[0]
    else:
        cto_m_anual, cto_ytd_anual = np.nan, np.nan

    df_prod = pd.DataFrame(columns=["Producto","Mensual Anualizado","Acum Anualizado"])
    if has_id_producto or has_desc_producto:
        df_p = df[df["NIVEL_PRODUCTO"].astype(str).str.upper()=="SI"].copy()
        if not df_p.empty:
            if has_desc_producto:
                df_p["Producto"] = df_p["DESCRIPCION_PRODUCTO"].fillna("")
            elif has_id_producto:
                mp = run_sql("SELECT ID_PRODUCTO, COALESCE(DESCRIPCION,'SIN_DESCRIPCION') AS PRODUCTO FROM SIAPII.V_M_PRODUCTO")
                df_p = df_p.merge(mp, on="ID_PRODUCTO", how="left")
                df_p["Producto"] = df_p["PRODUCTO"].fillna(df_p.get("ID_PRODUCTO").astype(str))

            m_an = _annualize_from_effective(_to_dec(df_p["TASA_EFECTIVA"]), df_p["PLAZO"])
            a_an = _annualize_from_effective(_to_dec(df_p["TASA_EFECTIVA_ACUMULADO"]), df_p["PLAZO_ACUMULADO"])

            out = pd.DataFrame({
                "Producto": df_p["Producto"].astype(str),
                "Mensual Anualizado": (m_an*100.0).round(2),
                "Acum Anualizado": (a_an*100.0).round(2)
            })
            df_prod = (out.groupby("Producto", as_index=False)
                          .agg({"Mensual Anualizado":"last","Acum Anualizado":"last"})
                          .sort_values("Mensual Anualizado", ascending=False)
                          .reset_index(drop=True))
    return cto_m_anual, cto_ytd_anual, df_prod

# =========================
#  NOMBRE CLIENTE (título)
# =========================
@st.cache_data(ttl=3600, show_spinner=True)
def get_nombre_cliente(alias: str) -> str:
    sql = "SELECT NOMBRE_CLIENTE FROM SIAPII.V_M_CONTRATO_CDM WHERE ALIAS_CDM = :alias FETCH FIRST 1 ROWS ONLY"
    df = run_sql(sql, {"alias": alias})
    if df.empty or pd.isna(df.iloc[0,0]): return alias
    return str(df.iloc[0,0]).split(',', 1)[0].strip()

# =========================
#  BASE AA (corte)
# =========================
def build_query_base_unfiltered(alias: str, fecha: str, contratos_key: tuple[int, ...] | None = None):
    filtro_contratos, extra_params = build_contrato_filter_sql(contratos_key, "e.ID_CLIENTE", "cid_aa")
    sql = f"""
    SELECT
      COALESCE(p.DESCRIPCION, 'SIN_DESCRIPCION') AS PRODUCTO,
      {CASE_ACTIVO} AS ACTIVO,
      SUM(e.POSICION_TOTAL) AS MONTO
    FROM SIAPII.V_CLIENTE_ESTADISTICAS e
    LEFT JOIN SIAPII.V_M_PRODUCTO p ON p.ID_PRODUCTO = e.ID_PRODUCTO
    WHERE e.ALIAS_CDM = :alias
      AND TRUNC(e.FECHA_ESTADISTICA) = TO_DATE(:fecha, 'YYYY-MM-DD')
      {filtro_contratos}
    GROUP BY COALESCE(p.DESCRIPCION, 'SIN_DESCRIPCION'), {CASE_ACTIVO}
    """
    params = {"alias": alias, "fecha": fecha}
    params.update(extra_params)
    return sql, params

@st.cache_data(ttl=3600, show_spinner=True)
def aa_hist_ultimo_5_anios(alias: str, cutoff_next: pd.Timestamp,
                           contratos_key: tuple[int, ...] | None = None):
    filtro_contratos, extra_params = build_contrato_filter_sql(contratos_key, "c.ID_CLIENTE", "cid_aa_hist")

    SQL = f"""
    WITH A AS (
      SELECT
        EXTRACT(YEAR FROM TRUNC(e.FECHA_ESTADISTICA)) AS ANIO,
        {CASE_ACTIVO} AS ACTIVO,
        COALESCE(p.DESCRIPCION, 'SIN_DESCRIPCION') AS PRODUCTO,
        SUM(e.POSICION_TOTAL) AS MONTO
      FROM SIAPII.V_CLIENTE_ESTADISTICAS e
      JOIN SIAPII.V_M_CONTRATO_CDM c
        ON c.ID_CLIENTE = e.ID_CLIENTE
      LEFT JOIN SIAPII.V_M_PRODUCTO p ON p.ID_PRODUCTO = e.ID_PRODUCTO
      WHERE c.ALIAS_CDM = :alias
        {filtro_contratos}
        AND e.FECHA_ESTADISTICA <  TO_DATE(:cutoff_next,'YYYY-MM-DD')
        AND e.FECHA_ESTADISTICA >= ADD_MONTHS(TRUNC(TO_DATE(:cutoff_next,'YYYY-MM-DD'),'YYYY'), -12*5)

      GROUP BY EXTRACT(YEAR FROM TRUNC(e.FECHA_ESTADISTICA)), {CASE_ACTIVO}, COALESCE(p.DESCRIPCION, 'SIN_DESCRIPCION')
    )
    SELECT * FROM A
    """
    params = {"alias": alias, "cutoff_next": pd.to_datetime(cutoff_next).strftime("%Y-%m-%d")}
    params.update(extra_params)

    df = run_sql(SQL, params)
    if df.empty:
        return (pd.DataFrame(columns=["ANIO","ACTIVO","MONTO","Pct"]),
                pd.DataFrame(columns=["ANIO","PRODUCTO","MONTO","Pct"]))
    aa_activo = df.groupby(["ANIO","ACTIVO"], dropna=False)["MONTO"].sum().reset_index()
    tot = aa_activo.groupby("ANIO")["MONTO"].sum().rename("TOT")
    aa_activo = aa_activo.merge(tot, on="ANIO", how="left")
    aa_activo["Pct"] = (aa_activo["MONTO"] / aa_activo["TOT"] * 100).round(2)
    aa_activo = aa_activo.drop(columns=["TOT"])
    aa_producto = df.groupby(["ANIO","PRODUCTO"], dropna=False)["MONTO"].sum().reset_index()
    tot2 = aa_producto.groupby("ANIO")["MONTO"].sum().rename("TOT")
    aa_producto = aa_producto.merge(tot2, on="ANIO", how="left")
    aa_producto["Pct"] = (aa_producto["MONTO"] / aa_producto["TOT"] * 100).round(2)
    aa_producto = aa_producto.drop(columns=["TOT"])
    return aa_activo, aa_producto

# =========================
#  Snapshot Deuda (ID_TIPO_ACTIVO=1) + ratings/carry
# =========================
FALLBACK_IDS = [37, 3]
ids_csv = ",".join(str(i) for i in FALLBACK_IDS)
DTYPE_Q = """
SELECT DATA_TYPE
FROM ALL_TAB_COLUMNS
WHERE OWNER = 'SIAPII'
  AND TABLE_NAME = 'V_TASAS_REFERENCIA'
  AND COLUMN_NAME = 'FECHA'
"""

@st.cache_data(ttl=3600, show_spinner=True)
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

def where_filters_for_his(contratos_key: tuple[int, ...] | None = None):
    base_sql = (
        "WHERE EXISTS ( SELECT 1 FROM SIAPII.V_M_CONTRATO_CDM c "
        "WHERE c.ALIAS_CDM = :alias_up AND c.ID_CLIENTE = h.ID_CLIENTE"
    )
    filtro, params = build_contrato_filter_sql(contratos_key, "c.ID_CLIENTE", "cid_his")
    return base_sql + filtro + " )", params

@st.cache_data(ttl=1200, show_spinner=True)
def query_snapshot_deuda(
    alias: str,
    f_ini: pd.Timestamp,
    f_fin_next: pd.Timestamp,
    contratos_key: tuple[int, ...] | None = None
) -> pd.DataFrame:
    params, DATE_EXPR = build_snapshot_params(alias, f_ini, f_fin_next)

    # Filtro de contratos sobre V_M_CONTRATO_CDM
    filtro_fc, params_fc = build_contrato_filter_sql(contratos_key, "c1.ID_CLIENTE", "cid_fc")
    params.update(params_fc)

    SQL_SNAPSHOT = f"""
WITH
CLIENTES AS (
  SELECT /*+ MATERIALIZE */ DISTINCT c1.ID_CLIENTE
  FROM SIAPII.V_M_CONTRATO_CDM c1
  WHERE c1.ALIAS_CDM = :alias_up
  {filtro_fc}
),

/* 1) fecha de corte: MAX(REGISTRO_CONTROL) para esos clientes y rango */
FECHA_C AS (
  SELECT /*+ MATERIALIZE */
    MAX(h1.REGISTRO_CONTROL)        AS FECHA_CORTE_TS,
    TRUNC(MAX(h1.REGISTRO_CONTROL)) AS FECHA_CORTE_DAY
  FROM SIAPII.V_HIS_POSICION_CLIENTE h1
  JOIN CLIENTES c ON c.ID_CLIENTE = h1.ID_CLIENTE
  WHERE h1.REGISTRO_CONTROL >= TO_DATE(:f_ini_dt,'YYYY-MM-DD')
    AND h1.REGISTRO_CONTROL <  TO_DATE(:f_fin_dt,'YYYY-MM-DD')
),

/* 2) snapshot del día de corte: TRAER SOLO COLUMNAS NECESARIAS */
H_CORTE AS (
  SELECT /*+ MATERIALIZE */
    h.ID_CLIENTE,
    h.ID_PRODUCTO,
    h.ID_EMISORA,
    h.CALIFICACION_HOMOLOGADA,
    h.CALIFICACION_S_P,
    h.CALIFICACION_MDYS,
    h.CALIFICACION_HRRATING,
    h.CALIFICACION_FITCH,
    h.EMIS_TASA,
    h.VALOR_NOMINAL,
    h.VALOR_REAL,
    NVL(h.PLAZO_REPORTO,0) AS PLAZO_REPORTO,
    h.REGISTRO_CONTROL
  FROM SIAPII.V_HIS_POSICION_CLIENTE h
  JOIN CLIENTES c ON c.ID_CLIENTE = h.ID_CLIENTE
  CROSS JOIN FECHA_C fc
  WHERE h.REGISTRO_CONTROL >= fc.FECHA_CORTE_DAY
    AND h.REGISTRO_CONTROL <  fc.FECHA_CORTE_DAY + 1
),

/* 3) Tasas referencia: FILTRAR DESDE EL ORIGEN por ids_csv */
VTR_BASE AS (
  SELECT
    r.ID_TASA_REFERENCIA,
    r.TASA_REFERENCIA,
    r.TASA,
    {DATE_EXPR} AS FECHA_TRUNC
  FROM SIAPII.V_TASAS_REFERENCIA r
  WHERE r.ID_TASA_REFERENCIA IN ({ids_csv})
),

VTR_EXACT AS (
  SELECT v.ID_TASA_REFERENCIA, v.TASA, v.TASA_REFERENCIA
  FROM VTR_BASE v
  CROSS JOIN FECHA_C fc
  WHERE v.FECHA_TRUNC = fc.FECHA_CORTE_DAY
),

VTR_FALL AS (
  SELECT x.ID_TASA_REFERENCIA, x.TASA, x.TASA_REFERENCIA
  FROM (
    SELECT
      v.ID_TASA_REFERENCIA,
      v.TASA,
      v.TASA_REFERENCIA,
      v.FECHA_TRUNC,
      ROW_NUMBER() OVER (
        PARTITION BY v.ID_TASA_REFERENCIA
        ORDER BY v.FECHA_TRUNC DESC
      ) AS RN
    FROM VTR_BASE v
    CROSS JOIN FECHA_C fc
    WHERE v.FECHA_TRUNC IS NOT NULL
      AND v.FECHA_TRUNC <= fc.FECHA_CORTE_DAY
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
    SELECT 1 FROM VTR_EXACT e
    WHERE e.ID_TASA_REFERENCIA = f.ID_TASA_REFERENCIA
  )
)

SELECT
    h.ID_PRODUCTO,
    e.ID_EMISORA,
    MAX(e.NOMBRE_EMISORA)           AS NOMBRE_EMISORA,
    MAX(e.SERIE)                    AS SERIE,
    MAX(e.TIPO_PAPEL)               AS TIPO_PAPEL,
    MAX(e.TIPO_INSTRUMENTO)         AS TIPO_INSTRUMENTO,
    MAX(e.PLAZO_CUPON)              AS PLAZO_CUPON,
    MAX(e.FECHA_VTO_EM)             AS FECHA_VTO_EM,
    MAX(e.ID_TASA_REFERENCIA)       AS ID_TASA_REFERENCIA,
    MAX(e.ID_DIVISA_TV)             AS ID_DIVISA_TV,
    MAX(h.CALIFICACION_HOMOLOGADA)  AS CALIFICACION_HOMOLOGADA,
    MAX(h.CALIFICACION_S_P)         AS CALIFICACION_S_P,
    MAX(h.CALIFICACION_MDYS)        AS CALIFICACION_MDYS,
    MAX(h.CALIFICACION_HRRATING)    AS CALIFICACION_HRRATING,
    MAX(h.CALIFICACION_FITCH)       AS CALIFICACION_FITCH,
    MAX(h.EMIS_TASA)                AS EMIS_TASA,
    SUM(h.VALOR_NOMINAL)            AS VALOR_NOMINAL,
    SUM(h.VALOR_REAL)               AS VALOR_REAL,
    CASE
      WHEN SUM(h.VALOR_REAL) IS NULL OR SUM(h.VALOR_REAL) = 0 THEN NULL
      ELSE SUM(h.PLAZO_REPORTO * h.VALOR_REAL) / SUM(h.VALOR_REAL)
    END                             AS DURACION_DIAS,
    TRUNC(MAX(e.FECHA_VTO_EM)) - TRUNC(MAX(h.REGISTRO_CONTROL)) AS DIAS_X_V,
    MAX(TRUNC(h.REGISTRO_CONTROL)) AS FECHA_CORTE,
    MAX(vtr.TASA)                   AS TASA_BASE,
    MAX(vtr.TASA_REFERENCIA)        AS TASA_REF_NAME
FROM H_CORTE h
LEFT JOIN SIAPII.V_M_EMISORA e ON e.ID_EMISORA = h.ID_EMISORA
LEFT JOIN VTR_REF vtr ON vtr.ID_TASA_REFERENCIA = e.ID_TASA_REFERENCIA
WHERE e.ID_TIPO_ACTIVO = 1
  AND h.ID_PRODUCTO NOT IN ({REPORTO_RV_CSV})
GROUP BY h.ID_PRODUCTO, e.ID_EMISORA
ORDER BY SUM(h.VALOR_REAL) DESC NULLS LAST, MAX(e.NOMBRE_EMISORA)
"""
    return run_sql(SQL_SNAPSHOT, params=params)

# ===== Ratings helpers + carry =====
VAL_TO_BUCKET = {
    1:"AAA",2:"AA+",3:"AA",4:"AA-",5:"A+",6:"A",7:"A-",
    8:"BBB+",9:"BBB",10:"BBB-",11:"BB+",12:"BB",13:"BB-",
    14:"B+",15:"B",16:"B-",17:"CCC+",18:"CCC",19:"CCC-",
    20:"CC+",21:"CC",22:"CC-",23:"C+",24:"C",25:"C-",26:"D"
}
RATING_RULES = [
    (r'^(MX)?AAA(\b|/|\()', 1),(r'^(AAA/)[1-7]$', 1),(r'^(A-?1\+|HR\+?1|HR\s*\+?1|F1\+|P-?1)\b', 1),
    (r'^(MX)?AA\+(\b|/|\()', 2),(r'^(MX)?AA(\b|/|\()', 3),(r'^(MX)?AA-(\b|/|\()', 4),
    (r'^(MX)?A\+(\b|/|\()', 5),(r'^(MX)?A(\b|/|\()', 6),(r'^(MX)?A-(\b|/|\()', 7),
    (r'^(MX)?BBB\+(\b|/|\()', 8),(r'^(MX)?BBB(\b|/|\()', 9),(r'^(MX)?BBB-(\b|/|\()', 10),
    (r'^(MX)?BB\+(\b|/|\()', 11),(r'^(MX)?BB(\b|/|\()', 12),(r'^(MX)?BB-(\b|/|\()', 13),
    (r'^(MX)?B\+(\b|/|\()', 14),(r'^(MX)?B(\b|/|\()', 15),(r'^(MX)?B-(\b|/|\()', 16),
    (r'^(MX)?CCC\+(\b|/|\()', 17),(r'^(MX)?CCC(\b|/|\()', 18),(r'^(MX)?CCC-(\b|/|\()', 19),
    (r'^(MX)?CC\+(\b|/|\()', 20),(r'^(MX)?CC(\b|/|\()', 21),(r'^(MX)?CC-(\b|/|\()', 22),
    (r'^(MX)?C\+(\b|/|\()', 23),(r'^(MX)?C(\b|/|\()', 24),(r'^(MX)?C-(\b|/|\()', 25),
    (r'^(MX)?D(\b|/|\()', 26),(r'^RD(\(MEX\))?$', 26),
    (r'^AAA\.?MX$', 1),(r'^AA\+\.?MX$', 2),(r'^AA\.?MX$', 3),(r'^AA-\.?MX$', 4),
    (r'^A\+\.?MX$', 5),(r'^A\.?MX$', 6),(r'^A-\.?MX$', 7),
    (r'^BBB\+\.?MX$', 8),(r'^BBB\.?MX$', 9),(r'^BBB-\.?MX$', 10),
    (r'^BB\+\.?MX$', 11),(r'^BB\.?MX$', 12),(r'^BB-\.?MX$', 13),
    (r'^B\+\.?MX$', 14),(r'^B\.?MX$', 15),(r'^B-\.?MX$', 16),
    (r'^CCC\+\.?MX$', 17),(r'^CCC\.?MX$', 18),(r'^CCC-\.?MX$', 19),
    (r'^Aaa$', 1),(r'^Aa1$', 2),(r'^Aa2$', 3),(r'^Aa3$', 4),
    (r'^A1$', 5),(r'^A2$', 6),(r'^A3$', 7),
    (r'^Baa1$', 8),(r'^Baa2$', 9),(r'^Baa3$', 10),
    (r'^Ba1$', 11),(r'^Ba2$', 12),(r'^Ba3$', 13),
    (r'^B1$', 14),(r'^B2$', 15),(r'^B3$', 16),
    (r'^Caa1$', 17),(r'^Caa2$', 18),(r'^Caa3$', 19),
    (r'^Ca$', 21),(r'^C$', 24),
    (r'^HR\+?1$', 1),(r'^HR1$', 1),(r'^HR2$', 2),(r'^HR3$', 9),(r'^HR4$', 17),(r'^HR5$', 26),
    (r'^F1\+$', 1),(r'^F1$', 2),(r'^F2$', 6),(r'^F3$', 9),
    (r'^P-?1$', 1),(r'^P-?2$', 3),(r'^P-?3$', 6),
]
def _norm(s: str) -> str:
    if s is None: return ""
    s = str(s).strip()
    if s == "" or s.lower() == "nan": return ""
    return s
def rating_to_value(s: str) -> float:
    s0 = _norm(s)
    if not s0: return np.nan
    s1 = s0.upper().replace('.', '').replace(' ', '')
    s1 = s1.replace('(G)', '').replace('(MEX)', '').replace('(MX)', '')
    s2 = s0.strip()
    for pat, val in RATING_RULES:
        if re.match(pat, s1) or re.match(pat, s2, flags=re.IGNORECASE):
            return float(val)
    return np.nan

def eq365(rate_dec, cap_series):
    base = 1.0 + (rate_dec / cap_series.replace(0, np.nan))
    base = pd.Series(base, index=cap_series.index).fillna(1.0)
    K = 360.0/365.0
    return (base.pow(cap_series / K) - 1.0) * K

def min_rating_from_row(row: pd.Series):
    fuentes = [
        ("S&P",     row.get("CALIFICACION_S_P", None)),
        ("MDYS",    row.get("CALIFICACION_MDYS", None)),
        ("HR",      row.get("CALIFICACION_HRRATING", None)),
        ("FITCH",   row.get("CALIFICACION_FITCH", None)),
        ("HOMO",    row.get("CALIFICACION_HOMOLOGADA", None)),
    ]
    mejor_val = np.nan; mejor_raw = ""; mejor_src = ""
    for src, raw in fuentes:
        val = rating_to_value(raw)
        if pd.isna(val): continue
        if pd.isna(mejor_val) or val < mejor_val:
            mejor_val = val; mejor_raw = str(raw) if raw is not None else ""; mejor_src = src
    return mejor_val, mejor_raw, mejor_src

def _parse_rate_any(x):
    if pd.isna(x): return np.nan
    s = str(x).strip().replace('%','').replace(' ','')
    if s.count(',') == 1 and s.count('.') == 0: s = s.replace(',', '.')
    s = re.sub(r'(?<=\d),(?=\d{3}\b)', '', s)
    try: return float(s)
    except: return np.nan

def _auto_to_decimal(series):
    vals = pd.to_numeric(series, errors='coerce')
    med = vals.dropna().median()
    return vals if (pd.notna(med) and 0 < med < 1) else vals * 0.01

@st.cache_data(ttl=900, show_spinner=True)
def map_productos() -> pd.DataFrame:
    return run_sql("""
        SELECT ID_PRODUCTO, COALESCE(DESCRIPCION,'SIN_DESCRIPCION') AS PRODUCTO
        FROM SIAPII.V_M_PRODUCTO
    """)

@st.cache_data(ttl=900, show_spinner=True)
def build_df_final(df_snap: pd.DataFrame, inflacion_anual: float) -> pd.DataFrame:
    if df_snap is None or df_snap.empty:
        return pd.DataFrame()

    df = df_snap.copy()

    # =========================
    # 1. Rating mínimo
    # =========================
    rating_info = df.apply(min_rating_from_row, axis=1, result_type='expand')
    rating_info.columns = ['VALOR_RATING_MIN', 'RAW_RATING_MIN', 'SRC_RATING_MIN']
    df = pd.concat([df, rating_info], axis=1)

    # =========================
    # 2. Tasas crudas y normalizadas
    # =========================
    raw_ytm   = df['EMIS_TASA'].apply(_parse_rate_any)
    raw_tbase = df.get('TASA_BASE', pd.Series([np.nan] * len(df))).apply(_parse_rate_any)

    ytm_dec   = _auto_to_decimal(raw_ytm)
    tbase_dec = _auto_to_decimal(raw_tbase)

    has_tref = df.get('ID_TASA_REFERENCIA', pd.Series([np.nan] * len(df)))
    mask_sin_ref = has_tref.isna()

    mask_raro = mask_sin_ref & raw_ytm.notna() & (raw_ytm.abs() > 2) & (raw_ytm.abs() <= 40)
    ytm_dec.loc[mask_raro] = (raw_ytm[mask_raro] / 100.0)

    mask_extremo_ytm = ytm_dec.abs() > 2
    ytm_dec.loc[mask_extremo_ytm] = np.nan

    mask_extremo_base = tbase_dec.abs() > 2
    tbase_dec.loc[mask_extremo_base] = np.nan

    # =========================
    # 3. Fechas y DxV
    # =========================
    f_vto   = pd.to_datetime(df['FECHA_VTO_EM'], errors='coerce')
    f_corte = pd.to_datetime(df['FECHA_CORTE'],   errors='coerce')
    dxv_bruto = (f_vto - f_corte).dt.days

    is_reporto = df['TIPO_PAPEL'].astype(str).str.contains('reporto', case=False, na=False) | \
                 df['TIPO_INSTRUMENTO'].astype(str).str.contains('reporto', case=False, na=False)
    is_cero = df['TIPO_INSTRUMENTO'].astype(str).str.contains('cero', case=False, na=False)

    dxv_mostrado = pd.Series(
        np.where(is_reporto, 1, dxv_bruto),
        index=df.index
    )

    plazo    = pd.to_numeric(df['PLAZO_CUPON'], errors='coerce')
    dxv_sql  = pd.to_numeric(df.get('DIAS_X_V', np.nan), errors='coerce')
    dxv_real = dxv_sql.where(dxv_sql.notna(), dxv_bruto)

    periodo_dias = pd.Series(
        np.where(
            is_reporto,
            1,
            np.where(
                is_cero & pd.notna(dxv_real) & (dxv_real > 0),
                dxv_real,
                plazo
            )
        ),
        index=df.index
    ).fillna(28).clip(lower=1)

    cap = 360.0 / periodo_dias

    # =========================
    # 4. Clasificación por tipo de instrumento
    # =========================
    infl = float(inflacion_anual)

    es_real = (
        df['TIPO_INSTRUMENTO'].astype(str).str.contains('tasa real', case=False, na=False)
        & (pd.to_numeric(df['ID_DIVISA_TV'], errors='coerce') == 8)
    )
    es_revisable = df['TIPO_INSTRUMENTO'].astype(str).str.contains('revis', case=False, na=False)

    mask_nominal = ~(es_real | es_revisable)

    # =========================
    # 5. Tasa equivalente 365 por tipo
    # =========================
    t_eq_nominal = eq365(ytm_dec, cap)

    t_in_revisable = tbase_dec.fillna(0.0) + ytm_dec.fillna(0.0)
    t_eq_revisable = eq365(t_in_revisable, cap)

    t_eq_real = eq365(ytm_dec, cap)
    K = 360.0 / 365.0
    t_nom_real = ((1.0 + (t_eq_real / K)) * (1.0 + (infl / K)) - 1.0) * K

    # =========================
    # 6. Carry final por instrumento
    # =========================
    t_carry = pd.Series(np.nan, index=df.index, dtype=float)
    t_carry[mask_nominal] = t_eq_nominal[mask_nominal]
    t_carry[es_revisable] = t_eq_revisable[es_revisable]
    t_carry[es_real]      = t_nom_real[es_real]

    # =========================
    # 7. Pesos, DxV y agregados de portafolio
    # =========================
    val_real = pd.to_numeric(df['VALOR_REAL'], errors='coerce').fillna(0.0)
    peso = (val_real / val_real.sum()) if val_real.sum() > 0 else pd.Series(0.0, index=df.index)

    val_nom_raw = pd.to_numeric(df['VALOR_NOMINAL'], errors='coerce').fillna(0.0) * 100.0
    val_nom_raw = np.where(is_reporto, 0.0, val_nom_raw)

    carry_total_pp = float((t_carry * peso).sum() * 100.0)
    dxv_total_pond = float((dxv_mostrado.fillna(0.0) * peso).sum())

    duracion_dias = pd.to_numeric(df.get('DURACION_DIAS', np.nan), errors='coerce')
    dur_portafolio = float((duracion_dias.fillna(0.0) * peso).sum()) if 'DURACION_DIAS' in df else None

    # =========================
    # 8. Tabla de detalle
    # =========================
    nombre = df['NOMBRE_EMISORA'].astype(str).fillna("")
    serie  = df.get('SERIE', pd.Series([""] * len(df))).astype(str).fillna("").replace("nan", "")
    instrumento = nombre.str.strip().str.cat(
        serie.apply(lambda s: (" " + s.strip()) if s and s.strip() else ""),
        na_rep=""
    )

    df_final = pd.DataFrame({
        'Tipo de Papel'       : df['TIPO_PAPEL'].astype(str),
        'Tipo de instrumento' : df['TIPO_INSTRUMENTO'].astype(str),
        'Instrumento'         : instrumento,
        'Fecha vto'           : f_vto.dt.date,
        'DxV'                 : dxv_mostrado,
        'Duración (días)'     : (pd.to_numeric(duracion_dias, errors='coerce').round(0).astype('Int64')
                                  if 'DURACION_DIAS' in df else pd.Series([pd.NA] * len(df))),
        'Tasa valuacion'      : [fmt_pct(x) for x in t_eq_nominal],
        'Carry (365 d)'       : [fmt_pct(x) for x in t_carry],
        'Valor Nominal'       : [f"{v:,.0f}" for v in val_nom_raw],
        'Monto'               : val_real.map(fmt_money2),
        '% Cartera'           : (peso * 100).map(lambda x: f"{x:.2f}%"),
        'Tasa ref'            : df.get('TASA_REF_NAME', pd.Series([''] * len(df))).astype(str),
        'Tasa base'           : df.get('TASA_BASE', pd.Series([np.nan] * len(df))),
        'Calificación'        : df['RAW_RATING_MIN'].fillna(df['CALIFICACION_HOMOLOGADA'].astype(str)),
        '_VALOR_RATING_MIN'   : df['VALOR_RATING_MIN'],
        '_ID_PRODUCTO'        : df['ID_PRODUCTO']
    })

    mp = map_productos()
    df_final = df_final.merge(mp, left_on="_ID_PRODUCTO", right_on="ID_PRODUCTO", how="left")
    df_final.drop(columns=["ID_PRODUCTO"], inplace=True, errors="ignore")
    df_final.rename(columns={"PRODUCTO": "Producto"}, inplace=True)

    ord_tp = {'Reporto': 1, 'Gubernamental': 2, 'CuasiGuber': 3, 'Banca Comercial': 4, 'Privado': 5}
    is_rep2 = df_final['Tipo de Papel'].str.contains('reporto', case=False, na=False) | \
              df_final['Tipo de instrumento'].str.contains('reporto', case=False, na=False)

    df_final['__ord__'] = np.where(is_rep2, 1, df_final['Tipo de Papel'].map(ord_tp).fillna(98))
    df_final['__m__']   = money_to_float_series(df_final['Monto'])

    df_detail = (df_final
                 .sort_values(['__ord__', '__m__'], ascending=[True, False])
                 .drop(columns=['__ord__', '__m__'])
                 .reset_index(drop=True))

    mask_rep_det = df_detail['Tipo de Papel'].str.contains('reporto', case=False, na=False) | \
                   df_detail['Tipo de instrumento'].str.contains('reporto', case=False, na=False)
    df_detail.loc[mask_rep_det, 'Calificación'] = 'MXAAA'

    if len(df_detail):
        row_total = {
            'Producto': '',
            'Tipo de Papel': '',
            'Tipo de instrumento': '',
            'Instrumento': 'TOTAL',
            'Fecha vto': '',
            'DxV': f"{dxv_total_pond:.0f}",
            'Duración (días)': (f"{dur_portafolio:.0f}" if dur_portafolio is not None else ''),
            'Tasa valuacion': '',
            'Carry (365 d)': f"{carry_total_pp:.2f}%",
            'Valor Nominal': '',
            'Monto': f"${float(money_to_float_series(df_detail['Monto']).sum()):,.2f}",
            '% Cartera': "100.00%",
            'Tasa ref': '',
            'Tasa base': '',
            'Calificación': '',
            '_VALOR_RATING_MIN': np.nan,
            '_ID_PRODUCTO': np.nan
        }
        df_detail = pd.concat([df_detail, pd.DataFrame([row_total])], ignore_index=True)

    return df_detail

# =========================
#  core_issuer y RV
# =========================
@st.cache_data(ttl=3600, show_spinner=True)
def core_issuer_map() -> pd.DataFrame:
    core = pg_run_sql("""
        SELECT issuer_name, ticker_symbol, sector, industry
        FROM core_issuer
        WHERE issuer_name IS NOT NULL
    """)
    if core.empty:
        return pd.DataFrame(columns=["issuer_name","Nombre Completo","sector","industry"])
    core = core.copy()
    core["issuer_name"] = core["issuer_name"].astype(str)
    core["ticker_symbol"] = core.get("ticker_symbol", pd.Series(index=core.index, dtype=object))
    core["sector"] = core.get("sector", pd.Series(index=core.index, dtype=object))
    core["industry"] = core.get("industry", pd.Series(index=core.index, dtype=object))

    def _mode_or_default(s, default_val):
        s = s.dropna()
        return s.value_counts().index[0] if len(s) else default_val

    agg = (core.groupby("issuer_name", dropna=False)
           .agg({
               "ticker_symbol": lambda s: _mode_or_default(s, None),
               "sector":        lambda s: _mode_or_default(s, "SIN SECTOR"),
               "industry":      lambda s: _mode_or_default(s, "SIN INDUSTRIA"),
           })
           .reset_index())

    agg["Nombre Completo"] = np.where(
        agg["ticker_symbol"].notna() & (agg["ticker_symbol"].astype(str).str.strip() != ""),
        agg["ticker_symbol"].astype(str),
        agg["issuer_name"].astype(str)
    )
    agg["Nombre Completo"] = agg["Nombre Completo"].str.split(",", n=1, expand=True)[0].str.strip()
    agg["sector"] = agg["sector"].fillna("SIN SECTOR")
    agg["industry"] = agg["industry"].fillna("SIN INDUSTRIA")
    return agg[["issuer_name","Nombre Completo","sector","industry"]]

@st.cache_data(ttl=900, show_spinner=True)
def rv_snapshot_por_producto(alias: str, f_ini: pd.Timestamp, f_fin_next: pd.Timestamp,
                             contratos_key: tuple[int, ...] | None = None) -> pd.DataFrame:
    filtro_fc, params_fc = build_contrato_filter_sql(contratos_key, "c1.ID_CLIENTE", "cid_rv_fc")
    filtro_main, params_main = build_contrato_filter_sql(contratos_key, "c.ID_CLIENTE", "cid_rv_main")

    SQL = f"""
    WITH FECHA_C AS (
      SELECT MAX(TRUNC(h.REGISTRO_CONTROL)) AS FECHA_CORTE
      FROM SIAPII.V_HIS_POSICION_CLIENTE h
      WHERE TRUNC(h.REGISTRO_CONTROL) >= TO_DATE(:f_ini_dt,'YYYY-MM-DD')
        AND TRUNC(h.REGISTRO_CONTROL) <  TO_DATE(:f_fin_dt,'YYYY-MM-DD')
        AND EXISTS (
            SELECT 1
            FROM SIAPII.V_M_CONTRATO_CDM c1
            WHERE c1.ALIAS_CDM = :alias
              AND c1.ID_CLIENTE = h.ID_CLIENTE
              {filtro_fc}
        )
    )
    SELECT
      h.ID_PRODUCTO,
      MAX(e.NOMBRE_EMISORA) AS NOMBRE_EMISORA,
      SUM(h.VALOR_REAL)     AS MONTO
    FROM SIAPII.V_HIS_POSICION_CLIENTE h
    JOIN FECHA_C fc ON TRUNC(h.REGISTRO_CONTROL) = fc.FECHA_CORTE
    JOIN SIAPII.V_M_CONTRATO_CDM c ON c.ID_CLIENTE = h.ID_CLIENTE AND c.ALIAS_CDM = :alias
    JOIN SIAPII.V_M_EMISORA e ON e.ID_EMISORA = h.ID_EMISORA
    WHERE (e.ID_TIPO_ACTIVO = 2 OR h.ID_PRODUCTO IN ({REPORTO_RV_CSV}))
      {filtro_main}
    GROUP BY h.ID_PRODUCTO, e.ID_EMISORA
    HAVING SUM(h.VALOR_REAL) IS NOT NULL
    """
    params = {
        "alias": alias,
        "f_ini_dt": f_ini.strftime("%Y-%m-%d"),
        "f_fin_dt": f_fin_next.strftime("%Y-%m-%d"),
    }
    params.update(params_fc)
    params.update(params_main)
    return run_sql(SQL, params)

# =========================
#  HISTÓRICO trimestral + duración
# =========================
@st.cache_data(ttl=3600, show_spinner=True)
def hist_trimestral_papel_instrumento(alias: str, id_tipo_activo: int, cutoff_next: pd.Timestamp,
                                      contratos_key: tuple[int, ...] | None = None):
    if contratos_key is not None and isinstance(contratos_key, pd.Index):
        contratos_key = tuple(map(int, contratos_key.tolist()))

    filtro_contratos, extra_params = build_contrato_filter_sql(contratos_key, "c.ID_CLIENTE", "cid_hist_tri")

    SQL = f"""
    WITH H AS (
      SELECT
        TRUNC(h.REGISTRO_CONTROL, 'Q') AS Q,
        CASE 
          WHEN h.ID_PRODUCTO IN ({REPORTO_RV_CSV}) THEN 2
          ELSE e.ID_TIPO_ACTIVO
        END AS ID_ACTIVO_LOGICO,
        e.TIPO_PAPEL,
        e.TIPO_INSTRUMENTO,
        SUM(h.VALOR_REAL) AS MONTO
      FROM SIAPII.V_HIS_POSICION_CLIENTE h
      JOIN SIAPII.V_M_EMISORA e ON e.ID_EMISORA = h.ID_EMISORA
      JOIN SIAPII.V_M_CONTRATO_CDM c ON c.ID_CLIENTE = h.ID_CLIENTE
      WHERE c.ALIAS_CDM = :alias
        {filtro_contratos}
        AND h.REGISTRO_CONTROL >= TO_DATE('2020-01-01','YYYY-MM-DD')
        AND h.REGISTRO_CONTROL <  TO_DATE(:cutoff_next,'YYYY-MM-DD')

      GROUP BY TRUNC(h.REGISTRO_CONTROL, 'Q'),
               CASE 
                 WHEN h.ID_PRODUCTO IN ({REPORTO_RV_CSV}) THEN 2
                 ELSE e.ID_TIPO_ACTIVO
               END,
               e.TIPO_PAPEL, e.TIPO_INSTRUMENTO
    ),
    FILT AS (
      SELECT Q, TIPO_PAPEL, TIPO_INSTRUMENTO, MONTO
      FROM H WHERE ID_ACTIVO_LOGICO = :id_act
    ),
    TOT AS ( SELECT Q, SUM(MONTO) AS TOT FROM FILT GROUP BY Q )
    SELECT
      TO_CHAR(f.Q,'YYYY') || '-Q' || TO_CHAR(f.Q,'Q') AS PERIODO,
      f.TIPO_PAPEL,
      f.TIPO_INSTRUMENTO,
      f.MONTO,
      t.TOT,
      CASE WHEN t.TOT=0 OR t.TOT IS NULL THEN 0 ELSE (f.MONTO/t.TOT)*100 END AS PCT
    FROM FILT f
    JOIN TOT  t ON t.Q = f.Q
    """
    params = {
    "alias": alias,
    "id_act": id_tipo_activo,
    "cutoff_next": pd.to_datetime(cutoff_next).strftime("%Y-%m-%d")
}
    params.update(extra_params)
    df = run_sql(SQL, params)
    if df.empty:
        return (pd.DataFrame(columns=["PERIODO","TIPO_PAPEL","Pct"]),
                pd.DataFrame(columns=["PERIODO","TIPO_INSTRUMENTO","Pct"]))
    df = df.rename(columns={"PCT": "Pct"})
    df["Pct"] = pd.to_numeric(df["Pct"], errors="coerce").fillna(0.0)
    por_papel = df.groupby(["PERIODO","TIPO_PAPEL"], dropna=False)["Pct"].sum().reset_index()
    por_instr = df.groupby(["PERIODO","TIPO_INSTRUMENTO"], dropna=False)["Pct"].sum().reset_index()
    def _key(p):
        y, q = p.split("-Q")
        return (int(y), int(q))
    por_papel = por_papel.sort_values(by="PERIODO", key=lambda s: s.map(_key)).reset_index(drop=True)
    por_instr = por_instr.sort_values(by="PERIODO", key=lambda s: s.map(_key)).reset_index(drop=True)
    return por_papel, por_instr

@st.cache_data(ttl=1800, show_spinner=True)
def deuda_duracion_historico(alias: str, inflacion_anual: float, f_ref_fin: pd.Timestamp,
                             contratos_key: tuple[int, ...] | None = None) -> pd.DataFrame:
    filas = []
    ref_period = f_ref_fin.to_period("M")
    for k in range(11, -1, -1):
        periodo = ref_period - k
        mes_end = periodo.to_timestamp("M")
        mes_ini = mes_end.replace(day=1)
        mes_end_next = mes_end + pd.Timedelta(days=1)
        df_snap = query_snapshot_deuda(alias, mes_ini, mes_end_next, contratos_key)
        df_det = build_df_final(df_snap, inflacion_anual)
        if df_det is None or df_det.empty:
            continue
        total_row = df_det[df_det["Instrumento"].astype(str).str.upper() == "TOTAL"].tail(1)
        if total_row.empty:
            continue
        dur = pd.to_numeric(total_row["Duración (días)"], errors="coerce").iloc[0]
        if pd.isna(dur):
            continue
        filas.append({"MES": mes_end, "DURACION_DIAS": float(dur)})
    if not filas:
        return pd.DataFrame(columns=["MES", "DURACION_DIAS"])
    return pd.DataFrame(filas).sort_values("MES").reset_index(drop=True)

# =========================
#  CONSULTAS BASE / PARAMS
# =========================
with st.spinner("Consultando Oracle / Postgres y construyendo vistas…"):
    QUERY_BASE_AA, params_aa = build_query_base_unfiltered(ALIAS_CDM, FECHA_ESTADISTICA, CONTRATOS_KEY)
    base = run_sql(QUERY_BASE_AA, params=params_aa)
    if not base.empty:
        base["MONTO"] = pd.to_numeric(base["MONTO"], errors="coerce").fillna(0.0)
        by_activo = base.groupby("ACTIVO", dropna=False)["MONTO"].sum().sort_values(ascending=False)
        by_producto = base.groupby(["PRODUCTO","ACTIVO"], dropna=False)["MONTO"].sum().reset_index()
        df_aa_activo = (by_activo.reset_index()
                        .rename(columns={"MONTO":"Monto","ACTIVO":"Categoria"})
                        .assign(Porcentaje=lambda d: (d["Monto"]/d["Monto"].sum()*100).round(2))
                        .sort_values("Monto", ascending=False).reset_index(drop=True))
        df_aa_producto = (by_producto
                          .assign(Porcentaje=lambda d: (d["MONTO"]/d["MONTO"].sum()*100).round(2))
                          .rename(columns={"MONTO":"Monto"})
                          .sort_values("Monto", ascending=False)
                          .reset_index(drop=True))
    else:
        df_aa_activo = pd.DataFrame(columns=["Categoria","Monto","Porcentaje"])
        df_aa_producto = pd.DataFrame(columns=["PRODUCTO","ACTIVO","Monto","Porcentaje"])

cto_m_anual, cto_ytd_anual, df_rend_prod = rend_bruto_contrato_y_producto(ALIAS_CDM, y, m, CONTRATOS_KEY)
df_hist_rend      = rend_bruto_contrato_hist_12m(ALIAS_CDM, y, m, CONTRATOS_KEY)
df_hist_rend_prod = rend_bruto_producto_hist_12m(ALIAS_CDM, y, m, CONTRATOS_KEY)
df_hist_rend_5y      = rend_bruto_contrato_hist_n_years(ALIAS_CDM, y, m, n_years=5, contratos_key=CONTRATOS_KEY)
df_hist_rend_prod_5y = rend_bruto_producto_hist_n_years(ALIAS_CDM, y, m, n_years=5, contratos_key=CONTRATOS_KEY)

with st.spinner("Calculando Deuda…"):
    df_snap_deuda = query_snapshot_deuda(ALIAS_CDM, F_DIA_INI, F_DIA_FIN_NEXT, CONTRATOS_KEY)
    df_final_deuda = build_df_final(df_snap_deuda, INFLACION_ANUAL)

rv_df_raw = rv_snapshot_por_producto(ALIAS_CDM, F_DIA_INI, F_DIA_FIN_NEXT, CONTRATOS_KEY)
core_map_df = core_issuer_map()
rv_enriq_base = pd.DataFrame()
if not rv_df_raw.empty:
    rv_enriq_base = rv_df_raw.merge(core_map_df, left_on="NOMBRE_EMISORA", right_on="issuer_name", how="left")
    mp_rv = map_productos()
    rv_enriq_base = rv_enriq_base.merge(mp_rv[["ID_PRODUCTO","PRODUCTO"]], on="ID_PRODUCTO", how="left")
    rv_enriq_base.rename(columns={"PRODUCTO": "Producto"}, inplace=True)
    rv_enriq_base["industry"] = rv_enriq_base["industry"].fillna("SIN INDUSTRIA")
    rv_enriq_base["sector"] = rv_enriq_base["sector"].fillna("SIN SECTOR")
    rv_enriq_base["Nombre Completo"] = rv_enriq_base.get("Nombre Completo", rv_enriq_base["NOMBRE_EMISORA"].astype(str))
    rv_enriq_base["Nombre Completo"] = rv_enriq_base["Nombre Completo"].astype(str).str.split(",", n=1, expand=True)[0].str.strip()

hist_deuda_papel, hist_deuda_instr = hist_trimestral_papel_instrumento(ALIAS_CDM, 1, F_DIA_FIN_NEXT, CONTRATOS_KEY)
hist_rv_papel, hist_rv_instr = hist_trimestral_papel_instrumento(ALIAS_CDM, 2, F_DIA_FIN_NEXT, CONTRATOS_KEY)
hist_dur = deuda_duracion_historico(ALIAS_CDM, INFLACION_ANUAL, F_DIA_FIN, CONTRATOS_KEY)

# =========================
#  TÍTULO
# =========================
st.markdown("<br>", unsafe_allow_html=True)
NOMBRE_CLIENTE = get_nombre_cliente(ALIAS_CDM)

if not print_mode:
    st.markdown("<br>", unsafe_allow_html=True)
    st.title(f"REPORTE {NOMBRE_CLIENTE}")
    st.markdown(
        f'<span class="chip" style="color:#0f172a;">FECHA: {FECHA_ESTADISTICA}</span>',
        unsafe_allow_html=True
    )
    st.markdown("<br>", unsafe_allow_html=True)
else:
    st.title(f"REPORTE {NOMBRE_CLIENTE}")
    st.markdown(
        f'<span class="chip" style="color:#0f172a;">FECHA: {FECHA_ESTADISTICA}</span>',
        unsafe_allow_html=True
    )
st.markdown("<br>", unsafe_allow_html=True)

# =========================
#  VISUALES BÁSICOS
# =========================
def donut_figure(labels, values, title: str, height=400, top_n: int | None = None, kind: str = "money") -> go.Figure:
    vals = pd.to_numeric(pd.Series(values), errors='coerce').fillna(0.0).values
    labs = pd.Series(labels).astype(str).values
    total = float(np.nansum(vals))
    if total <= 0:
        labs, vals, total = np.array(["Sin datos"]), np.array([1.0]), 0.0
    else:
        order = np.argsort(-vals)
        labs, vals = labs[order], vals[order]
        if top_n is not None and top_n > 0:
            labs, vals = labs[:top_n], vals[:top_n]
    if kind == "money":
        textinfo = "percent"
        texttemplate = "%{percent:.1%}"
        hovertemplate = "%{label}<br>$%{value:,.0f} (%{percent:.1%})<extra></extra>"
        annot_text = f"Total<br>${total:,.0f}"
    else:
        textinfo = "label+text"
        texttemplate = "%{value:.1f}%"
        hovertemplate = "%{label}<br>%{value:.2f}%<extra></extra>"
        annot_text = f"Total<br>{total:.1f}%"
    fig = go.Figure(data=[go.Pie(
        labels=labs, values=vals, hole=.55, sort=False,
        textinfo=textinfo, texttemplate=texttemplate,
        hovertemplate=hovertemplate
    )])
    fig.update_layout(
        title=title, showlegend=True, legend=LEGEND_RIGHT,
        margin=dict(l=10, r=220, t=42, b=6),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color='#0f172a'), height=height,
        annotations=[dict(text=annot_text, x=0.5, y=0.5, font=dict(size=12), showarrow=False)]
    )
    return fig

def area100_from_pivot(pvt: pd.DataFrame, title: str, height=BARH_H, tickvals=None):
    if pvt.empty:
        fig = go.Figure()
        fig.update_layout(title=title, height=height)
        return fig
    ord_cols = pvt.mean(axis=0).sort_values(ascending=False).index.tolist()
    pvt = pvt[ord_cols]
    fig = go.Figure()
    for col in pvt.columns:
        fig.add_trace(go.Scatter(
            x=pvt.index, y=pvt[col], mode="lines", stackgroup="one", groupnorm="percent",
            name=str(col), hovertemplate="%{x}<br>%{y:.2f}%<extra></extra>"
        ))
    xaxis_args = dict(title="Periodo", tickangle=TICKANGLE)
    if tickvals is not None:
        xaxis_args["tickmode"] = "array"
        xaxis_args["tickvals"] = tickvals
    fig.update_layout(
        title=title,
        yaxis=dict(title="% cartera", range=[0,100], ticksuffix="%"),
        xaxis=xaxis_args,
        legend=LEGEND_RIGHT,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=220, t=42, b=6),
        height=height
    )
    return fig

def plot_rend_producto_series(
    df_hist_prod_12m: pd.DataFrame,
    df_hist_prod_5y: pd.DataFrame,
    producto: str,
    modo: str,
    bench_pack: pd.DataFrame | None = None
):
    """
    Grafica:
      - Mensual 12m (Oracle) + Benchmark mensual
      - Acumulado por año 5y (Oracle) + Benchmark anual (1 punto por año)
    Reglas:
      - Eje X real (FECHA month-end)
      - Rotación automática si se amontona (más en impresión)
      - Puntos visibles
      - Tooltips sin decimales
      - Etiquetas sin decimales en impresión
      - Leyenda con nombre real del benchmark si viene BENCH_LABEL
    """

    # -------- Mensual (12m) --------
    dfp = df_hist_prod_12m[df_hist_prod_12m["PRODUCTO"] == producto].copy()
    if dfp.empty:
        st.info("Sin rendimientos disponibles para este producto.")
        return

    dfp = dfp.sort_values(["ANIO", "MES"]).copy()
    dfp = _month_end_from_anio_mes(dfp, "ANIO", "MES", "FECHA")

    # Merge benchmark SOLO por FECHA month-end
    if bench_pack is not None and not bench_pack.empty:
        bp = bench_pack.copy()
        bp["FECHA"] = pd.to_datetime(bp["FECHA"], errors="coerce")
        bp = bp.dropna(subset=["FECHA"]).copy()
        bp["FECHA"] = (bp["FECHA"] + pd.offsets.MonthEnd(0)).dt.normalize()
        bp = bp.sort_values("FECHA").drop_duplicates(subset=["FECHA"], keep="last")
        dfp = dfp.merge(bp, on="FECHA", how="left")
        # ===============================
        # FIX FINAL: no permitir meses > corte del sidebar
        # ===============================
        end_ref = _get_cutoff_month_end()

        dfp["FECHA"] = pd.to_datetime(dfp["FECHA"], errors="coerce")
        dfp = dfp[dfp["FECHA"] <= end_ref].copy()

    # columnas Oracle
    col_m = "TASA_M_ANUAL" if modo == "Anualizado" else "TASA_M_EFEC"
    dfp[col_m] = pd.to_numeric(dfp[col_m], errors="coerce")

    # ✅ EJE X coherente con el corte del reporte (y,m) y sin meses "fantasma"
    end_ref = F_DIA_FIN  # cierre de mes aplicado en sidebar
    dfp = _clip_monthly_df(dfp, end_ref, date_col="FECHA")
    spine = _month_end_spine(end_ref, n=12)
    dfp = _reindex_to_month_spine(dfp, spine, date_col="FECHA")
   
    # Figura mensual
    fig_m = go.Figure()
    y_port = dfp[col_m] * 100.0

    fig_m.add_trace(go.Bar(
        x=dfp["FECHA"],
        y=y_port,
        name="Rendimientos",
        text=[f"{v:.1f}%" if pd.notna(v) else "" for v in y_port],
        hovertemplate="%{x|%b-%Y}<br>%{y:.1f}%<extra></extra>",
    ))

    # Benchmark mensual (respeta anualizado si existe BENCH_M_ANUAL)
    bench_name = "Benchmark"
    if "BENCH_LABEL" in dfp.columns and dfp["BENCH_LABEL"].notna().any():
        bench_name = str(dfp["BENCH_LABEL"].dropna().iloc[-1])

    if "BENCH_M" in dfp.columns:
        bm = None
        if modo == "Anualizado" and "BENCH_M_ANUAL" in dfp.columns:
            bm = pd.to_numeric(dfp["BENCH_M_ANUAL"], errors="coerce")
        else:
            bm = pd.to_numeric(dfp["BENCH_M"], errors="coerce")

        if bm is not None and bm.notna().any():
            fig_m.add_trace(go.Bar(
                x=dfp["FECHA"],
                y=bm * 100.0,
                name=bench_name,
            cliponaxis=False,
            hovertemplate="%{x|%b-%Y}<br>%{y:.1f}%<extra></extra>",
            ))

    fig_m.update_layout(barmode="group")
    fig_m.update_yaxes(title="Rendimiento (%)", ticksuffix="%", showgrid=True)
    _style_time_xaxis(fig_m, n_points=len(dfp), print_mode=print_mode)
    _style_fig_for_mode(fig_m, print_mode=print_mode)
    # Benchmark (composición) bajo la gráfica (producto)
    rows_bm_prod = get_bench_ficha_rows(
        alias_cdm=globals().get("ALIAS_CDM", ""),
        nombre_corto_focus=globals().get("NOMBRE_CORTO_FOCUS"),
        producto=str(producto),
        modo=None,
    )
    footer_bm_prod = bench_ficha_to_markdown(rows_bm_prod, title="Benchmark (composición)")
    render_print_block(" ", fig_m, print_mode=print_mode, break_after=True, footer_md=footer_bm_prod)

    # -------- Acumulado (por año, 5y) --------
    tmp = build_yearly_accum_series(df_hist_prod_5y, modo, y, m, n_years=5, producto=producto)
    if isinstance(tmp, tuple) and len(tmp) == 2:
        x_years, y_years = tmp
    else:
        x_years, y_years = [], []

    if len(x_years) == 0:
        st.caption("Sin histórico suficiente para acumulado anual.")
        return

    fig_a = go.Figure()
    fig_a.add_trace(go.Bar(
        x=x_years,
        y=y_years,
        name="Acumulado anual",
        text=[f"{v:.1f}%" if (v is not None and not np.isnan(v)) else "" for v in y_years] if print_mode else None,
        hovertemplate="%{x}<br>%{y:.1f}%<extra></extra>",
    ))

    # benchmark anual por año (usa BENCH_YTD / BENCH_YTD_ANUAL)
    if bench_pack is not None and not bench_pack.empty:
        col_b = "BENCH_YTD_ANUAL" if modo == "Anualizado" else "BENCH_YTD"

        bp = bench_pack.copy()
        bp["FECHA"] = pd.to_datetime(bp["FECHA"], errors="coerce")
        bp = bp.dropna(subset=["FECHA"]).copy()
        bp["FECHA"] = (bp["FECHA"] + pd.offsets.MonthEnd(0)).dt.normalize()
        bp["ANIO"] = bp["FECHA"].dt.year
        bp["MES"] = bp["FECHA"].dt.month

        y_bench = []
        for yy in [int(x) for x in x_years]:
            sub = bp[bp["ANIO"] == yy].copy()
            if sub.empty or col_b not in sub.columns:
                y_bench.append(np.nan)
                continue
            # preferir diciembre, si no, último mes disponible
            if (sub["MES"] == 12).any():
                row = sub[sub["MES"] == 12].sort_values("FECHA").iloc[-1]
            else:
                row = sub.sort_values("FECHA").iloc[-1]
            v = pd.to_numeric(row.get(col_b), errors="coerce")
            y_bench.append(float(v) * 100.0 if pd.notna(v) else np.nan)

        if any(pd.notna(y_bench)):
            bench_name2 = "Benchmark"
            if "BENCH_LABEL" in bp.columns and bp["BENCH_LABEL"].notna().any():
                bench_name2 = str(bp["BENCH_LABEL"].dropna().iloc[-1])

            fig_a.add_trace(go.Bar(
                x=x_years,
                y=y_bench,
                name=bench_name2,
                text=[f"{v:.1f}%" if (v==v) else "" for v in y_bench],
                hovertemplate="%{x}<br>%{y:.1f}%<extra></extra>",
            ))

    fig_a.update_layout(barmode="group")
    fig_a.update_yaxes(title="Rendimiento (%)", ticksuffix="%", showgrid=True)
    _style_fig_for_mode(fig_a, print_mode=print_mode)
    # Benchmark (composición) bajo la gráfica (producto)
    rows_bm_prod_a = get_bench_ficha_rows(
        alias_cdm=globals().get("ALIAS_CDM", ""),
        nombre_corto_focus=globals().get("NOMBRE_CORTO_FOCUS"),
        producto=str(producto),
        modo=None,
    )
    footer_bm_prod_a = bench_ficha_to_markdown(rows_bm_prod_a, title="Benchmark (composición)")
    render_print_block(" ", fig_a, print_mode=print_mode, break_after=True, footer_md=footer_bm_prod_a)

# =========================
#  BENCHMARKS: CACHE HELPERS
# =========================
@st.cache_data(show_spinner=False)
def _bench_map_cached():
    return load_bench_map(BENCH_MAP_FILE)

@st.cache_data(show_spinner=False)
def _bench_levels_cached(alias_cdm: str, nombre_corto: str, producto: str | None):
    df_map = _bench_map_cached()
    rows = get_bench_rows(df_map, alias_cdm=alias_cdm, nombre_corto=nombre_corto, producto=producto)
    return build_benchmark_series(rows, BENCH_FILES)  # FECHA, BENCH (nivel)

bench_map_df = load_bench_map(BENCH_MAP_FILE)
# =========================
#  RENDER SECCIONES
# =========================
def render_resumen():
    # KPIs
    total_port = float(df_aa_activo["Monto"].sum()) if len(df_aa_activo) else 0.0
    n_productos = int(df_aa_producto["PRODUCTO"].nunique()) if len(df_aa_producto) else 0
    n_contratos = get_num_contratos(ALIAS_CDM)

    top_prod_row = (
        df_aa_producto.sort_values("Monto", ascending=False).head(1)
        if len(df_aa_producto) else pd.DataFrame()
    )
    top_prod_nom = str(top_prod_row["PRODUCTO"].iloc[0]) if not top_prod_row.empty else "—"
    top_prod_pct = float(top_prod_row["Porcentaje"].iloc[0]) if not top_prod_row.empty else 0.0
    top_prod_mnt = float(top_prod_row["Monto"].iloc[0]) if not top_prod_row.empty else 0.0

    kpi_rend_mes = "—"
    kpi_rend_ytd = "—"
    if df_hist_rend is not None and not df_hist_rend.empty:
        sel = df_hist_rend[(df_hist_rend["ANIO"] == y) & (df_hist_rend["MES"] == m)]
        if not sel.empty:
            row = sel.iloc[0]
            v_m = row.get("TASA_M_ANUAL", np.nan)
            v_y = row.get("TASA_ACUM_ANUAL", np.nan)
            if pd.notna(v_m):
                kpi_rend_mes = f"{float(v_m) * 100:.2f}%"
            if pd.notna(v_y):
                kpi_rend_ytd = f"{float(v_y) * 100:.2f}%"

        # =========================
    # KPIs: primero PORTAFOLIO TOTAL
    # =========================
    resumen_portafolio = {
        "Total Portafolio": f"${total_port:,.2f}",
        "# Contratos": f"{n_contratos:,}",
        "No. Estrategias": f"{n_productos:,}",
        "Rend. mensual (anualizado)": kpi_rend_mes,
        "Rend. acum. año (anualizado)": kpi_rend_ytd,
    }

    st.markdown(
        '<div class="kpi-grid">' +
        "".join(
            f'<div class="kpi-card"><div class="kpi-label">{k}</div><div class="kpi-value">{v}</div></div>'
            for k, v in resumen_portafolio.items()
        ) +
        '</div>',
        unsafe_allow_html=True
    )

    st.markdown("<hr/>", unsafe_allow_html=True)

    # =========================
    # KPIs: después TOP
    # =========================
    resumen_top = {
        "Top Estrategia": top_prod_nom,
        "Top %": f"{top_prod_pct:.2f}%",
        "Top Monto": f"${top_prod_mnt:,.2f}",
    }

    st.markdown(
        '<div class="kpi-grid">' +
        "".join(
            f'<div class="kpi-card"><div class="kpi-label">{k}</div><div class="kpi-value">{v}</div></div>'
            for k, v in resumen_top.items()
        ) +
        '</div>',
        unsafe_allow_html=True
    )

    # PRINCIPALES HOLDINGS
    c1, c2 = st.columns((1, 1))

    rv_series = pd.Series(dtype=float)
    if not rv_enriq_base.empty:
        rv_series = (
            rv_enriq_base.groupby("industry")["MONTO"].sum()
            .rename_axis("Categoria").astype(float)
        )

    deuda_series = pd.Series(dtype=float)
    if not df_final_deuda.empty:
        mask_det = df_final_deuda["Instrumento"].astype(str).str.upper() != "TOTAL"
        tmp = df_final_deuda.loc[mask_det].copy()
        tmp["Tipo de instrumento"] = tmp["Tipo de instrumento"].replace(
            {None: "Reporto Guber Excento", "none": "Reporto Guber Excento", "None": "Reporto Guber Excento"}
        )
        monto_num = money_to_float_series(tmp["Monto"])
        deuda_series = monto_num.groupby(tmp["Tipo de instrumento"]).sum()
        deuda_series.index = deuda_series.index.astype(str)

    combined = pd.concat([
        rv_series.rename(lambda x: f"RV · {x}"),
        deuda_series.rename(lambda x: f"DEUDA · {x}")
    ]).groupby(level=0).sum().sort_values(ascending=False)

    combined_top = combined.head(5)

    with c1:
        if total_port <= 0 or len(combined_top) == 0:
            st.info("Sin datos suficientes para los principales holdings del portafolio.")
        else:
            etiquetas = combined_top.index.tolist()
            montos = combined_top.values.astype(float)
            pct_sobre_total = (montos / total_port * 100.0)

            fig_hold = go.Figure()
            for lab, pct in zip(etiquetas, pct_sobre_total):
                fig_hold.add_trace(go.Bar(
                    x=["Portafolio"],
                    y=[pct],
                    name=lab,
                    text=[f"{pct:.1f}%"],
                    hovertemplate="%{x}<br>" + lab + ": %{y:.2f}%<extra></extra>",
                ))

            fig_hold.update_layout(
                barmode="stack",
                title="Principales holdings del portafolio (Top 5)",
                yaxis=dict(title="% del portafolio", ticksuffix="%", range=[0, 100]),
                xaxis=dict(title=""),
                legend=LEGEND_RIGHT,
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                margin=dict(l=10, r=220, t=42, b=6),
                height=CHART_H
            )
            fig_hold.update_traces(textfont_size=9, cliponaxis=False)
            fig_hold = add_datapoints_to_fig(fig_hold, decimals=1)
            st.plotly_chart(fig_hold, use_container_width=True, config={"displayModeBar": False})

    with c2:
        if len(combined_top) == 0 or total_port <= 0:
            st.info("Sin datos para el detalle de holdings.")
        else:
            df_donut = combined_top.reset_index()
            df_donut.columns = ["Categoría", "Monto"]
            df_donut["% Portafolio"] = (df_donut["Monto"] / total_port * 100).round(2)
            df_donut["Monto"] = df_donut["Monto"].map(lambda x: f"${x:,.2f}")
            df_donut["% Portafolio"] = df_donut["% Portafolio"].map(lambda x: f"{x:.2f}%")
            st.markdown("**Detalle Top 5 holdings**")
            if print_mode:
                tiny_table_print(df_donut)
            else:
                st.dataframe(df_donut, hide_index=True, use_container_width=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ==========================================================
    # Rendimientos 12m (contrato) + Benchmark PORTAFOLIO TOTAL
    # ==========================================================
    st.markdown("### Rendimiento bruto del contrato")    # Modo fijo (Portafolio/Deuda): Anualizado
    modo = "Anualizado"

    # --- siempre inicializa ---
    bench_pack = None
    nombre_corto_focus = str(st.session_state.get("NOMBRE_CORTO_FOCUS", "")).strip()

    # PORTAFOLIO TOTAL => producto=None (según nuestra regla)
    if nombre_corto_focus:
        try:
            bench_pack = build_bench_pack_from_map(
                bench_map_df=bench_map_df,
                alias_cdm=ALIAS_CDM,
                nombre_corto=nombre_corto_focus,
                producto=None,          # ✅ PORTAFOLIO TOTAL
                bench_files=BENCH_FILES,
            )
            if bench_pack is not None and bench_pack.empty:
                bench_pack = None
        except Exception as e:
            st.caption(f"Benchmarks (PORTAFOLIO TOTAL): no se pudo construir. ({e})")
            bench_pack = None

    if df_hist_rend is None or df_hist_rend.empty:
        st.caption("No hay información de rendimientos brutos para los últimos 12 meses.")
        return

    dfh = df_hist_rend.sort_values(["ANIO", "MES"]).copy()

    # FECHA month-end + LABEL
    fechas_ini = pd.to_datetime(dict(year=dfh["ANIO"], month=dfh["MES"], day=1), errors="coerce")
    dfh["LABEL"] = fechas_ini.dt.strftime("%b-%y")
    dfh["FECHA"] = fechas_ini.dt.to_period("M").dt.to_timestamp("M")

    # merge benchmark por FECHA month-end
    if bench_pack is not None and not bench_pack.empty:
        bp = bench_pack.copy()
        bp["FECHA"] = pd.to_datetime(bp["FECHA"], errors="coerce")
        bp = bp.dropna(subset=["FECHA"])
        bp["FECHA"] = bp["FECHA"].dt.to_period("M").dt.to_timestamp("M")
        bp = bp.sort_values("FECHA").drop_duplicates(subset=["FECHA"], keep="last")
        # trae BENCH_LABEL para que la leyenda muestre el nombre real
        cols_bp = ["FECHA", "BENCH_M", "BENCH_YTD"]
        if "BENCH_LABEL" in bp.columns:
            cols_bp.append("BENCH_LABEL")

        dfh = dfh.merge(bp[cols_bp], on="FECHA", how="left")
        # ===============================
        # FIX FINAL: no permitir meses > corte del sidebar
        # ===============================
        end_ref = _get_cutoff_month_end()

        dfh["FECHA"] = pd.to_datetime(dfh["FECHA"], errors="coerce")
        dfh = dfh[dfh["FECHA"] <= end_ref].copy()


    # columnas Oracle
    if modo == "Anualizado":
        col_m = "TASA_M_ANUAL"
    else:
        col_m = "TASA_M_EFEC"

    m_vals = (pd.to_numeric(dfh[col_m], errors="coerce") * 100.0).round(2)
    x_labels = dfh["LABEL"].tolist()

    # =========================
    # Mensual (12m)
    # =========================
    d = _month_end_from_anio_mes(dfh, "ANIO", "MES", "FECHA")
    d[col_m] = pd.to_numeric(d[col_m], errors="coerce")

    # ✅ EJE X coherente con el corte del reporte (y,m) y sin meses "fantasma"
    end_ref = F_DIA_FIN  # cierre de mes aplicado en sidebar
    d = _clip_monthly_df(d, end_ref, date_col="FECHA")
    spine = _month_end_spine(end_ref, n=12)
    d = _reindex_to_month_spine(d, spine, date_col="FECHA")
    d = d.sort_values("FECHA").copy()
    fig_m = go.Figure()

    # --- Serie portafolio (mensual) en % ---
    y_port = pd.to_numeric(d[col_m], errors="coerce") * 100.0

    fig_m.add_trace(go.Bar(
        name="Rendimiento",
        x=d["FECHA"],
        y=y_port,
        text=[f"{v:.1f}%" if pd.notna(v) else "" for v in y_port],
        textposition="outside"
    ))

    if "BENCH_M" in d.columns:
        y_bench = pd.to_numeric(d["BENCH_M"], errors="coerce") * 100.0

        bench_name = "Benchmark"
        if "BENCH_LABEL" in d.columns and d["BENCH_LABEL"].notna().any():
            bench_name = str(d["BENCH_LABEL"].dropna().iloc[-1])

        fig_m.add_trace(go.Bar(
            name=bench_name,
            x=d["FECHA"],
            y=y_bench,
            text=[f"{v:.1f}%" if pd.notna(v) else "" for v in y_bench],
            textposition="outside"
        ))

    fig_m.update_yaxes(title="Rendimiento (%)", ticksuffix="%", showgrid=True)

    _style_time_xaxis(fig_m, n_points=len(d), print_mode=print_mode)
    _style_fig_for_mode(fig_m, print_mode=print_mode)
    # Benchmark (composición) bajo la gráfica
    rows_bm_pf = get_bench_ficha_rows(
        alias_cdm=ALIAS_CDM,
        nombre_corto_focus=NOMBRE_CORTO_FOCUS,
        producto=None,  # contrato / portafolio
        modo=None,
    )
    footer_bm_pf = bench_ficha_to_markdown(rows_bm_pf, title="Benchmark (composición)")
    render_print_block(" ", fig_m, print_mode=print_mode, break_after=True, footer_md=footer_bm_pf)

    # =========================
    # Acumulado por año (últimos 5 años)
    # =========================
    x_years, y_years = build_yearly_accum_series(df_hist_rend_5y, modo, y, m, n_years=5)
        # Benchmark anual (si hay bench_pack)
    x_b, y_b = [], []
    bench_name_y = "Benchmark"
    if bench_pack is not None and not bench_pack.empty:
        x_b, y_b = build_yearly_accum_series_from_bench_pack(bench_pack, y_ref=y, m_ref=m, n_years=5)
        if "BENCH_LABEL" in bench_pack.columns and bench_pack["BENCH_LABEL"].notna().any():
            bench_name_y = str(bench_pack["BENCH_LABEL"].dropna().iloc[-1])

    # Gráfica anual vs benchmark
    if x_years:
        fig_y = go.Figure()
        fig_y.add_trace(go.Bar(name="Acumulado Anual", x=x_years, y=y_years))

        # Solo agrega bench si alinea y tiene datos
        if x_b and (x_b == x_years):
            fig_y.add_trace(go.Bar(name=bench_name_y, x=x_b, y=y_b))

        fig_y.update_layout(
            barmode="group",
            margin=dict(l=10, r=10, t=10, b=10),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1.0),
        )
        fig_y.update_yaxes(title="Rendimiento (%)", ticksuffix="%", showgrid=True)

        _style_fig_for_mode(fig_y, print_mode=print_mode)
        render_print_block(" ", fig_y, print_mode=print_mode, break_after=True)

def render_allocation_general():
    st.subheader("Portafolio")
    if not len(df_aa_producto):
        st.info("Sin productos en el periodo seleccionado.")
        return
    serie_prod = df_aa_producto.groupby("PRODUCTO")["Monto"].sum().sort_values(ascending=False)
    total_monto = float(serie_prod.sum())
    c1, c2 = st.columns((1,1))
    with c1:
        st.plotly_chart(
            donut_figure(serie_prod.index.tolist(), serie_prod.values.tolist(),
                         "Distribución por estrategia"),
            use_container_width=True, config={"displayModeBar": False}
        )
    with c2:
        df_tab = serie_prod.reset_index()
        df_tab.columns = ["Estrategia","Monto"]
        df_tab["%"] = (df_tab["Monto"]/total_monto*100).round(2)
        df_tab["Monto"] = df_tab["Monto"].map(lambda x: f"${x:,.2f}")
        df_tab["%"] = df_tab["%"].map(lambda x: f"{x:.2f}%")
        st.markdown("**Detalle**")
        if print_mode:
            tiny_table_print(df_tab)
        else:
            st.dataframe(df_tab, hide_index=True, use_container_width=True)

def render_allocation_detalle():
    st.subheader("Distribución por estrategia")
    prod_deuda = df_aa_producto[df_aa_producto["ACTIVO"]=="Deuda"]["PRODUCTO"].dropna().unique().tolist()
    prod_rv    = df_aa_producto[df_aa_producto["ACTIVO"]=="Renta Variable"]["PRODUCTO"].dropna().unique().tolist()
    c1, c2 = st.columns(2)
    with c1:
        sel_prod_deuda = st.multiselect("Estrategia — Deuda", options=prod_deuda, default=prod_deuda[:min(6, len(prod_deuda))])
        det_d = df_aa_producto[(df_aa_producto["ACTIVO"]=="Deuda") & (df_aa_producto["PRODUCTO"].isin(sel_prod_deuda))].copy()
        if det_d.empty:
            st.info("Selecciona al menos un producto Deuda.")
        else:
            det_d = det_d.groupby("PRODUCTO")["Monto"].sum().reset_index().sort_values("Monto", ascending=False)
            fig_donut = donut_figure(det_d["PRODUCTO"], det_d["Monto"], "Deuda — Estrategias seleccionadas")
            st.plotly_chart(fig_donut, use_container_width=True, config={"displayModeBar": False})

            vista = det_d.copy()
            vista["%"] = (vista["Monto"]/vista["Monto"].sum()*100).round(2)
            vista["Monto"] = vista["Monto"].map(lambda x: f"${x:,.2f}")
            vista["%"] = vista["%"].map(lambda x: f"{x:.2f}%")
            vista = vista.rename(columns={"PRODUCTO":"Producto"})
            if print_mode:
                tiny_table_print(vista)
            else:
                st.dataframe(vista, hide_index=True, use_container_width=True)
    with c2:
        sel_prod_rv = st.multiselect("Estrategia — Renta Variable", options=prod_rv, default=prod_rv[:min(6, len(prod_rv))])
        det_r = df_aa_producto[(df_aa_producto["ACTIVO"]=="Renta Variable") & (df_aa_producto["PRODUCTO"].isin(sel_prod_rv))].copy()
        if det_r.empty:
            st.info("Selecciona al menos un producto RV.")
        else:
            det_r = det_r.groupby("PRODUCTO")["Monto"].sum().reset_index().sort_values("Monto", ascending=False)
            fig_donut = donut_figure(det_r["PRODUCTO"], det_r["Monto"], "Capitales — Estrategias seleccionadas")
            st.plotly_chart(fig_donut, use_container_width=True, config={"displayModeBar": False})

            vista = det_r.copy()
            vista["%"] = (vista["Monto"]/vista["Monto"].sum()*100).round(2)
            vista["Monto"] = vista["Monto"].map(lambda x: f"${x:,.2f}")
            vista["%"] = vista["%"].map(lambda x: f"{x:.2f}%")
            vista = vista.rename(columns={"PRODUCTO":"Producto"})
            if print_mode:
                tiny_table_print(vista)
            else:
                st.dataframe(vista, hide_index=True, use_container_width=True)

def render_allocation_historico():
    st.subheader("Comportamiento de activos y estrategias")
    aa_activo, aa_producto = aa_hist_ultimo_5_anios(ALIAS_CDM, F_DIA_FIN_NEXT, CONTRATOS_KEY)
    c1, c2 = st.columns((1,1))
    with c1:
        if aa_activo.empty:
            st.info("Sin histórico por tipo de activo.")
        else:
            p = aa_activo.copy()
            p["AX"] = p["ANIO"].astype(str)
            pivot_pp = p.pivot_table(index="AX", columns="ACTIVO", values="Pct", aggfunc="sum").fillna(0)
            tickvals = pivot_pp.index.tolist()
            st.plotly_chart(area100_from_pivot(pivot_pp, "Activos", tickvals=tickvals),
                            use_container_width=True, config={"displayModeBar": False})
    with c2:
        if aa_producto.empty:
            st.info("Sin histórico por producto.")
        else:
            topN = 10
            top_cols = (aa_producto.groupby("PRODUCTO")["Pct"].mean()
                        .sort_values(ascending=False).head(topN).index.tolist())
            p2 = aa_producto[aa_producto["PRODUCTO"].isin(top_cols)].copy()
            p2["AX"] = p2["ANIO"].astype(str)
            pivot_p2 = p2.pivot_table(index="AX", columns="PRODUCTO", values="Pct", aggfunc="sum").fillna(0)
            tickvals2 = pivot_p2.index.tolist()
            st.plotly_chart(area100_from_pivot(pivot_p2, "Productos", tickvals=tickvals2),
                            use_container_width=True, config={"displayModeBar": False})

def render_deuda_composicion(df_final):
    st.subheader("Composición de activos deuda")
    if df_final.empty:
        st.info("Sin instrumentos de Deuda en el corte actual.")
        return
    mask_det = df_final['Instrumento'].astype(str).str.upper() != 'TOTAL'
    df_det = df_final.loc[mask_det].copy()
    df_det['Tipo de instrumento'] = df_det['Tipo de instrumento'].replace(
        {None: 'Reporto Guber Excento', 'none': 'Reporto Guber Excento', 'None': 'Reporto Guber Excento'}
    )
    pct_num = pd.to_numeric(df_det['% Cartera'].str.replace('%','', regex=False), errors='coerce').fillna(0.0)
    serie_tp = pct_num.groupby(df_det['Tipo de Papel']).sum().sort_values(ascending=False)
    serie_ti = pct_num.groupby(df_det['Tipo de instrumento']).sum().sort_values(ascending=False)
    c1, c2 = st.columns((1,1))
    with c1:
        st.plotly_chart(
            donut_figure(
                serie_tp.index.tolist(),
                serie_tp.values.tolist(),
                "Por Tipo de Papel",
                kind="pct"
            ),
            use_container_width=True, config={"displayModeBar": False}
        )
    with c2:
        st.plotly_chart(
            donut_figure(
                serie_ti.index.tolist(),
                serie_ti.values.tolist(),
                "Por Tipo de Instrumento",
                kind="pct"
            ),
            use_container_width=True, config={"displayModeBar": False}
        )

def render_deuda_riesgo(df_final):
    st.subheader("Calificación")
    if df_final.empty:
        st.info("Sin instrumentos de Deuda en el corte actual.")
        return
    mask_det = df_final['Instrumento'].astype(str).str.upper() != 'TOTAL'
    df_det = df_final.loc[mask_det].copy()
    pct_num = pd.to_numeric(df_det['% Cartera'].str.replace('%','', regex=False), errors='coerce').fillna(0.0)
    vals = pd.to_numeric(df_det.get('_VALOR_RATING_MIN', np.nan), errors='coerce')
    is_rep = df_det['Tipo de Papel'].str.contains('reporto', case=False, na=False) | \
             df_det['Tipo de instrumento'].str.contains('reporto', case=False, na=False)
    vals.loc[is_rep] = 1.0
    escala = vals.map(lambda v: VAL_TO_BUCKET.get(int(v), "NR") if not pd.isna(v) else "NR")
    tabla = (pd.DataFrame({'Escala': escala, 'Pct': pct_num})
             .groupby('Escala', dropna=False)['Pct'].sum().reset_index()
             .sort_values('Pct', ascending=False))
    tabla["% Cartera"] = tabla["Pct"].map(lambda x: f"{x:.2f}%")
    tabla = tabla[["Escala","% Cartera"]].reset_index(drop=True)
    def color_row(row):
        e = str(row["Escala"])
        if e in ("AAA","AA+","AA","AA-","A+","A","A-"):
            c="#dcfce7"
        elif e in ("BBB+","BBB","BBB-"):
            c="#fef9c3"
        elif e in ("NR",):
            c="#e2e8f0"
        else:
            c="#fee2e2"
        return [f"background-color: {c}"]*len(row)
    styled = tabla.style.apply(color_row, axis=1)
    html = styled.to_html(index=False, border=0)
    st.markdown(f'<div class="table-print pb-after">{html}</div>', unsafe_allow_html=True)

    if hist_dur is not None and not hist_dur.empty:
        hd = hist_dur.copy()
        # ✅ Normaliza MES a cierre de mes y amarra el eje al corte (y,m)
        hd["MES"] = pd.to_datetime(hd["MES"], errors="coerce")
        hd = hd.dropna(subset=["MES"]).copy()
        hd["MES"] = (hd["MES"] + pd.offsets.MonthEnd(0)).dt.normalize()

        end_ref = F_DIA_FIN
        spine = _month_end_spine(end_ref, n=12)
        end_ref_n = (pd.to_datetime(end_ref) + pd.offsets.MonthEnd(0)).normalize()
        hd = hd[hd["MES"] <= end_ref_n].copy()
        hd = hd.sort_values("MES").drop_duplicates(subset=["MES"], keep="last")
        hd = hd.set_index("MES").reindex(spine).reset_index().rename(columns={"index": "MES"})

        text_vals = [f"{v:.0f}" if pd.notna(v) else "" for v in hd["DURACION_DIAS"]]

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=hd["MES"],
            y=hd["DURACION_DIAS"],
            mode="lines+markers+text",
            name="Duración (días)",
            text=text_vals,
            textposition="top center",
            cliponaxis=False,
            line=dict(width=2),
            marker=dict(size=8),
            hovertemplate="%{x|%Y-%m}: %{y:.0f} días<extra></extra>"
        ))

        fig.update_layout(
            title="Duración - últimos 12 meses",
            yaxis=dict(title="Días"),
            xaxis=dict(title="Mes"),
            legend=LEGEND_RIGHT,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=10, r=220, t=60, b=6),
            height=BARH_H
        )

        # ✅ FIX: eje X mensual sin meses fantasma (usa tu helper)
        _style_time_xaxis(fig, n_points=len(hd), print_mode=print_mode)

        # ✅ headroom arriba para que no corte texto (en días)
        try:
            ymax = pd.to_numeric(hd["DURACION_DIAS"], errors="coerce").max()
            if pd.notna(ymax):
                fig.update_yaxes(range=[0, float(ymax) * 1.10])
        except Exception:
            pass

        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    else:
        st.caption("No hay histórico de duración disponible.")

def render_deuda_historico_trimestral():
    st.subheader("Comportamiento del tipo de papel e instrumento")
    c1, c2 = st.columns(2)
    with c1:
        if hist_deuda_papel.empty:
            st.info("Sin histórico por Tipo de Papel.")
        else:
            p = hist_deuda_papel.copy()
            pvt = p.pivot_table(index="PERIODO", columns="TIPO_PAPEL", values="Pct", aggfunc="sum").fillna(0)
            idx = list(pvt.index)
            tickvals = idx[::2] if len(idx) > 2 else idx
            fig = area100_from_pivot(pvt, "Tipo de Papel", tickvals=tickvals)
            fig = add_datapoints_to_fig(fig, decimals=1)
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    with c2:
        if hist_deuda_instr.empty:
            st.info("Sin histórico por Tipo de Instrumento.")
        else:
            p2 = hist_deuda_instr.copy()
            pvt2 = p2.pivot_table(index="PERIODO", columns="TIPO_INSTRUMENTO", values="Pct", aggfunc="sum").fillna(0)
            idx2 = list(pvt2.index)
            tickvals2 = idx2[::2] if len(idx2) > 2 else idx2
            fig2 = area100_from_pivot(pvt2, "Tipo de Instrumento", tickvals=tickvals2)
            fig2 = add_datapoints_to_fig(fig2, decimals=1)
            st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})

def render_deuda_tabla(df_final):
    st.subheader("Portafolio")
    if df_final.empty:
        st.info("Sin instrumentos de Deuda en el corte actual.")
        return

    mask_det = df_final['Instrumento'].astype(str).str.upper() != 'TOTAL'
    df_det = df_final.loc[mask_det].copy()

    df_det['Tipo de instrumento'] = df_det['Tipo de instrumento'].replace(
        {None: 'Reporto Guber Excento', 'none': 'Reporto Guber Excento', 'None': 'Reporto Guber Excento'}
    )

    productos = df_det["Producto"].fillna("SIN_DESCRIPCION").astype(str).unique().tolist()
    productos = sorted(productos, key=lambda x: x.upper())

    cols_order = [
        'Producto','Instrumento','Tipo de Papel','Tipo de instrumento','Calificación',
        'Fecha vto','DxV','Duración (días)','Tasa valuacion','Carry (365 d)',
        'Valor Nominal','Monto','% Cartera','Tasa ref','Tasa base'
    ]

    for prod in productos:
        sub = df_det[df_det["Producto"].fillna("SIN_DESCRIPCION").astype(str) == prod].copy()
        if sub.empty:
            continue

        sub["__m__"] = money_to_float_series(sub["Monto"])
        sub = sub.sort_values("__m__", ascending=False).drop(columns="__m__")

        cols_to_drop = ["_VALOR_RATING_MIN", "_ID_PRODUCTO", "Producto"]
        display_sub = sub.drop(columns=cols_to_drop, errors="ignore")

        cols_final = [c for c in cols_order if c in display_sub.columns] + \
                     [c for c in display_sub.columns if c not in cols_order]

        with st.expander(f"Producto: {prod}  —  instrumentos: {len(display_sub)}", expanded=False):
            st.markdown('<div class="deuda-detail-table">', unsafe_allow_html=True)
            if print_mode:
                tiny_table_print(display_sub[cols_final])
            else:
                altura = min(900, 60 + 22 * len(display_sub))
                st.dataframe(
                    display_sub[cols_final],
                    hide_index=True,
                    use_container_width=True,
                    height=altura
                )
            st.markdown('</div>', unsafe_allow_html=True)
            st.markdown("<br><em>Carry calculado a 365 días</em>", unsafe_allow_html=True)

def render_deuda_por_producto_comp(df_final):
    st.subheader("Composición por estrategia de deuda")
    if df_final.empty:
        st.info("Sin instrumentos de Deuda en el corte actual.")
        return
    mask_det = df_final['Instrumento'].astype(str).str.upper() != 'TOTAL'
    df_det = df_final.loc[mask_det].copy()
    df_det['Tipo de instrumento'] = df_det['Tipo de instrumento'].replace(
        {None: 'Reporto Guber Excento', 'none': 'Reporto Guber Excento', 'None': 'Reporto Guber Excento'}
    )
    productos = sorted(df_det["Producto"].fillna("SIN_DESCRIPCION").astype(str).unique().tolist())
    sel = st.multiselect("Selecciona estrategia(s) Deuda", options=productos, default=productos[:1])
    if not sel:
        st.info("Selecciona al menos un producto.")
        return
    for prod in sel:
        sub = df_det[df_det["Producto"].fillna("SIN_DESCRIPCION").astype(str) == prod].copy()
        if sub.empty:
            continue
        sub["MontoNum"] = money_to_float_series(sub["Monto"])
        serie_tp = sub.groupby("Tipo de Papel")["MontoNum"].sum().sort_values(ascending=False)
        serie_ti = sub.groupby("Tipo de instrumento")["MontoNum"].sum().sort_values(ascending=False)
        st.markdown(f"**Estrategia: {prod}**")
        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(
                donut_figure(serie_tp.index.tolist(), serie_tp.values.tolist(),
                             f"{prod} — Tipo de Papel", kind="money"),
                use_container_width=True, config={"displayModeBar": False}
            )
        with c2:
            st.plotly_chart(
                donut_figure(serie_ti.index.tolist(), serie_ti.values.tolist(),
                             f"{prod} — Tipo de Instrumento", kind="money"),
                use_container_width=True, config={"displayModeBar": False}
            )

def render_deuda_rendimientos_por_producto():
    st.subheader("Rendimientos por estrategia de deuda")
    if df_hist_rend_prod is None or df_hist_rend_prod.empty:
        st.info("Sin rendimientos por producto disponibles.")
        return

    prod_act = df_aa_producto[["PRODUCTO","ACTIVO"]].drop_duplicates()
    df = df_hist_rend_prod.merge(prod_act, on="PRODUCTO", how="left")
    df = df[df["ACTIVO"] == "Deuda"]
    if df.empty:
        st.info("No hay productos de deuda con rendimientos.")
        return

    productos = sorted(df["PRODUCTO"].unique().tolist())
    prod_sel = st.selectbox("Estrategia Deuda", options=productos, index=0)    # Modo fijo (Deuda): Anualizado
    modo = "Anualizado"

    # ✅ contrato foco para buscar benchmarks
    nombre_corto_focus = str(st.session_state.get("NOMBRE_CORTO_FOCUS", "")).strip()

    bench_pack = None
    if nombre_corto_focus:
        try:
            # producto != portafolio total => benchmarks de producto
            bench_pack = build_bench_pack_from_map(
                bench_map_df=bench_map_df,
                alias_cdm=ALIAS_CDM,
                nombre_corto=nombre_corto_focus,
                producto=prod_sel,          # ✅ benchmarks ligados al producto
                bench_files=BENCH_FILES,
            )
            if bench_pack is not None and bench_pack.empty:
                bench_pack = None
        except Exception as e:
            st.caption(f"Benchmarks (producto): no se pudo construir benchmark. ({e})")
            bench_pack = None

    plot_rend_producto_series(df, df_hist_rend_prod_5y, prod_sel, modo, bench_pack=bench_pack)
    try:
        ficha_df = get_bench_ficha_rows(ALIAS_CDM, NOMBRE_CORTO_FOCUS, prod_sel, modo)
        render_benchmark_ficha(ficha_df, modo=modo)
    except Exception:
        pass
    
def render_rv_resumen():
    st.subheader("Distribución")
    if rv_enriq_base.empty:
        st.info("No hay RV en el corte actual.")
        return
    c1, c2 = st.columns((1,1))
    with c1:
        sec = rv_enriq_base.groupby("sector")["MONTO"].sum().reset_index().sort_values("MONTO", ascending=False)
        fig_sec = donut_figure(sec["sector"], sec["MONTO"], "Distribución por Sector")
        st.plotly_chart(fig_sec, use_container_width=True, config={"displayModeBar": False})
        sec_tab = sec.copy()
        sec_tab["%"] = (sec_tab["MONTO"]/sec_tab["MONTO"].sum()*100).round(2)
        sec_tab["MONTO"] = sec_tab["MONTO"].map(lambda x: f"${x:,.2f}")
        sec_tab["%"] = sec_tab["%"].map(lambda x: f"{x:.2f}%")
        sec_tab = sec_tab.rename(columns={"sector":"Sector","MONTO":"Monto"})
        st.markdown("**Detalle Sector**")
        if print_mode:
            tiny_table_print(sec_tab)
        else:
            st.dataframe(sec_tab, hide_index=True, use_container_width=True)
    with c2:
        ind = rv_enriq_base.groupby("industry")["MONTO"].sum().reset_index().sort_values("MONTO", ascending=False)
        fig_industry = donut_figure(ind["industry"], ind["MONTO"], "Distribución por Industria")
        st.plotly_chart(fig_industry, use_container_width=True, config={"displayModeBar": False})
        ind_tab = ind.copy()
        ind_tab["%"] = (ind_tab["MONTO"]/ind_tab["MONTO"].sum()*100).round(2)
        ind_tab["MONTO"] = ind_tab["MONTO"].map(lambda x: f"${x:,.2f}")
        ind_tab["%"] = ind_tab["%"].map(lambda x: f"{x:.2f}%")
        ind_tab = ind_tab.rename(columns={"industry":"Industria","MONTO":"Monto"})
        st.markdown("**Detalle Industria**")
        if print_mode:
            tiny_table_print(ind_tab)
        else:
            st.dataframe(ind_tab, hide_index=True, use_container_width=True)
    
    st.markdown("<br><em>Carry calculado a 365 días</em>", unsafe_allow_html=True)

def render_rv_por_producto():
    st.subheader("Participación de industria y sector por estrategia")
    if rv_enriq_base.empty:
        st.info("No hay RV en el corte actual.")
        return
    productos = sorted(rv_enriq_base["Producto"].fillna("SIN_DESCRIPCION").astype(str).unique().tolist())
    sel = st.multiselect("Selecciona estrategia(s) RV", options=productos, default=productos[:1])
    if not sel:
        st.info("Selecciona al menos un producto.")
        return
    for prod in sel:
        sub = rv_enriq_base[rv_enriq_base["Producto"].fillna("SIN_DESCRIPCION").astype(str) == prod]
        if sub.empty:
            continue
        c1, c2 = st.columns(2)
        with c1:
            sub_s = sub.groupby("sector")["MONTO"].sum().reset_index().sort_values("MONTO", ascending=False)
            st.plotly_chart(
                donut_figure(sub_s["sector"], sub_s["MONTO"], f"Estrategia {prod} — Sector"),
                use_container_width=True, config={"displayModeBar": False}
            )
        with c2:
            sub_i = sub.groupby("industry")["MONTO"].sum().reset_index().sort_values("MONTO", ascending=False)
            st.plotly_chart(
                donut_figure(sub_i["industry"], sub_i["MONTO"], f"Estrategia {prod} — Industria"),
                use_container_width=True, config={"displayModeBar": False}
            )
        view = (sub.groupby(["NOMBRE_EMISORA","Nombre Completo","industry","sector"])["MONTO"].sum()
                  .reset_index().sort_values("MONTO", ascending=False))
        view["MONTO"] = view["MONTO"].map(lambda x: f"${x:,.2f}")
        view = view.rename(columns={
            "NOMBRE_EMISORA":"Emisora",
            "Nombre Completo":"Nombre completo",
            "industry":"Industria",
            "sector":"Sector",
            "MONTO":"Monto"
        })
        if print_mode:
            tiny_table_print(view)
        else:
            st.dataframe(view, hide_index=True, use_container_width=True)

def render_rv_evolucion():
    st.subheader("Comportamiento en el tiempo de principales sectores e industrias")
    filtro_contratos, extra_params = build_contrato_filter_sql(CONTRATOS_KEY, "c.ID_CLIENTE", "cid_rv_evo")

    rv12 = run_sql(f"""
        WITH H AS (
          SELECT
            TRUNC(h.REGISTRO_CONTROL,'MM') AS MES,
            e.NOMBRE_EMISORA,
            CASE 
              WHEN h.ID_PRODUCTO IN ({REPORTO_RV_CSV}) THEN 2
              ELSE e.ID_TIPO_ACTIVO
            END AS ID_ACTIVO_LOGICO,
            SUM(h.VALOR_REAL) AS MONTO
          FROM SIAPII.V_HIS_POSICION_CLIENTE h
          JOIN SIAPII.V_M_CONTRATO_CDM c
            ON c.ID_CLIENTE = h.ID_CLIENTE
          JOIN SIAPII.V_M_EMISORA e ON e.ID_EMISORA = h.ID_EMISORA
          WHERE c.ALIAS_CDM = :alias
            {filtro_contratos}
            AND h.REGISTRO_CONTROL >= ADD_MONTHS(TRUNC(SYSDATE,'MM'), -12)
          GROUP BY TRUNC(h.REGISTRO_CONTROL,'MM'),
                   e.NOMBRE_EMISORA,
                   CASE 
                     WHEN h.ID_PRODUCTO IN ({REPORTO_RV_CSV}) THEN 2
                     ELSE e.ID_TIPO_ACTIVO
                   END
        ),
        RV_MES AS (
          SELECT MES, SUM(MONTO) AS TOT_RV
          FROM H
          WHERE ID_ACTIVO_LOGICO = 2
          GROUP BY MES
        )
        SELECT H.MES, H.NOMBRE_EMISORA, H.ID_ACTIVO_LOGICO, H.MONTO, R.TOT_RV
        FROM H JOIN RV_MES R ON R.MES = H.MES
        WHERE H.ID_ACTIVO_LOGICO = 2
    """, {"alias": ALIAS_CDM, **extra_params})
    if rv12.empty:
        st.info("Sin datos para evolución 12 meses de RV.")
        return
    core = core_issuer_map()
    rv_m = rv12.merge(core, left_on="NOMBRE_EMISORA", right_on="issuer_name", how="left")
    rv_m["sector"] = rv_m["sector"].fillna("SIN SECTOR")
    rv_m["industry"] = rv_m["industry"].fillna("SIN INDUSTRIA")
    rv_m["PctPort"] = (rv_m["MONTO"] / rv_m["TOT_RV"] * 100.0).round(4)
    sec_rank = rv_m.groupby("sector")["PctPort"].sum().sort_values(ascending=False).head(3).index.tolist()
    rv_sec = rv_m[rv_m["sector"].isin(sec_rank)].copy()
    piv_sec = rv_sec.pivot_table(index="MES", columns="sector", values="PctPort", aggfunc="sum").fillna(0)
    piv_sec = piv_sec[piv_sec.mean(axis=0).sort_values(ascending=False).index]
    ind_rank = rv_m.groupby("industry")["PctPort"].sum().sort_values(ascending=False).head(3).index.tolist()
    rv_ind = rv_m[rv_m["industry"].isin(ind_rank)].copy()
    piv_ind = rv_ind.pivot_table(index="MES", columns="industry", values="PctPort", aggfunc="sum").fillna(0)
    piv_ind = piv_ind[piv_ind.mean(axis=0).sort_values(ascending=False).index]
    end_ref = F_DIA_FIN
    spine = _month_end_spine(end_ref, n=12)

    piv_sec.index = pd.to_datetime(piv_sec.index, errors="coerce")
    piv_ind.index = pd.to_datetime(piv_ind.index, errors="coerce")
    piv_sec = piv_sec.dropna(axis=0, how="any")
    piv_ind = piv_ind.dropna(axis=0, how="any")

    piv_sec.index = (piv_sec.index + pd.offsets.MonthEnd(0)).normalize()
    piv_ind.index = (piv_ind.index + pd.offsets.MonthEnd(0)).normalize()

    end_ref_n = (pd.to_datetime(end_ref) + pd.offsets.MonthEnd(0)).normalize()
    piv_sec = piv_sec[piv_sec.index <= end_ref_n].reindex(spine).fillna(0)
    piv_ind = piv_ind[piv_ind.index <= end_ref_n].reindex(spine).fillna(0)

    fig_sec = go.Figure()
    for col in piv_sec.columns:
        fig_sec.add_trace(go.Scatter(
            x=piv_sec.index, y=piv_sec[col], mode="lines", name=str(col),
            hovertemplate="%{x|%Y-%m}: %{y:.2f}%<extra></extra>"
        ))
    fig_sec.update_layout(
        title="3 Sectores",
        yaxis=dict(title="% de RV", ticksuffix="%"),
        xaxis=dict(title="Mes", tickangle=TICKANGLE),
        legend=LEGEND_RIGHT,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=220, t=42, b=6), height=BARH_H
    )
    fig_ind = go.Figure()
    for col in piv_ind.columns:
        fig_ind.add_trace(go.Scatter(
            x=piv_ind.index, y=piv_ind[col], mode="lines", name=str(col),
            hovertemplate="%{x|%Y-%m}: %{y:.2f}%<extra></extra>"
        ))
    fig_ind.update_layout(
        title="3 Industrias",
        yaxis=dict(title="% de RV", ticksuffix="%"),
        xaxis=dict(title="Mes", tickangle=TICKANGLE),
        legend=LEGEND_RIGHT,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=220, t=42, b=6), height=BARH_H
    )
    c1, c2 = st.columns(2)
    with c1:
#         fig = add_datapoints_to_fig(fig, decimals=1)
        fig_sec = add_datapoints_to_fig(fig_sec, decimals=1)
        st.plotly_chart(fig_sec, use_container_width=True, config={"displayModeBar": False})
    with c2:
#         fig = add_datapoints_to_fig(fig, decimals=1)
        fig_ind = add_datapoints_to_fig(fig_ind, decimals=1)
        st.plotly_chart(fig_ind, use_container_width=True, config={"displayModeBar": False})

def render_rv_rendimientos_por_producto():
    st.subheader("Rendimientos por estrategia de renta variable")
    if df_hist_rend_prod is None or df_hist_rend_prod.empty:
        st.info("Sin rendimientos por producto disponibles.")
        return

    prod_act = df_aa_producto[["PRODUCTO","ACTIVO"]].drop_duplicates()
    df = df_hist_rend_prod.merge(prod_act, on="PRODUCTO", how="left")
    df = df[df["ACTIVO"] == "Renta Variable"]
    if df.empty:
        st.info("No hay productos de renta variable con rendimientos.")
        return

    productos = sorted(df["PRODUCTO"].unique().tolist())
    prod_sel = st.selectbox("Estrategia RV", options=productos, index=0)    # Modo fijo (Renta Variable): Efectivo
    modo = "Efectivo"

    nombre_corto_focus = str(st.session_state.get("NOMBRE_CORTO_FOCUS", "")).strip()

    bench_pack = None
    if nombre_corto_focus:
        try:
            bench_pack = build_bench_pack_from_map(
                bench_map_df=bench_map_df,
                alias_cdm=ALIAS_CDM,
                nombre_corto=nombre_corto_focus,
                producto=prod_sel,          # ✅ benchmarks ligados al producto
                bench_files=BENCH_FILES,
            )
            if bench_pack is not None and bench_pack.empty:
                bench_pack = None
        except Exception as e:
            st.caption(f"Benchmarks (producto): no se pudo construir benchmark. ({e})")
            bench_pack = None

    plot_rend_producto_series(df, df_hist_rend_prod_5y, prod_sel, modo, bench_pack=bench_pack)
    try:
        ficha_df = get_bench_ficha_rows(ALIAS_CDM, NOMBRE_CORTO_FOCUS, prod_sel, modo)
        render_benchmark_ficha(ficha_df, modo=modo)
    except Exception:
        pass

# =========================
#  TABS
# =========================
if not print_mode:
    tabs = st.tabs(["Resumen", "Asset Allocation", "Deuda", "Renta Variable"])

    with tabs[0]:
        st.container().markdown('<div class="tabs-normal"></div>', unsafe_allow_html=True)
        render_resumen()

    with tabs[1]:
        st.container().markdown('<div class="tabs-normal"></div>', unsafe_allow_html=True)
        sub = st.tabs(["Nivel Contrato", "Nivel producto", "Histórico"])
        with sub[0]:
            render_allocation_general()
        with sub[1]:
            render_allocation_detalle()
        with sub[2]:
            render_allocation_historico()

    with tabs[2]:
        st.container().markdown('<div class="tabs-normal"></div>', unsafe_allow_html=True)
        if df_final_deuda.empty:
            resumen_vals = { "Instrumentos":"0", "Valor mercado":"$0.00", "Duración (días)":"", "DxV (pond.)":"", "Rto. esperado 1 año":"" }
        else:
            mask_det = df_final_deuda['Instrumento'].astype(str).str.upper() != 'TOTAL'
            valor_mercado = money_to_float_series(df_final_deuda.loc[mask_det, 'Monto']).sum() if len(df_final_deuda) else 0.0
            total_row = df_final_deuda.iloc[-1] if len(df_final_deuda) else None
            resumen_vals = {
                "Instrumentos": f"{int(mask_det.sum()):,}",
                "Valor mercado": f"${valor_mercado:,.2f}",
                "Duración (días)": "" if total_row is None else str(total_row['Duración (días)']),
                "DxV (pond.)": "" if total_row is None else str(total_row['DxV']),
                "Rto. esperado 1 año": "" if total_row is None else str(total_row['Carry (365 d)']),
            }
        st.markdown('<div class="kpi-grid">' + "".join(
            f'<div class="kpi-card"><div class="kpi-label">{k}</div><div class="kpi-value">{v}</div></div>'
            for k,v in resumen_vals.items()
        ) + '</div>', unsafe_allow_html=True)

        sub = st.tabs(["Composición", "Riesgo", "Histórico", "Detalle", "Composicion por producto", "Rendimientos"])
        with sub[0]:
            render_deuda_composicion(df_final_deuda)
        with sub[1]:
            render_deuda_riesgo(df_final_deuda)
        with sub[2]:
            render_deuda_historico_trimestral()
        with sub[3]:
            render_deuda_tabla(df_final_deuda)
        with sub[4]:
            render_deuda_por_producto_comp(df_final_deuda)
        with sub[5]:
            render_deuda_rendimientos_por_producto()

    with tabs[3]:
        st.container().markdown('<div class="tabs-normal"></div>', unsafe_allow_html=True)
        sub = st.tabs(["Nivel Activo", "Nivel Producto", "Histórico", "Rendimientos"])
        with sub[0]:
            render_rv_resumen()
        with sub[1]:
            render_rv_por_producto()
        with sub[2]:
            render_rv_evolucion()
        with sub[3]:
            render_rv_rendimientos_por_producto()

else:
    st.markdown('<div class="print-container">', unsafe_allow_html=True)

    st.header("Resumen")
    render_resumen()

    st.markdown('<div class="print-section">', unsafe_allow_html=True)
    st.header("Asset Allocation")
    render_allocation_general()
    render_allocation_detalle()
    render_allocation_historico()
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="print-section">', unsafe_allow_html=True)
    st.header("Deuda")
    render_deuda_composicion(df_final_deuda)
    render_deuda_riesgo(df_final_deuda)
    render_deuda_historico_trimestral()
    render_deuda_tabla(df_final_deuda)
    render_deuda_por_producto_comp(df_final_deuda)
    render_deuda_rendimientos_por_producto()
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="print-section">', unsafe_allow_html=True)
    st.header("Renta Variable")
    render_rv_resumen()
    render_rv_por_producto()
    render_rv_evolucion()
    render_rv_rendimientos_por_producto()
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

st.markdown("<hr/><div style='text-align:center;opacity:.85'><small>Datos al cierre del mes seleccionado</small></div>", unsafe_allow_html=True)
