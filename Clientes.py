import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
from io import BytesIO
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# --- CONFIGURACION DE GOOGLE SHEETS ---
scope = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

@st.cache_resource
def conectar_google_sheets():
    creds_dict = dict(st.secrets["gcp_service_account"])
    if "\n" in creds_dict["private_key"]:
        creds_dict["private_key"] = creds_dict["private_key"].replace("\n", "")
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)
    return client.open('Clientes y Proveedores')

spreadsheet = conectar_google_sheets()

@st.cache_data(ttl=300)
def load_data(nombre_pestana):
    try:
        worksheet = spreadsheet.worksheet(nombre_pestana)
        data = worksheet.get_all_values()
        if not data:
            return pd.DataFrame()
        
        headers = [str(h).strip() if str(h).strip() != "" else f"COL_{i}" for i, h in enumerate(data[0])]
        
        seen = {}
        unique_headers = []
        for h in headers:
            if h in seen:
                seen[h] += 1
                unique_headers.append(f"{h}_{seen[h]}")
            else:
                seen[h] = 0
                unique_headers.append(h)
                
        return pd.DataFrame(data[1:], columns=unique_headers)
    except Exception:
        if nombre_pestana == "Abono a tarjeta de crédito":
            try:
                ws = spreadsheet.add_worksheet(title=nombre_pestana, rows=100, cols=10)
                headers_iniciales = ["Mes", "Abono TC", "Descripcion", "Tarjeta Debito", "Saldo TC", "FECHA"]
                try:
                    ws.update(range_name="A1", values=[headers_iniciales])
                except Exception:
                    ws.update("A1", [headers_iniciales])
                return pd.DataFrame(columns=headers_iniciales)
            except Exception:
                pass
        return pd.DataFrame()

meses_nombres = {
    1: "--- E N E R O ---",
    2: "--- F E B R E R O ---",
    3: "--- M A R Z O ---",
    4: "--- A B R I L ---",
    5: "--- M A Y O ---",
    6: "--- J U N I O ---",
    7: "--- J U L I O ---",
    8: "--- A G O S T O ---",
    9: "--- S E P T I E M B R E ---",
    10: "--- O C T U B R E ---",
    11: "--- N O V I E M B R E ---",
    12: "--- D I C I E M B R E ---"
}

def parsear_fecha(fecha_str):
    fecha_str = str(fecha_str).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(fecha_str.split(" ")[0], fmt)
        except ValueError:
            continue
    return None

def limpiar_numero(val):
    if val is None:
        return 0.0
    val_str = str(val).strip().replace('$', '')
    if not val_str:
        return 0.0
    try:
        if ',' in val_str and '.' in val_str:
            if val_str.find('.') < val_str.find(','):
                val_str = val_str.replace('.', '').replace(',', '.')
            else:
                val_str = val_str.replace(',', '')
        elif ',' in val_str:
            val_str = val_str.replace(',', '.')
        return float(val_str)
    except ValueError:
        return 0.0

def calcular_total_tarjeta_debito_pagada():
    df_c = load_data("Clientes")
    if df_c.empty:
        return 0.0
    total_pagado = 0.0
    for _, row in df_c.iterrows():
        estatus = str(row.get("ESTATUS", "")).strip().upper()
        fact = str(row.get("FACTURA", "")).strip()
        if fact and not fact.startswith("---") and not fact.startswith("TOTALES") and not fact.startswith("El mes"):
            if estatus == "PAGADA":
                total_pagado += limpiar_numero(row.get("TOTAL", 0))
    return total_pagado

