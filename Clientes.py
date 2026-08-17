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
    if "\\n" in creds_dict["private_key"]:
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
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
        if estatus == "PAGADA":
            total_pagado += limpiar_numero(row.get("TOTAL", 0))
    return total_pagado

def calcular_utilidad_mes(m_num):
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
            for mn, m_str in meses_nombres.items():
                if m_str in fila_str:
                    mes_encontrado = mn
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

    sub_c = extraer_subtotales_por_mes(df_c).get(m_num, 0.0)
    sub_p = extraer_subtotales_por_mes(df_p).get(m_num, 0.0)
    sub_g = extraer_subtotales_por_mes(df_g).get(m_num, 0.0)
    return sub_c - sub_p - sub_g

def reorganizar_con_meses_en_sheet(df_actual, tipo_seccion):
    registros = []
    for _, row in df_actual.iterrows():
        identificador = str(row.get("FACTURA", row.get("ABONO TC", ""))).strip()
        if identificador and not identificador.startswith("---") and not identificador.startswith("TOTALES"):
            r_dict = row.to_dict()
            if tipo_seccion == "Abono a tarjeta de crédito":
                for col_num in ["ABONO TC", "Tarjeta Debito", "SALDO TC"]:
                    if col_num in r_dict and str(r_dict[col_num]).strip() != "":
                        r_dict[col_num] = f"{limpiar_numero(r_dict[col_num]):.2f}"
            else:
                for col_num in ["SUBTOTAL", "IVA", "ISR", "TOTAL"]:
                    if col_num in r_dict and str(r_dict[col_num]).strip() != "":
                        r_dict[col_num] = f"{limpiar_numero(r_dict[col_num]):.2f}"
            registros.append(r_dict)
            
    if not registros:
        return []

    def clave_orden(r):
        dt = parsear_fecha(r.get("FECHA", ""))
        return dt if dt else datetime.min

    registros.sort(key=clave_orden)

    nueva_data = []
    mes_actual = None
    registros_mes_actual = []
    saldo_tc_acumulado = 0.0

    def agregar_totales_mes(m_num, regs_mes):
        fila_tot = {col: "" for col in df_actual.columns}
        if tipo_seccion == "Abono a tarjeta de crédito":
            if "ABONO TC" in df_actual.columns:
                fila_tot["ABONO TC"] = "TOTALES DEL MES"
            elif "Mes" in df_actual.columns:
                fila_tot["Mes"] = "TOTALES DEL MES"
            
            t_abono = sum(limpiar_numero(r.get("ABONO TC", 0)) for r in regs_mes)
            if "ABONO TC" in df_actual.columns: 
                fila_tot["ABONO TC"] = f"{t_abono:.2f}"
            if "Saldo TC" in df_actual.columns and regs_mes:
                fila_tot["Saldo TC"] = regs_mes[-1].get("Saldo TC", "0.00")
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

    for reg in registros:
        dt = parsear_fecha(reg.get("FECHA", ""))
        if dt:
            if dt.month != mes_actual:
                if mes_actual is not None and registros_mes_actual:
                    fila_fin = {col: "" for col in df_actual.columns}
                    fila_fin[df_actual.columns[0]] = f"El mes termino con = {saldo_tc_acumulado:.2f}"
                    nueva_data.append(fila_fin)
                    nueva_data.append(agregar_totales_mes(mes_actual, registros_mes_actual))
                    registros_mes_actual = []
                
                mes_actual = dt.month
                nombre_div = meses_nombres.get(mes_actual, "--- MES ---")
                fila_div = {col: "" for col in df_actual.columns}
                fila_div[df_actual.columns[0]] = nombre_div
                
                if tipo_seccion == "Abono a tarjeta de crédito":
                    t_debito_actual = calcular_total_tarjeta_debito_pagada()
                    saldo_tc_acumulado = t_debito_actual
                    if len(df_actual.columns) > 1:
                        fila_div[df_actual.columns[1]] = f"El mes se inicio con: {t_debito_actual:.2f}"
                
                nueva_data.append(fila_div)
        
        if tipo_seccion == "Abono a tarjeta de crédito":
            abono_val = limpiar_numero(reg.get("ABONO TC", 0))
            t_debito_val = calcular_total_tarjeta_debito_pagada()
            saldo_tc_acumulado = max(0.0, t_debito_val - abono_val)
            reg["Tarjeta Debito"] = f"{t_debito_val:.2f}"
            reg["Saldo TC"] = f"{saldo_tc_acumulado:.2f}"

        registros_mes_actual.append(reg)
        nueva_data.append(reg)
        
    if mes_actual is not None and registros_mes_actual:
        fila_fin = {col: "" for col in df_actual.columns}
        fila_fin[df_actual.columns[0]] = f"El mes termino con = {saldo_tc_acumulado:.2f}"
        nueva_data.append(fila_fin)
        nueva_data.append(agregar_totales_mes(mes_actual, registros_mes_actual))

    return nueva_data

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
        name='TitleStyle',
        parent=styles['Heading1'],
        fontSize=16,
        leading=20,
        alignment=1,
        textColor=colors.HexColor('#1f2937')
    )
    cell_style = ParagraphStyle(
        name='CellStyle',
        parent=styles['Normal'],
        fontSize=8,
        leading=10,
        textColor=colors.HexColor('#374151')
    )
    header_style = ParagraphStyle(
        name='HeaderStyle',
        parent=styles['Normal'],
        fontSize=9,
        leading=11,
        fontName='Helvetica-Bold',
        textColor=colors.whitesmoke,
        alignment=1
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

# --- INTERFAZ STREAMLIT ---
st.set_page_config(layout="wide")

col_titulo, col_metrica = st.columns([2, 1])

with col_titulo:
    st.title("Control de Clientes, Proveedores y Gastos")

with col_metrica:
    df_temp_tc = load_data("Abono a tarjeta de crédito")
    ultimo_saldo_tc = 0.0
    if not df_temp_tc.empty:
        for _, r in df_temp_tc.iterrows():
            s_val = str(r.get("Saldo TC", "")).strip()
            if s_val and not s_val.startswith("---") and not s_val.startswith("TOTALES"):
                ultimo_saldo_tc = limpiar_numero(s_val)
    st.metric(label="💳 Saldo Actual Tarjeta de Crédito", value=f"${ultimo_saldo_tc:.2f}")

pestana_seleccionada = st.radio(
    "Selecciona la sección a gestionar:",
    options=["Clientes", "Proveedores", "Gastos", "Utilidad", "Abono a tarjeta de crédito"],
    horizontal=True
)

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
        sheet_utilidad.update("A1", data_util)
    except Exception:
        pass

else:
    try:
        sheet = spreadsheet.worksheet(pestana_seleccionada)
    except Exception:
        sheet = spreadsheet.add_worksheet(title=pestana_seleccionada, rows=100, cols=10)
        if pestana_seleccionada == "Abono a tarjeta de crédito":
            sheet.update("A1", [["Mes", "Abono TC", "Descripcion", "Tarjeta Debito", "Saldo TC", "FECHA"]])

    df = load_data(pestana_seleccionada)

    if not df.empty:
        registros_a_normalizar = []
        cambio_necesario = False
        for _, r in df.iterrows():
            r_dict = r.to_dict()
            identificador = str(r_dict.get("FACTURA", r_dict.get("ABONO TC", ""))).strip()
            if identificador and not identificador.startswith("---") and not identificador.startswith("TOTALES"):
                if pestana_seleccionada == "Abono a tarjeta de crédito":
                    for col_num in ["ABONO TC", "Tarjeta Debito", "SALDO TC"]:
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
            sheet.update("A1", sheet_data)
            load_data.clear()
            df = load_data(pestana_seleccionada)

    st.subheader(f"Vista actual: {pestana_seleccionada}")
    st.dataframe(df, use_container_width=True)

    pdf_bytes = generar_pdf(df, pestana_seleccionada)
    st.download_button(
        label="📥 Descargar Inventario PDF",
        data=pdf_bytes,
        file_name=f"Reporte_{pestana_seleccionada}.pdf",
        mime="application/pdf"
    )

    if "val_factura" not in st.session_state: st.session_state.val_factura = ""
    if "val_col2" not in st.session_state: st.session_state.val_col2 = "" 
    if "val_col3" not in st.session_state: st.session_state.val_col3 = "" 
    if "val_descripcion" not in st.session_state: st.session_state.val_descripcion = ""
    if "val_fecha" not in st.session_state: st.session_state.val_fecha = datetime.today()
    if "val_subtotal" not in st.session_state: st.session_state.val_subtotal = 0.0

    if "reset_edit" in st.session_state and st.session_state.reset_edit:
        st.session_state.select_edit = "-- Selecciona un registro --"
        st.session_state.reset_edit = False

    st.sidebar.header(f"Dar de alta en {pestana_seleccionada}" if pestana_seleccionada != "Abono a tarjeta de crédito" else "Registrar Abono a tarjeta de crédito")
    with st.sidebar.form(f"alta_form_{pestana_seleccionada}", clear_on_submit=True):
        if pestana_seleccionada == "Abono a tarjeta de crédito":
            fecha = st.date_input("FECHA", value=st.session_state.val_fecha)
            abono_tc = st.number_input("ABONO TC", min_value=0.0, value=0.0, format="%.2f")
            descripcion = st.text_input("DESCRIPCION", value="")
        else:
            factura = st.text_input("FACTURA", value=st.session_state.val_factura)
            if pestana_seleccionada == "Clientes":
                cliente = st.text_input("CLIENTES", value=st.session_state.val_col3)
                descripcion = st.text_input("DESCRIPCION", value=st.session_state.val_descripcion)
                fecha = st.date_input("FECHA", value=st.session_state.val_fecha)
                subtotal = st.number_input("SUBTOTAL", min_value=0.0, value=st.session_state.val_subtotal, format="%.2f")
                
                calc_iva = f"{subtotal * 0.16:.2f}"
                calc_isr = f"{subtotal * 0.0125:.2f}"
                iva_input = st.text_input("IVA (Opcional, 16%)", value=calc_iva)
                isr_input = st.text_input("ISR (Opcional, 1.25%)", value=calc_isr)
            else: 
                col2_label = "RFC"
                col3_label = "PROVEEDOR"
                c2_input = st.text_input(col2_label, value=st.session_state.val_col2)
                c3_input = st.text_input(col3_label, value=st.session_state.val_col3)
                descripcion = st.text_input("DESCRIPCION", value=st.session_state.val_descripcion)
                fecha = st.date_input("FECHA", value=st.session_state.val_fecha)
                subtotal = st.number_input("SUBTOTAL", min_value=0.0, value=st.session_state.val_subtotal, format="%.2f")
                
                calc_iva = f"{subtotal * 0.16:.2f}"
                iva_input = st.text_input("IVA (Opcional, 16%)", value=calc_iva)

        submitted = st.form_submit_button("Guardar")
        
        if submitted:
            if pestana_seleccionada == "Abono a tarjeta de crédito":
                desc_upper = descripcion.strip().upper()
                valido = bool(desc_upper)
                
                if valido:
                    current_records = []
                    if not df.empty:
                        for _, r in df.iterrows():
                            val_check = str(r.get("ABONO TC", "")).strip()
                            if val_check and not val_check.startswith("---") and not val_check.startswith("TOTALES"):
                                current_records.append(r.to_dict())
                    
                    t_debito_val = calcular_total_tarjeta_debito_pagada()
                    new_row = {
                        "Mes": meses_nombres.get(fecha.month, "--- MES ---"),
                        "Abono TC": f"{abono_tc:.2f}",
                        "Descripcion": desc_upper,
                        "Tarjeta Debito": f"{t_debito_val:.2f}",
                        "Saldo TC": f"{abono_tc:.2f}",
                        "FECHA": str(fecha)
                    }
                    
                    current_records.append(new_row)
                    temp_df = pd.DataFrame(current_records)
                    reorganized = reorganizar_con_meses_en_sheet(temp_df, pestana_seleccionada)
                    
                    headers = list(df.columns) if not df.empty else ["Mes", "Abono TC", "Descripcion", "Tarjeta Debito", "Saldo TC", "FECHA"]
                    sheet_data = [headers]
                    for r in reorganized:
                        fila_limpia = [str(r.get(h, "")) if r.get(h, "") is not None else "" for h in headers]
                        sheet_data.append(fila_limpia)
                        
                    sheet.clear()
                    sheet.update("A1", sheet_data)
                    load_data.clear()
                    st.success("Guardado y sincronizado correctamente con Google Sheets")
                    st.rerun()
                else:
                    st.error("Por favor completa la descripción.")
            else:
                f_upper = factura.strip().upper()
                desc_upper = descripcion.strip().upper()
                
                if pestana_seleccionada == "Clientes":
                    c3_upper = cliente.strip().upper()
                    valido = bool(f_upper and c3_upper and desc_upper)
                else:
                    c2_upper = c2_input.strip().upper()
                    c3_upper = c3_input.strip().upper()
                    valido = bool(f_upper and c2_upper and c3_upper and desc_upper)

                if valido and subtotal >= 0:
                    facturas_existentes = [str(row.get("FACTURA", "")).strip() for _, row in df.iterrows() if str(row.get("FACTURA", "")).strip() and not str(row.get("FACTURA", "")).startswith("---") and not str(row.get("FACTURA", "")).startswith("TOTALES")]
                    if f_upper in facturas_existentes:
                        st.error(f"¡Error! La factura '{f_upper}' ya existe.")
                    else:
                        try:
                            iva = float(iva_input.replace(',', '.')) if iva_input.strip() != "" else subtotal * 0.16
                        except ValueError:
                            iva = 0.0

                        if pestana_seleccionada == "Clientes":
                            try:
                                isr = float(isr_input.replace(',', '.')) if isr_input.strip() != "" else subtotal * 0.0125
                            except ValueError:
                                isr = 0.0
                            total = subtotal + iva - isr
                            
                            new_row = {
                                "FACTURA": f_upper,
                                "CLIENTES": c3_upper,
                                "DESCRIPCION": desc_upper,
                                "FECHA": str(fecha),
                                "SUBTOTAL": f"{subtotal:.2f}",
                                "IVA": f"{iva:.2f}",
                                "ISR": f"{isr:.2f}",
                                "TOTAL": f"{total:.2f}",
                                "ESTATUS": "PENDIENTE"
                            }
                        else:
                            total = subtotal + iva
                            new_row = {
                                "FACTURA": f_upper,
                                "RFC": c2_upper,
                                "PROVEEDOR": c3_upper,
                                "DESCRIPCION": desc_upper,
                                "FECHA": str(fecha),
                                "SUBTOTAL": f"{subtotal:.2f}",
                                "IVA": f"{iva:.2f}",
                                "TOTAL": f"{total:.2f}",
                                "ESTATUS": "PENDIENTE"
                            }
                        
                        current_records = []
                        if not df.empty:
                            for _, r in df.iterrows():
                                f_val = str(r.get("FACTURA", "")).strip()
                                if f_val and not f_val.startswith("---") and not f_val.startswith("TOTALES"):
                                    current_records.append(r.to_dict())
                        
                        current_records.append(new_row)
                        temp_df = pd.DataFrame(current_records)
                        reorganized = reorganizar_con_meses_en_sheet(temp_df, pestana_seleccionada)
                        
                        headers = list(df.columns) if not df.empty else list(new_row.keys())
                        sheet_data = [headers]
                        for r in reorganized:
                            fila_limpia = [str(r.get(h, "")) if r.get(h, "") is not None else "" for h in headers]
                            sheet_data.append(fila_limpia)
                            
                        sheet.clear()
                        sheet.update("A1", sheet_data)
                        load_data.clear()
                        st.success("Guardado y sincronizado correctamente con Google Sheets")
                        st.rerun()
                else:
                    st.error("Por favor completa todos los campos obligatorios.")

    st.markdown("---")
    with st.expander(f"✏️ Editar o Eliminar en {pestana_seleccionada}"):
        if df.empty:
            st.info("No hay registros disponibles para editar.")
        else:
            opciones_registros = ["-- Selecciona un registro --"]
            indices_reales = [None]
            
            for idx, row in df.iterrows():
                if pestana_seleccionada == "Abono a tarjeta de crédito":
                    val_id = str(row.get('ABONO TC', '')).strip()
                    desc_id = str(row.get('DESCRIPCION', '')).strip()
                    if val_id and not val_id.startswith("---") and not val_id.startswith("TOTALES"):
                        label = f"Abono: ${val_id} | Desc: {desc_id}"
                        opciones_registros.append(label)
                        indices_reales.append(idx + 2)
                else:
                    fact = str(row.get('FACTURA', '')).strip()
                    if fact and not fact.startswith("---") and not fact.startswith("TOTALES"):
                        etiqueta_campo = row.get('CLIENTES', row.get('PROVEEDOR', row.get('COL_2', '')))
                        label = f"Factura: {fact} | Nombre: {etiqueta_campo}"
                        opciones_registros.append(label)
                        indices_reales.append(idx + 2)
                    
            if "select_edit" not in st.session_state:
                st.session_state.select_edit = "-- Selecciona un registro --"

            seleccion = st.selectbox("Selecciona el registro a modificar", options=opciones_registros, key="select_edit")
            
            if seleccion == "-- Selecciona un registro --":
                st.info("👆 Selecciona un registro para habilitar la edición.")
            else:
                idx_seleccionado = indices_reales[opciones_registros.index(seleccion)]
                fila_df = df.iloc[idx_seleccionado - 2]
                
                if "last_edit_selection" not in st.session_state or st.session_state.last_edit_selection != seleccion:
                    st.session_state.last_edit_selection = seleccion
                    if pestana_seleccionada == "Abono a tarjeta de crédito":
                        try:
                            st.session_state.e_abono = float(str(fila_df.get("ABONO TC", 0)).replace(',', '.'))
                        except ValueError:
                            st.session_state.e_abono = 0.0
                        st.session_state.e_desc = str(fila_df.get("DESCRIPCION", ""))
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
                            for i, r in df.iterrows():
                                val_check = str(r.get("ABONO TC", "")).strip()
                                if val_check and not val_check.startswith("---") and not val_check.startswith("TOTALES"):
                                    if (i + 2) == idx_seleccionado:
                                        temp_mod = r.to_dict()
                                        temp_mod["ABONO TC"] = f"{e_abono:.2f}"
                                        temp_mod["DESCRIPCION"] = e_descripcion.strip().upper()
                                        temp_mod["FECHA"] = e_fecha.strip()
                                        current_records.append(temp_mod)
                                    else:
                                        current_records.append(r.to_dict())

                            temp_df = pd.DataFrame(current_records)
                            reorganized = reorganizar_con_meses_en_sheet(temp_df, pestana_seleccionada)
                            
                            headers = list(df.columns)
                            sheet_data = [headers]
                            for r in reorganized:
                                fila_limpia = [str(r.get(h, "")) if r.get(h, "") is not None else "" for h in headers]
                                sheet_data.append(fila_limpia)
                                
                            sheet.clear()
                            sheet.update("A1", sheet_data)
                            load_data.clear()
                            st.session_state.reset_edit = True
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
                            for i, r in df.iterrows():
                                if (i + 2) != idx_seleccionado:
                                    f_val = str(r.get("FACTURA", "")).strip()
                                    if f_val and not f_val.startswith("---") and not f_val.startswith("TOTALES"):
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
                                for i, r in df.iterrows():
                                    if (i + 2) == idx_seleccionado:
                                        current_records.append(updated_row)
                                    else:
                                        f_val = str(r.get("FACTURA", "")).strip()
                                        if f_val and not f_val.startswith("---") and not f_val.startswith("TOTALES"):
                                            current_records.append(r.to_dict())
                                            
                                temp_df = pd.DataFrame(current_records)
                                reorganized = reorganizar_con_meses_en_sheet(temp_df, pestana_seleccionada)
                                
                                headers = list(df.columns)
                                sheet_data = [headers]
                                for r in reorganized:
                                    fila_limpia = [str(r.get(h, "")) if r.get(h, "") is not None else "" for h in headers]
                                    sheet_data.append(fila_limpia)
                                    
                                sheet.clear()
                                sheet.update("A1", sheet_data)
                                load_data.clear()
                                st.session_state.reset_edit = True
                                st.success("¡Actualizado y sincronizado con éxito!")
                                st.rerun()
                        
                    if eliminar:
                        current_records = []
                        for i, r in df.iterrows():
                            if (i + 2) == idx_seleccionado:
                                continue 
                            val_check = str(r.get("FACTURA", r.get("ABONO TC", ""))).strip()
                            if val_check and not val_check.startswith("---") and not val_check.startswith("TOTALES"):
                                current_records.append(r.to_dict())
                                
                        temp_df = pd.DataFrame(current_records)
                        reorganized = reorganizar_con_meses_en_sheet(temp_df, pestana_seleccionada)
                        
                        headers = list(df.columns)
                        sheet_data = [headers]
                        for r in reorganized:
                            fila_limpia = [str(r.get(h, "")) if r.get(h, "") is not None else "" for h in headers]
                            sheet_data.append(fila_limpia)
                            
                        sheet.clear()
                        sheet.update("A1", sheet_data)
                        load_data.clear()
                        st.session_state.reset_edit = True
                        st.success("¡Registro eliminado y totales recalculados correctamente!")
                        st.rerun()