def reorganizar_con_meses_en_sheet(df_actual, tipo_seccion):
    registros = []
    for _, row in df_actual.iterrows():
        identificador = str(row.get("FACTURA", row.get("Abono TC", row.get("ABONO TC", "")))).strip()
        desc_check = str(row.get("Descripcion", row.get("DESCRIPCION", ""))).strip()
        
        es_valido = False
        if tipo_seccion == "Abono a tarjeta de crédito":
            es_valido = bool(desc_check and not desc_check.startswith("---") and not desc_check.startswith("TOTALES") and not desc_check.startswith("El mes") and desc_check.upper() != "PRUEBA")
        else:
            es_valido = bool(identificador and not identificador.startswith("---") and not identificador.startswith("TOTALES") and not identificador.startswith("El mes"))

        if es_valido:
            r_dict = row.to_dict()
            if tipo_seccion == "Abono a tarjeta de crédito":
                for col_num in ["Abono TC", "ABONO TC", "Tarjeta Debito", "Saldo TC"]:
                    if col_num in r_dict and str(r_dict[col_num]).strip() != "":
                        r_dict[col_num] = f"{limpiar_numero(r_dict[col_num]):.2f}"
            else:
                for col_num in ["SUBTOTAL", "IVA", "ISR", "TOTAL"]:
                    if col_num in r_dict and str(r_dict[col_num]).strip() != "":
                        r_dict[col_num] = f"{limpiar_numero(r_dict[col_num]):.2f}"
            registros.append(r_dict)
            
    def clave_orden(r):
        dt = parsear_fecha(r.get("FECHA", ""))
        return dt if dt else datetime.min

    registros.sort(key=clave_orden)

    nueva_data = []
    mes_actual = None
    registros_mes_actual = []
    
    t_debito_actual = calcular_total_tarjeta_debito_pagada()
    saldo_tc_acumulado = t_debito_actual

    def agregar_totales_mes(regs_mes):
        fila_tot = {col: "" for col in df_actual.columns}
        if tipo_seccion == "Abono a tarjeta de crédito":
            if "Mes" in df_actual.columns:
                fila_tot["Mes"] = "TOTALES DEL MES"
            elif "Abono TC" in df_actual.columns:
                fila_tot["Abono TC"] = "TOTALES DEL MES"
            
            t_abono = sum(limpiar_numero(r.get("Abono TC", r.get("ABONO TC", 0))) for r in regs_mes)
            col_abono = "Abono TC" if "Abono TC" in df_actual.columns else "ABONO TC"
            if col_abono in df_actual.columns: 
                fila_tot[col_abono] = f"{t_abono:.2f}"
            if "Saldo TC" in df_actual.columns:
                ultimo_s = regs_mes[-1].get("Saldo TC", "0.00") if regs_mes else f"{t_debito_actual:.2f}"
                fila_tot["Saldo TC"] = ultimo_s
        else:
            if "FACTURA" in df_actual.columns:
                fila_tot["FACTURA"] = "TOTALES DEL MES"
                
            if tipo_seccion == "Clientes":
                t_sub = sum(limpiar_numero(r.get("SUBTOTAL", 0)) for r in regs_mes)
                t_iva = sum(limpiar_numero(r.get("IVA", 0)) for r in regs_mes)
                t_isr = sum(limpiar_numero(r.get("ISR", 0)) for r in regs_mes)
                t_tot = sum(limpiar_numero(r.get("TOTAL", 0)) for r in regs_mes)
                if "SUBTOTAL" in df_actual.columns: fila_tot["SUBTOTAL"] = f"{t_sub:.2f}"
                if "IVA" in df_actual.columns: fila_tot["IVA"] = f"{t_iva:.2f}"
                if "ISR" in df_actual.columns: fila_tot["ISR"] = f"{t_isr:.2f}"
                if "TOTAL" in df_actual.columns: fila_tot["TOTAL"] = f"{t_tot:.2f}"
            else:
                t_sub = sum(limpiar_numero(r.get("SUBTOTAL", 0)) for r in regs_mes)
                t_iva = sum(limpiar_numero(r.get("IVA", 0)) for r in regs_mes)
                t_tot = sum(limpiar_numero(r.get("TOTAL", 0)) for r in regs_mes)
                if "SUBTOTAL" in df_actual.columns: fila_tot["SUBTOTAL"] = f"{t_sub:.2f}"
                if "IVA" in df_actual.columns: fila_tot["IVA"] = f"{t_iva:.2f}"
                if "TOTAL" in df_actual.columns: fila_tot["TOTAL"] = f"{t_tot:.2f}"
        return fila_tot

    if not registros and tipo_seccion == "Abono a tarjeta de crédito":
        return []

    for reg in registros:
        dt = parsear_fecha(reg.get("FECHA", ""))
        if dt:
            if dt.month != mes_actual:
                if mes_actual is not None and registros_mes_actual:
                    fila_fin = {col: "" for col in df_actual.columns}
                    fila_fin[df_actual.columns[0]] = f"El mes termino con = {saldo_tc_acumulado:.2f}"
                    nueva_data.append(fila_fin)
                    nueva_data.append(agregar_totales_mes(registros_mes_actual))
                    registros_mes_actual = []
                
                mes_actual = dt.month
                nombre_div = meses_nombres.get(mes_actual, "--- MES ---")
                fila_div = {col: "" for col in df_actual.columns}
                fila_div[df_actual.columns[0]] = nombre_div
                
                if tipo_seccion == "Abono a tarjeta de crédito":
                    if len(df_actual.columns) > 1:
                        fila_div[df_actual.columns[1]] = f"El mes se inicio con: {t_debito_actual:.2f}"
                
                nueva_data.append(fila_div)
        
        if tipo_seccion == "Abono a tarjeta de crédito":
            abono_val = limpiar_numero(reg.get("Abono TC", reg.get("ABONO TC", 0)))
            saldo_tc_acumulado = saldo_tc_acumulado - abono_val
            if saldo_tc_acumulado < 0:
                saldo_tc_acumulado = 0.0
                
            reg["Tarjeta Debito"] = f"{t_debito_actual:.2f}"
            reg["Saldo TC"] = f"{saldo_tc_acumulado:.2f}"

        registros_mes_actual.append(reg)
        nueva_data.append(reg)
        
    if mes_actual is not None and registros_mes_actual:
        fila_fin = {col: "" for col in df_actual.columns}
        fila_fin[df_actual.columns[0]] = f"El mes termino con = {saldo_tc_acumulado:.2f}"
        nueva_data.append(fila_fin)
        nueva_data.append(agregar_totales_mes(registros_mes_actual))

    return nueva_data

def recalcular_y_sincronizar_tarjeta_tc():
    try:
        ws_tc = spreadsheet.worksheet("Abono a tarjeta de crédito")
        df_tc = load_data("Abono a tarjeta de crédito")
        registros_tc = []
        if not df_tc.empty:
            for _, r in df_tc.iterrows():
                desc_check = str(r.get("Descripcion", r.get("DESCRIPCION", ""))).strip()
                if desc_check and not desc_check.startswith("---") and not desc_check.startswith("TOTALES") and not desc_check.startswith("El mes") and desc_check.upper() != "PRUEBA":
                    registros_tc.append(r.to_dict())
        
        temp_df_tc = pd.DataFrame(registros_tc)
        reorganized_tc = reorganizar_con_meses_en_sheet(temp_df_tc, "Abono a tarjeta de crédito")
        headers_tc = ["Mes", "Abono TC", "Descripcion", "Tarjeta Debito", "Saldo TC", "FECHA"]
        sheet_data_tc = [headers_tc]
        for r in reorganized_tc:
            fila_limpia = [str(r.get(h, "")) if r.get(h, "") is not None else "" for h in headers_tc]
            sheet_data_tc.append(fila_limpia)
        ws_tc.clear()
        try:
            ws_tc.update(range_name="A1", values=sheet_data_tc)
        except Exception:
            ws_tc.update("A1", sheet_data_tc)
    except Exception:
        pass

def calcular_tabla_utilidad():
    df_c = load_data("Clientes")
    df_p = load_data("Proveedores")
    df_g = load_data("Gastos")
    
    def extraer_subtotales_por_mes(df):
        subtotales_mes = {}
        if df.empty:
            return subtotales_mes
        mes_activo = None
        sub_acumulado = 0.0
        for _, row in df.iterrows():
            fila_str = " ".join([str(val) for val in row.values])
            mes_encontrado = None
            for m_num, m_str in meses_nombres.items():
                if m_str in fila_str:
                    mes_encontrado = m_num
                    break
            if mes_encontrado is not None:
                if mes_activo is not None:
                    subtotales_mes[mes_activo] = sub_acumulado
                mes_activo = mes_encontrado
                sub_acumulado = 0.0
                continue
            fact = str(row.get("FACTURA", "")).strip()
            if fact and not fact.startswith("---") and not fact.startswith("TOTALES"):
                sub_acumulado += limpiar_numero(row.get("SUBTOTAL", 0))
        if mes_activo is not None:
            subtotales_mes[mes_activo] = sub_acumulado
        return subtotales_mes

    sub_clientes = extraer_subtotales_por_mes(df_c)
    sub_proveedores = extraer_subtotales_por_mes(df_p)
    sub_gastos = extraer_subtotales_por_mes(df_g)
    
    meses_unidos = sorted(list(set(list(sub_clientes.keys()) + list(sub_proveedores.keys()) + list(sub_gastos.keys()))))
    
    filas_utilidad = []
    for m in meses_unidos:
        filas_utilidad.append({
            "Mes": meses_nombres.get(m, "--- MES ---"),
            "Subtotal de Clientes Del mes": "",
            "Subtotal de Proveedores Del mes": "",
            "Subtotal de Gastos Del mes": "",
            "Total": ""
        })
        s_cli = sub_clientes.get(m, 0.0)
        s_prov = sub_proveedores.get(m, 0.0)
        s_gas = sub_gastos.get(m, 0.0)
        utilidad_total = s_cli - s_prov - s_gas
        
        filas_utilidad.append({
            "Mes": "",
            "Subtotal de Clientes Del mes": f"{s_cli:.2f}",
            "Subtotal de Proveedores Del mes": f"{s_prov:.2f}",
            "Subtotal de Gastos Del mes": f"{s_gas:.2f}",
            "Total": f"{utilidad_total:.2f}"
        })
    return pd.DataFrame(filas_utilidad)

def generar_pdf(df, titulo_reporte):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(letter), rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    story = []
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        name='TitleStyle', parent=styles['Heading1'], fontSize=16, leading=20, alignment=1, textColor=colors.HexColor('#1f2937')
    )
    cell_style = ParagraphStyle(
        name='CellStyle', parent=styles['Normal'], fontSize=8, leading=10, textColor=colors.HexColor('#374151')
    )
    header_style = ParagraphStyle(
        name='HeaderStyle', parent=styles['Normal'], fontSize=9, leading=11, fontName='Helvetica-Bold', textColor=colors.whitesmoke, alignment=1
    )

    story.append(Paragraph(f"Reporte de {titulo_reporte}", title_style))
    story.append(Spacer(1, 15))
    
    if df.empty:
        story.append(Paragraph("No hay registros disponibles.", cell_style))
    else:
        headers = list(df.columns)
        table_data = [[Paragraph(str(h), header_style) for h in headers]]
        
        for _, row in df.iterrows():
            row_cells = []
            for h in headers:
                val = str(row.get(h, ""))
                row_cells.append(Paragraph(val, cell_style))
            table_data.append(row_cells)
            
        page_width = landscape(letter)[0] - 60
        col_width = page_width / len(headers)
        col_widths = [col_width] * len(headers)
        
        t = Table(table_data, colWidths=col_widths, repeatRows=1)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f2937')),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9fafb')])
        ]))
        story.append(t)
        
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

st.set_page_config(layout="wide")

if "seccion_activa" not in st.session_state:
    st.session_state.seccion_activa = "Clientes"

recalcular_y_sincronizar_tarjeta_tc()

col_titulo, col_metrica = st.columns([2, 1])

with col_titulo:
    st.title("Control de Clientes, Proveedores y Gastos")

with col_metrica:
    df_temp_tc = load_data("Abono a tarjeta de crédito")
    ultimo_saldo_tc = 0.0
    
    if not df_temp_tc.empty:
        for _, r in df_temp_tc.iterrows():
            s_val = str(r.get("Saldo TC", "")).strip()
            desc_chk = str(r.get("Descripcion", r.get("DESCRIPCION", ""))).strip()
            if s_val and not s_val.startswith("---") and not s_val.startswith("TOTALES") and not s_val.startswith("El mes") and desc_chk.upper() != "PRUEBA":
                ultimo_saldo_tc = limpiar_numero(s_val)
    
    if ultimo_saldo_tc == 0.0:
        ultimo_saldo_tc = calcular_total_tarjeta_debito_pagada()

    st.metric(label="💳 Saldo Actual Tarjeta de Crédito", value=f"${ultimo_saldo_tc:.2f}")
    
    if st.button("🔄 Refrescar Saldo"):
        load_data.clear()
        recalcular_y_sincronizar_tarjeta_tc()
        st.session_state.seccion_activa = "Clientes"
        st.rerun()

opciones_menu = ["Clientes", "Proveedores", "Gastos", "Utilidad", "Abono a tarjeta de crédito"]
indice_actual = opciones_menu.index(st.session_state.seccion_activa) if st.session_state.seccion_activa in opciones_menu else 0

pestana_seleccionada = st.sidebar.radio(
    "Selecciona la sección a gestionar:",
    options=opciones_menu,
    index=indice_actual
)

if st.session_state.seccion_activa != pestana_seleccionada:
    st.session_state.seccion_activa = pestana_seleccionada
    st.session_state.select_edit = "-- Selecciona un registro --"
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.subheader("Agregar Nuevo Registro")

if "val_factura" not in st.session_state:
    st.session_state.val_factura = ""
if "val_rfc" not in st.session_state:
    st.session_state.val_rfc = ""
if "val_cliente" not in st.session_state:
    st.session_state.val_cliente = ""
if "val_desc" not in st.session_state:
    st.session_state.val_desc = ""
if "val_fecha" not in st.session_state:
    st.session_state.val_fecha = datetime.today().strftime('%Y-%m-%d')
if "val_subtotal" not in st.session_state:
    st.session_state.val_subtotal = 0.0
if "val_abono" not in st.session_state:
    st.session_state.val_abono = 0.0

if st.session_state.get("reset_form", False):
    st.session_state.val_factura = ""
    st.session_state.val_rfc = ""
    st.session_state.val_cliente = ""
    st.session_state.val_desc = ""
    st.session_state.val_fecha = datetime.today().strftime('%Y-%m-%d')
    st.session_state.val_subtotal = 0.0
    st.session_state.val_abono = 0.0
    st.session_state.reset_form = False

try:
    sheet = spreadsheet.worksheet(pestana_seleccionada)
except Exception:
    sheet = spreadsheet.add_worksheet(title=pestana_seleccionada, rows=100, cols=10)
    
if pestana_seleccionada == "Abono a tarjeta de crédito":
    try:
        sheet.update(range_name="A1", values=[["Mes", "Abono TC", "Descripcion", "Tarjeta Debito", "Saldo TC", "FECHA"]])
    except Exception:
        sheet.update("A1", [["Mes", "Abono TC", "Descripcion", "Tarjeta Debito", "Saldo TC", "FECHA"]])
        
df = load_data(pestana_seleccionada)

if pestana_seleccionada != "Utilidad":
    with st.sidebar.form("form_agregar_registro", clear_on_submit=False):
        if pestana_seleccionada == "Abono a tarjeta de crédito":
            f_abono = st.number_input("Abono TC", format="%.2f", key="val_abono")
            f_descripcion = st.text_input("Descripción", key="val_desc")
            f_fecha = st.text_input("Fecha (YYYY-MM-DD)", key="val_fecha")
            submit_agregar = st.form_submit_button("Guardar Registro")
            
            if submit_agregar:
                f_desc_upper = f_descripcion.strip().upper()
                if not f_desc_upper or not f_fecha.strip():
                    st.sidebar.error("Por favor completa la descripción y la fecha.")
                else:
                    nuevo_reg = {
                        "Mes": "",
                        "Abono TC": f"{f_abono:.2f}",
                        "Descripcion": f_desc_upper,
                        "Tarjeta Debito": "",
                        "Saldo TC": "",
                        "FECHA": f_fecha.strip()
                    }
                    current_records = []
                    if not df.empty:
                        for _, r in df.iterrows():
                            d_check = str(r.get("Descripcion", r.get("DESCRIPCION", ""))).strip()
                            if d_check and not d_check.startswith("---") and not d_check.startswith("TOTALES") and not d_check.startswith("El mes") and d_check.upper() != "PRUEBA":
                                current_records.append(r.to_dict())
                    current_records.append(nuevo_reg)
                    temp_df = pd.DataFrame(current_records)
                    reorganized = reorganizar_con_meses_en_sheet(temp_df, pestana_seleccionada)
                    headers = ["Mes", "Abono TC", "Descripcion", "Tarjeta Debito", "Saldo TC", "FECHA"]
                    sheet_data = [headers]
                    for r in reorganized:
                        fila_limpia = [str(r.get(h, "")) if r.get(h, "") is not None else "" for h in headers]
                        sheet_data.append(fila_limpia)
                    sheet.clear()
                    try:
                        sheet.update(range_name="A1", values=sheet_data)
                    except Exception:
                        sheet.update("A1", sheet_data)
                    load_data.clear()
                    st.session_state.reset_form = True
                    st.sidebar.success("¡Guardado con éxito!")
                    st.rerun()
        else:
            f_factura = st.text_input("Factura", key="val_factura")
            if pestana_seleccionada == "Clientes":
                f_cliente = st.text_input("Clientes", key="val_cliente")
                f_descripcion = st.text_input("Descripción", key="val_desc")
                f_fecha = st.text_input("Fecha (YYYY-MM-DD)", key="val_fecha")
                f_subtotal = st.number_input("Subtotal", format="%.2f", key="val_subtotal")
                
                calc_iva = f_subtotal * 0.16
                calc_isr = f_subtotal * 0.0125
                calc_tot = f_subtotal + calc_iva - calc_isr
                
                f_iva_input = st.text_input("IVA (16%)", value=f"{calc_iva:.2f}")
                f_isr_input = st.text_input("ISR (1.25%)", value=f"{calc_isr:.2f}")
                st.sidebar.info(f"Total estimado: ${calc_tot:.2f}")
            elif pestana_seleccionada == "Proveedores":
                f_rfc = st.text_input("RFC", key="val_rfc")
                f_proveedor = st.text_input("Proveedor", key="val_cliente")
                f_descripcion = st.text_input("Descripción", key="val_desc")
                f_fecha = st.text_input("Fecha (YYYY-MM-DD)", key="val_fecha")
                f_subtotal = st.number_input("Subtotal", format="%.2f", key="val_subtotal")
                
                calc_iva = f_subtotal * 0.16
                calc_tot = f_subtotal + calc_iva
                
                f_iva_input = st.text_input("IVA (16%)", value=f"{calc_iva:.2f}")
                st.sidebar.info(f"Total estimado: ${calc_tot:.2f}")
            else:
                f_rfc = st.text_input("RFC", key="val_rfc")
                f_proveedor = st.text_input("Proveedor", key="val_cliente")
                f_descripcion = st.text_input("Descripción", key="val_desc")
                f_fecha = st.text_input("Fecha (YYYY-MM-DD)", key="val_fecha")
                f_subtotal = st.number_input("Subtotal", format="%.2f", key="val_subtotal")
                
                calc_iva = f_subtotal * 0.16
                calc_tot = f_subtotal + calc_iva
                
                f_iva_input = st.text_input("IVA (16%)", value=f"{calc_iva:.2f}")
                st.sidebar.info(f"Total estimado: ${calc_tot:.2f}")

            f_estatus = st.selectbox("Estatus", options=["PENDIENTE", "PAGADA"], key="val_estatus")
            submit_agregar = st.form_submit_button("Guardar Registro")
            
            if submit_agregar:
                f_fact_upper = f_factura.strip().upper()
                f_desc_upper = f_descripcion.strip().upper()
                
                if not f_fact_upper or not f_fecha.strip():
                    st.sidebar.error("Completa Factura y Fecha.")
                else:
                    facturas_existentes = []
                    if not df.empty:
                        for _, r in df.iterrows():
                            f_val = str(r.get("FACTURA", "")).strip()
                            if f_val and not f_val.startswith("---") and not f_val.startswith("TOTALES") and not f_val.startswith("El mes"):
                                facturas_existentes.append(f_val)
                                
                    if f_fact_upper in facturas_existentes:
                        st.sidebar.error(f"¡La factura '{f_fact_upper}' ya existe!")
                    else:
                        try:
                            f_iva = float(f_iva_input.replace(',', '.')) if f_iva_input.strip() != "" else f_subtotal * 0.16
                        except ValueError:
                            f_iva = 0.0

                        if pestana_seleccionada == "Clientes":
                            try:
                                f_isr = float(f_isr_input.replace(',', '.')) if f_isr_input.strip() != "" else f_subtotal * 0.0125
                            except ValueError:
                                f_isr = 0.0
                            f_total = f_subtotal + f_iva - f_isr
                            
                            nuevo_reg = {
                                "FACTURA": f_fact_upper,
                                "CLIENTES": f_cliente.strip().upper(),
                                "DESCRIPCION": f_desc_upper,
                                "FECHA": f_fecha.strip(),
                                "SUBTOTAL": f"{f_subtotal:.2f}",
                                "IVA": f"{f_iva:.2f}",
                                "ISR": f"{f_isr:.2f}",
                                "TOTAL": f"{f_total:.2f}",
                                "ESTATUS": f_estatus
                            }
                        else:
                            f_total = f_subtotal + f_iva
                            nuevo_reg = {
                                "FACTURA": f_fact_upper,
                                "RFC": f_rfc.strip().upper(),
                                "PROVEEDOR": f_proveedor.strip().upper(),
                                "DESCRIPCION": f_desc_upper,
                                "FECHA": f_fecha.strip(),
                                "SUBTOTAL": f"{f_subtotal:.2f}",
                                "IVA": f"{f_iva:.2f}",
                                "TOTAL": f"{f_total:.2f}",
                                "ESTATUS": f_estatus
                            }
                            
                        current_records = []
                        if not df.empty:
                            for _, r in df.iterrows():
                                f_val = str(r.get("FACTURA", "")).strip()
                                if f_val and not f_val.startswith("---") and not f_val.startswith("TOTALES") and not f_val.startswith("El mes"):
                                    current_records.append(r.to_dict())
                        current_records.append(nuevo_reg)
                        
                        temp_df = pd.DataFrame(current_records)
                        reorganized = reorganizar_con_meses_en_sheet(temp_df, pestana_seleccionada)
                        
                        headers = list(df.columns)
                        sheet_data = [headers]
                        for r in reorganized:
                            fila_limpia = [str(r.get(h, "")) if r.get(h, "") is not None else "" for h in headers]
                            sheet_data.append(fila_limpia)
                            
                        sheet.clear()
                        try:
                            sheet.update(range_name="A1", values=sheet_data)
                        except Exception:
                            sheet.update("A1", sheet_data)
                            
                        recalcular_y_sincronizar_tarjeta_tc()

                        load_data.clear()
                        st.session_state.reset_form = True
                        st.sidebar.success("¡Guardado con éxito!")
                        st.rerun()

st.markdown("---")
if pestana_seleccionada == "Utilidad":
    st.subheader("Vista actual: Utilidad (Calculada Automáticamente)")
    df_utilidad = calcular_tabla_utilidad()
    st.dataframe(df_utilidad, use_container_width=True)
    
    pdf_utilidad_bytes = generar_pdf(df_utilidad, "Utilidad")
    st.download_button(
        label="📥 Descargar Inventario PDF",
        data=pdf_utilidad_bytes,
        file_name="Reporte_Utilidad.pdf",
        mime="application/pdf"
    )
    try:
        sheet_utilidad = spreadsheet.worksheet("Utilidad")
        headers_util = list(df_utilidad.columns)
        data_util = [headers_util]
        for _, r in df_utilidad.iterrows():
            data_util.append([str(r.get(h, "")) for h in headers_util])
        sheet_utilidad.clear()
        try:
            sheet_utilidad.update(range_name="A1", values=data_util)
        except Exception:
            sheet_utilidad.update("A1", data_util)
    except Exception:
        pass
else:
    if pestana_seleccionada == "Abono a tarjeta de crédito" and df.empty:
        try:
            sheet.clear()
            sheet.update(range_name="A1", values=[["Mes", "Abono TC", "Descripcion", "Tarjeta Debito", "Saldo TC", "FECHA"]])
            df = load_data(pestana_seleccionada)
        except Exception:
            pass

    if not df.empty:
        registros_a_normalizar = []
        cambio_necesario = False
        for _, r in df.iterrows():
            r_dict = r.to_dict()
            identificador = str(r_dict.get("FACTURA", r_dict.get("Abono TC", r_dict.get("ABONO TC", "")))).strip()
            desc_check = str(r_dict.get("Descripcion", r_dict.get("DESCRIPCION", ""))).strip()
            
            if desc_check.upper() == "PRUEBA":
                cambio_necesario = True
                continue

            es_valido = False
            if pestana_seleccionada == "Abono a tarjeta de crédito":
                es_valido = bool(desc_check and not desc_check.startswith("---") and not desc_check.startswith("TOTALES") and not desc_check.startswith("El mes"))
            else:
                es_valido = bool(identificador and not identificador.startswith("---") and not identificador.startswith("TOTALES") and not identificador.startswith("El mes"))

            if es_valido:
                if pestana_seleccionada == "Abono a tarjeta de crédito":
                    for col_num in ["Abono TC", "ABONO TC", "Tarjeta Debito", "Saldo TC"]:
                        if col_num in r_dict and str(r_dict[col_num]).strip() != "":
                            val_num = limpiar_numero(r_dict[col_num])
                            val_fmt = f"{val_num:.2f}"
                            if str(r_dict[col_num]).strip() != val_fmt:
                                r_dict[col_num] = val_fmt
                                cambio_necesario = True
                else:
                    for col_num in ["SUBTOTAL", "IVA", "ISR", "TOTAL"]:
                        if col_num in r_dict and str(r_dict[col_num]).strip() != "":
                            val_num = limpiar_numero(r_dict[col_num])
                            val_fmt = f"{val_num:.2f}"
                            if str(r_dict[col_num]).strip() != val_fmt:
                                r_dict[col_num] = val_fmt
                                cambio_necesario = True
                                
                    if pestana_seleccionada == "Clientes":
                        sub = limpiar_numero(r_dict.get("SUBTOTAL", 0))
                        iva = limpiar_numero(r_dict.get("IVA", 0))
                        isr = limpiar_numero(r_dict.get("ISR", 0))
                        tot_esperado = sub + iva - isr
                        if abs(limpiar_numero(r_dict.get("TOTAL", 0)) - tot_esperado) > 0.01:
                            r_dict["TOTAL"] = f"{tot_esperado:.2f}"
                            cambio_necesario = True
                                
                registros_a_normalizar.append(r_dict)
            else:
                registros_a_normalizar.append(r_dict)
                
        if cambio_necesario:
            temp_df = pd.DataFrame(registros_a_normalizar)
            reorganized = reorganizar_con_meses_en_sheet(temp_df, pestana_seleccionada)
            headers = list(df.columns)
            sheet_data = [headers]
            for r in reorganized:
                fila_limpia = [str(r.get(h, "")) if r.get(h, "") is not None else "" for h in headers]
                sheet_data.append(fila_limpia)
            sheet.clear()
            try:
                sheet.update(range_name="A1", values=sheet_data)
            except Exception:
                sheet.update("A1", sheet_data)
            load_data.clear()
            df = load_data(pestana_seleccionada)

    recalcular_y_sincronizar_tarjeta_tc()

    st.subheader(f"Vista actual: {pestana_seleccionada}")
    
    def resaltar_pendientes(row):
        estatus_val = str(row.get("ESTATUS", "")).strip().upper()
        if estatus_val == "PENDIENTE":
            return ['background-color: rgba(255, 75, 75, 0.25)'] * len(row)
        return [''] * len(row)

    if not df.empty and "ESTATUS" in df.columns:
        df_styled = df.style.apply(resaltar_pendientes, axis=1)
        st.dataframe(df_styled, use_container_width=True)
    else:
        st.dataframe(df, use_container_width=True)
    
    pdf_bytes = generar_pdf(df, pestana_seleccionada)
    st.download_button(
        label="📥 Descargar Inventario PDF",
        data=pdf_bytes,
        file_name=f"Reporte_{pestana_seleccionada}.pdf",
        mime="application/pdf"
    )

    st.markdown("---")
    st.subheader("Editar o Eliminar Registro Existente")
    
    # --- CORRECCIÓN CLAVE PARA MAPEO DE REGISTROS REALES ---
    opciones_dict = {}
    registros_validos_lista = []
    
    if not df.empty:
        for _, r in df.iterrows():
            r_dict = r.to_dict()
            if pestana_seleccionada == "Abono a tarjeta de crédito":
                identif = str(r_dict.get("Descripcion", r_dict.get("DESCRIPCION", ""))).strip()
            else:
                identif = str(r_dict.get("FACTURA", "")).strip()
                
            if identif and not identif.startswith("---") and not identif.startswith("TOTALES") and not identif.startswith("El mes") and identif.upper() != "PRUEBA":
                fec = str(r_dict.get("FECHA", "")).strip()
                etiqueta = f"{identif} ({fec})"
                opciones_dict[etiqueta] = r_dict
                registros_validos_lista.append(r_dict)
                
    if not opciones_dict:
        st.info("No hay registros válidos para editar o eliminar.")
    else:
        opciones_registros = ["-- Selecciona un registro --"] + list(opciones_dict.keys())

        if "select_edit" not in st.session_state:
            st.session_state.select_edit = "-- Selecciona un registro --"

        def actualizar_campos_edicion():
            seleccion_actual = st.session_state.select_edit
            if seleccion_actual != "-- Selecciona un registro --" and seleccion_actual in opciones_dict:
                fila_df = opciones_dict[seleccion_actual]
                st.session_state.last_edit_selection = seleccion_actual
                if pestana_seleccionada == "Abono a tarjeta de crédito":
                    try:
                        st.session_state.e_abono = float(str(fila_df.get("Abono TC", fila_df.get("ABONO TC", 0))).replace(',', '.'))
                    except ValueError:
                        st.session_state.e_abono = 0.0
                    st.session_state.e_desc = str(fila_df.get("Descripcion", fila_df.get("DESCRIPCION", "")))
                    st.session_state.e_fec = str(fila_df.get("FECHA", ""))
                else:
                    st.session_state.e_fact = str(fila_df.get("FACTURA", ""))
                    st.session_state.e_c2 = str(fila_df.get("RFC", ""))
                    st.session_state.e_c3 = str(fila_df.get("CLIENTES", fila_df.get("PROVEEDOR", "")))
                    st.session_state.e_desc = str(fila_df.get("DESCRIPCION", ""))
                    st.session_state.e_fec = str(fila_df.get("FECHA", ""))
                    try:
                        sub_str = str(fila_df.get("SUBTOTAL", 0)).replace(',', '.')
                        st.session_state.e_sub = float(sub_str)
                    except ValueError:
                        st.session_state.e_sub = 0.0
                    st.session_state.e_est_idx = 0 if str(fila_df.get("ESTATUS", "PENDIENTE")) != "PAGADA" else 1

        seleccion = st.selectbox("Selecciona el registro a modificar", options=opciones_registros, key="select_edit", on_change=actualizar_campos_edicion)
        
        if seleccion == "-- Selecciona un registro --":
            st.info("👆 Selecciona un registro para habilitar la edición.")
        else:
            registro_seleccionado_dict = opciones_dict[seleccion]
            
            if "last_edit_selection" not in st.session_state or st.session_state.last_edit_selection != seleccion:
                actualizar_campos_edicion()

            with st.form("form_editar_factura"):
                if pestana_seleccionada == "Abono a tarjeta de crédito":
                    e_abono = st.number_input("Abono TC", format="%.2f", key="e_abono")
                    e_descripcion = st.text_input("Descripción", key="e_desc")
                    e_fecha = st.text_input("Fecha (YYYY-MM-DD)", key="e_fec")
                    
                    col1, col2 = st.columns(2)
                    actualizar = col1.form_submit_button("Actualizar Registro")
                    eliminar = col2.form_submit_button("Eliminar Registro")
                    
                    if actualizar:
                        current_records = []
                        for r in registros_validos_lista:
                            desc_check = str(r.get("Descripcion", r.get("DESCRIPCION", ""))).strip()
                            fec_check = str(r.get("FECHA", "")).strip()
                            abono_check = str(r.get("Abono TC", r.get("ABONO TC", ""))).strip()
                            
                            # Identificar exactamente el registro a modificar por su contenido original
                            if (desc_check == str(registro_seleccionado_dict.get("Descripcion", registro_seleccionado_dict.get("DESCRIPCION", ""))).strip() and 
                                fec_check == str(registro_seleccionado_dict.get("FECHA", "")).strip() and
                                abono_check == str(registro_seleccionado_dict.get("Abono TC", registro_seleccionado_dict.get("ABONO TC", ""))).strip()):
                                temp_mod = r.copy()
                                temp_mod["Abono TC"] = f"{e_abono:.2f}"
                                temp_mod["Descripcion"] = e_descripcion.strip().upper()
                                temp_mod["FECHA"] = e_fecha.strip()
                                current_records.append(temp_mod)
                            else:
                                current_records.append(r)

                        temp_df = pd.DataFrame(current_records)
                        reorganized = reorganizar_con_meses_en_sheet(temp_df, pestana_seleccionada)
                        headers = ["Mes", "Abono TC", "Descripcion", "Tarjeta Debito", "Saldo TC", "FECHA"]
                        sheet_data = [headers]
                        for r in reorganized:
                            fila_limpia = [str(r.get(h, "")) if r.get(h, "") is not None else "" for h in headers]
                            sheet_data.append(fila_limpia)
                            
                        sheet.clear()
                        try:
                            sheet.update(range_name="A1", values=sheet_data)
                        except Exception:
                            sheet.update("A1", sheet_data)
                        
                        recalcular_y_sincronizar_tarjeta_tc()
                        load_data.clear()
                        st.session_state.select_edit = "-- Selecciona un registro --"
                        st.success("¡Actualizado y sincronizado con éxito!")
                        st.rerun()
                else:
                    e_factura = st.text_input("Factura", key="e_fact")
                    if pestana_seleccionada == "Clientes":
                        e_cliente = st.text_input("Clientes", key="e_c3")
                        e_descripcion = st.text_input("Descripción", key="e_desc")
                        e_fecha = st.text_input("Fecha (YYYY-MM-DD)", key="e_fec")
                        e_subtotal = st.number_input("Subtotal", format="%.2f", key="e_sub")
                        
                        calc_e_iva = e_subtotal * 0.16
                        calc_e_isr = e_subtotal * 0.0125
                        calc_e_tot = e_subtotal + calc_e_iva - calc_e_isr
                        
                        e_iva_input = st.text_input("IVA (16%)", value=f"{calc_e_iva:.2f}")
                        e_isr_input = st.text_input("ISR (1.25%)", value=f"{calc_e_isr:.2f}")
                        st.info(f"Total estimado: ${calc_e_tot:.2f}")
                    else:
                        e_rfc = st.text_input("RFC", key="e_c2")
                        e_prov = st.text_input("Proveedor", key="e_c3")
                        e_descripcion = st.text_input("Descripción", key="e_desc")
                        e_fecha = st.text_input("Fecha (YYYY-MM-DD)", key="e_fec")
                        e_subtotal = st.number_input("Subtotal", format="%.2f", key="e_sub")
                        
                        calc_e_iva = e_subtotal * 0.16
                        calc_e_tot = e_subtotal + calc_e_iva
                        
                        e_iva_input = st.text_input("IVA (16%)", value=f"{calc_e_iva:.2f}")
                        st.info(f"Total estimado: ${calc_e_tot:.2f}")

                    e_estatus = st.selectbox("Estatus", options=["PENDIENTE", "PAGADA"], index=st.session_state.get("e_est_idx", 0), key="e_est")
                    
                    col1, col2 = st.columns(2)
                    actualizar = col1.form_submit_button("Actualizar Registro")
                    eliminar = col2.form_submit_button("Eliminar Registro")
                    
                    if actualizar:
                        e_fact_upper = e_factura.strip().upper()
                        e_desc_upper = e_descripcion.strip().upper()
                        
                        facturas_existentes = []
                        for r in registros_validos_lista:
                            f_val = str(r.get("FACTURA", "")).strip()
                            if f_val and f_val != str(registro_seleccionado_dict.get("FACTURA", "")).strip():
                                facturas_existentes.append(f_val)
                                    
                        if e_fact_upper in facturas_existentes:
                            st.error(f"¡Error! La factura '{e_fact_upper}' ya pertenece a otro registro.")
                        else:
                            try:
                                e_iva = float(e_iva_input.replace(',', '.')) if e_iva_input.strip() != "" else e_subtotal * 0.16
                            except ValueError:
                                e_iva = 0.0

                            if pestana_seleccionada == "Clientes":
                                try:
                                    e_isr = float(e_isr_input.replace(',', '.')) if e_isr_input.strip() != "" else e_subtotal * 0.0125
                                except ValueError:
                                    e_isr = 0.0
                                e_total = e_subtotal + e_iva - e_isr
                                
                                updated_row = {
                                    "FACTURA": e_fact_upper,
                                    "CLIENTES": e_cliente.strip().upper(),
                                    "DESCRIPCION": e_desc_upper,
                                    "FECHA": e_fecha.strip(),
                                    "SUBTOTAL": f"{e_subtotal:.2f}",
                                    "IVA": f"{e_iva:.2f}",
                                    "ISR": f"{e_isr:.2f}",
                                    "TOTAL": f"{e_total:.2f}",
                                    "ESTATUS": e_estatus
                                }
                            else:
                                e_total = e_subtotal + e_iva
                                updated_row = {
                                    "FACTURA": e_fact_upper,
                                    "RFC": e_rfc.strip().upper(),
                                    "PROVEEDOR": e_prov.strip().upper(),
                                    "DESCRIPCION": e_desc_upper,
                                    "FECHA": e_fecha.strip(),
                                    "SUBTOTAL": f"{e_subtotal:.2f}",
                                    "IVA": f"{e_iva:.2f}",
                                    "TOTAL": f"{e_total:.2f}",
                                    "ESTATUS": e_estatus
                                }
                            
                            current_records = []
                            for r in registros_validos_lista:
                                f_val = str(r.get("FACTURA", "")).strip()
                                if f_val == str(registro_seleccionado_dict.get("FACTURA", "")).strip():
                                    current_records.append(updated_row)
                                else:
                                    current_records.append(r)
                                        
                            temp_df = pd.DataFrame(current_records)
                            reorganized = reorganizar_con_meses_en_sheet(temp_df, pestana_seleccionada)
                            
                            headers = list(df.columns)
                            sheet_data = [headers]
                            for r in reorganized:
                                fila_limpia = [str(r.get(h, "")) if r.get(h, "") is not None else "" for h in headers]
                                sheet_data.append(fila_limpia)
                                
                            sheet.clear()
                            try:
                                sheet.update(range_name="A1", values=sheet_data)
                            except Exception:
                                sheet.update("A1", sheet_data)
                            
                            recalcular_y_sincronizar_tarjeta_tc()
                            load_data.clear()
                            st.session_state.select_edit = "-- Selecciona un registro --"
                            st.success("¡Actualizado y sincronizado con éxito!")
                            st.rerun()
                    
                if eliminar:
                    current_records = []
                    for r in registros_validos_lista:
                        if pestana_seleccionada == "Abono a tarjeta de crédito":
                            match = (str(r.get("Descripcion", "")).strip() == str(registro_seleccionado_dict.get("Descripcion", "")).strip() and
                                     str(r.get("FECHA", "")).strip() == str(registro_seleccionado_dict.get("FECHA", "")).strip() and
                                     str(r.get("Abono TC", "")).strip() == str(registro_seleccionado_dict.get("Abono TC", "")).strip())
                        else:
                            match = (str(r.get("FACTURA", "")).strip() == str(registro_seleccionado_dict.get("FACTURA", "")).strip())
                        
                        if match:
                            continue 
                        current_records.append(r)
                            
                    temp_df = pd.DataFrame(current_records)
                    reorganized = reorganizar_con_meses_en_sheet(temp_df, pestana_seleccionada)
                    
                    headers = list(df.columns)
                    sheet_data = [headers]
                    for r in reorganized:
                        fila_limpia = [str(r.get(h, "")) if r.get(h, "") is not None else "" for h in headers]
                        sheet_data.append(fila_limpia)
                        
                    sheet.clear()
                    try:
                        sheet.update(range_name="A1", values=sheet_data)
                    except Exception:
                        sheet.update("A1", sheet_data)
                    
                    recalcular_y_sincronizar_tarjeta_tc()
                    load_data.clear()
                    st.session_state.select_edit = "-- Selecciona un registro --"
                    st.success("¡Registro eliminado y totales recalculados correctamente!")
                    st.rerun()