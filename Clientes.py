import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# --- CONFIGURACION DE GOOGLE SHEETS ---
scope = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

# Cachear la conexión para evitar autenticaciones lentas repetidas
@st.cache_resource
def conectar_google_sheets():
    creds_dict = dict(st.secrets["gcp_service_account"])
    if "\\n" in creds_dict["private_key"]:
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)
    return client.open('Clientes y Proveedores')

spreadsheet = conectar_google_sheets()

# Cachear la lectura de datos por 5 minutos para máxima velocidad
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
        return pd.DataFrame()

# Diccionario de meses en español con formato espaciado
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

def reorganizar_con_meses_en_sheet(df_actual, tipo_seccion):
    registros = []
    for _, row in df_actual.iterrows():
        fact = str(row.get("FACTURA", "")).strip()
        if fact and not fact.startswith("---") and not fact.startswith("TOTALES"):
            registros.append(row.to_dict())
            
    if not registros:
        return []

    def clave_orden(r):
        dt = parsear_fecha(r.get("FECHA", ""))
        return dt if dt else datetime.min

    registros.sort(key=clave_orden)

    nueva_data = []
    mes_actual = None
    registros_mes_actual = []

    def agregar_totales_mes(m_num, regs_mes):
        fila_tot = {col: "" for col in df_actual.columns}
        if "FACTURA" in df_actual.columns:
            fila_tot["FACTURA"] = "TOTALES DEL MES"
            
        def limpiar_numero(val):
            if val is None:
                return 0.0
            val_str = str(val).strip().replace('$', '').replace(',', '.')
            if not val_str:
                return 0.0
            try:
                return float(val_str)
            except ValueError:
                return 0.0
            
        if tipo_seccion == "Clientes":
            t_sub = sum(limpiar_numero(r.get("SUBTOTAL", 0)) for r in regs_mes)
            t_iva = sum(limpiar_numero(r.get("IVA", 0)) for r in regs_mes)
            t_isr = sum(limpiar_numero(r.get("ISR", 0)) for r in regs_mes)
            t_tot = sum(limpiar_numero(r.get("TOTAL", 0)) for r in regs_mes)
            if "SUBTOTAL" in df_actual.columns: fila_tot["SUBTOTAL"] = f"{t_sub:.2f}"
            if "IVA" in df_actual.columns: fila_tot["IVA"] = f"{t_iva:.3f}"
            if "ISR" in df_actual.columns: fila_tot["ISR"] = f"{t_isr:.3f}"
            if "TOTAL" in df_actual.columns: fila_tot["TOTAL"] = f"{t_tot:.3f}"
        else:  # Proveedores y Gastos
            t_sub = sum(limpiar_numero(r.get("SUBTOTAL", 0)) for r in regs_mes)
            t_iva = sum(limpiar_numero(r.get("IVA", 0)) for r in regs_mes)
            t_tot = sum(limpiar_numero(r.get("TOTAL", 0)) for r in regs_mes)
            if "SUBTOTAL" in df_actual.columns: fila_tot["SUBTOTAL"] = f"{t_sub:.2f}"
            if "IVA" in df_actual.columns: fila_tot["IVA"] = f"{t_iva:.3f}"
            if "TOTAL" in df_actual.columns: fila_tot["TOTAL"] = f"{t_tot:.3f}"
            
        return fila_tot

    for reg in registros:
        dt = parsear_fecha(reg.get("FECHA", ""))
        if dt:
            if dt.month != mes_actual:
                if mes_actual is not None and registros_mes_actual:
                    nueva_data.append(agregar_totales_mes(mes_actual, registros_mes_actual))
                    registros_mes_actual = []
                
                mes_actual = dt.month
                nombre_div = meses_nombres.get(mes_actual, "--- MES ---")
                fila_div = {col: "" for col in df_actual.columns}
                fila_div[df_actual.columns[0]] = nombre_div
                nueva_data.append(fila_div)
        
        registros_mes_actual.append(reg)
        nueva_data.append(reg)
        
    if mes_actual is not None and registros_mes_actual:
        nueva_data.append(agregar_totales_mes(mes_actual, registros_mes_actual))

    return nueva_data

# --- INTERFAZ STREAMLIT ---
st.set_page_config(layout="wide")
st.title("Control de Clientes, Proveedores y Gastos")

# Selector principal de vistas arriba
pestana_seleccionada = st.radio(
    "Selecciona la sección a gestionar:",
    options=["Clientes", "Proveedores", "Gastos"],
    horizontal=True
)

st.markdown("---")

# Seleccionar la hoja de Google Sheets correspondiente
sheet = spreadsheet.worksheet(pestana_seleccionada)
df = load_data(pestana_seleccionada)

st.subheader(f"Vista actual: {pestana_seleccionada}")
st.dataframe(df, use_container_width=True)

# --- ESTADOS DE LIMPIEZA ---
if "val_factura" not in st.session_state: st.session_state.val_factura = ""
if "val_col2" not in st.session_state: st.session_state.val_col2 = "" 
if "val_col3" not in st.session_state: st.session_state.val_col3 = "" 
if "val_descripcion" not in st.session_state: st.session_state.val_descripcion = ""
if "val_fecha" not in st.session_state: st.session_state.val_fecha = datetime.today()
if "val_subtotal" not in st.session_state: st.session_state.val_subtotal = 0.0

if "reset_edit" in st.session_state and st.session_state.reset_edit:
    st.session_state.select_edit = "-- Selecciona un registro --"
    st.session_state.reset_edit = False

# --- FORMULARIO DE ALTA (SIDEBAR) ---
st.sidebar.header(f"Dar de alta en {pestana_seleccionada}")
with st.sidebar.form(f"alta_form_{pestana_seleccionada}", clear_on_submit=True):
    factura = st.text_input("FACTURA", value=st.session_state.val_factura)
    
    if pestana_seleccionada == "Clientes":
        cliente = st.text_input("CLIENTES", value=st.session_state.val_col3)
        descripcion = st.text_input("DESCRIPCION", value=st.session_state.val_descripcion)
        fecha = st.date_input("FECHA", value=st.session_state.val_fecha)
        subtotal = st.number_input("SUBTOTAL", min_value=0.0, value=st.session_state.val_subtotal, format="%.2f")
        
        calc_iva = f"{subtotal * 0.16:.3f}"
        calc_isr = f"{subtotal * 0.0125:.3f}"
        iva_input = st.text_input("IVA (Opcional, 16%)", value=calc_iva)
        isr_input = st.text_input("ISR (Opcional, 1.25%)", value=calc_isr)
    else: 
        col2_label = "RFC"
        col3_label = "PROVEEDOR" if pestana_seleccionada == "Proveedores" else "PROVEEDOR"
        
        c2_input = st.text_input(col2_label, value=st.session_state.val_col2)
        c3_input = st.text_input(col3_label, value=st.session_state.val_col3)
        descripcion = st.text_input("DESCRIPCION", value=st.session_state.val_descripcion)
        fecha = st.date_input("FECHA", value=st.session_state.val_fecha)
        subtotal = st.number_input("SUBTOTAL", min_value=0.0, value=st.session_state.val_subtotal, format="%.2f")
        
        calc_iva = f"{subtotal * 0.16:.3f}"
        iva_input = st.text_input("IVA (Opcional, 16%)", value=calc_iva)

    submitted = st.form_submit_button("Guardar")
    
    if submitted:
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
                    total = subtotal + iva + isr
                    
                    new_row = {
                        "FACTURA": f_upper,
                        "CLIENTES": c3_upper,
                        "DESCRIPCION": desc_upper,
                        "FECHA": str(fecha),
                        "SUBTOTAL": f"{subtotal:.2f}",
                        "IVA": f"{iva:.3f}",
                        "ISR": f"{isr:.3f}",
                        "TOTAL": f"{total:.3f}",
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
                        "IVA": f"{iva:.3f}",
                        "TOTAL": f"{total:.3f}",
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
                    sheet_data.append([r.get(h, "") for h in headers])
                    
                sheet.clear()
                sheet.update("A1", sheet_data)
                
                # Limpiar caché para que refleje los cambios de inmediato
                load_data.clear()
                
                st.success("Guardado y sincronizado correctamente con Google Sheets")
                st.rerun()
        else:
            st.error("Por favor completa todos los campos obligatorios.")

# --- EDITAR O ELIMINAR REGISTROS ---
st.markdown("---")
with st.expander(f"✏️ Editar o Eliminar en {pestana_seleccionada}"):
    if df.empty:
        st.info("No hay registros disponibles para editar.")
    else:
        opciones_registros = ["-- Selecciona un registro --"]
        indices_reales = [None]
        
        for idx, row in df.iterrows():
            fact = str(row.get('FACTURA', '')).strip()
            if fact and not fact.startswith("---") and not fact.startswith("TOTALES"):
                etiqueta_campo = row.get('CLIENTES', row.get('PROVEEDOR', ''))
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
                e_factura = st.text_input("Factura", key="e_fact")
                
                if pestana_seleccionada == "Clientes":
                    e_cliente = st.text_input("Clientes", key="e_c3")
                    e_descripcion = st.text_input("Descripción", key="e_desc")
                    e_fecha = st.text_input("Fecha (YYYY-MM-DD)", key="e_fec")
                    e_subtotal = st.number_input("Subtotal", format="%.2f", key="e_sub")
                    
                    calc_e_iva = e_subtotal * 0.16
                    calc_e_isr = e_subtotal * 0.0125
                    calc_e_tot = e_subtotal + calc_e_iva + calc_e_isr
                    
                    e_iva_input = st.text_input("IVA (16%)", value=f"{calc_e_iva:.3f}")
                    e_isr_input = st.text_input("ISR (1.25%)", value=f"{calc_e_isr:.3f}")
                    st.info(f"Total estimado: ${calc_e_tot:.3f}")
                else:
                    e_rfc = st.text_input("RFC", key="e_c2")
                    e_prov = st.text_input("Proveedor", key="e_c3")
                    e_descripcion = st.text_input("Descripción", key="e_desc")
                    e_fecha = st.text_input("Fecha (YYYY-MM-DD)", key="e_fec")
                    e_subtotal = st.number_input("Subtotal", format="%.2f", key="e_sub")
                    
                    calc_e_iva = e_subtotal * 0.16
                    calc_e_tot = e_subtotal + calc_e_iva
                    
                    e_iva_input = st.text_input("IVA (16%)", value=f"{calc_e_iva:.3f}")
                    st.info(f"Total estimado: ${calc_e_tot:.3f}")

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
                            e_total = e_subtotal + e_iva + e_isr
                            
                            updated_row = {
                                "FACTURA": e_fact_upper,
                                "CLIENTES": e_cliente.strip().upper(),
                                "DESCRIPCION": e_desc_upper,
                                "FECHA": e_fecha.strip(),
                                "SUBTOTAL": f"{e_subtotal:.2f}",
                                "IVA": f"{e_iva:.3f}",
                                "ISR": f"{e_isr:.3f}",
                                "TOTAL": f"{e_total:.3f}",
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
                                "IVA": f"{e_iva:.3f}",
                                "TOTAL": f"{e_total:.3f}",
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
                            sheet_data.append([r.get(h, "") for h in headers])
                            
                        sheet.clear()
                        sheet.update("A1", sheet_data)
                        
                        # Limpiar caché para reflejar los cambios de inmediato
                        load_data.clear()
                        
                        st.session_state.reset_edit = True
                        st.success("¡Actualizado y sincronizado con éxito!")
                        st.rerun()
                    
                if eliminar:
                    sheet.delete_rows(idx_seleccionado)
                    # Limpiar caché para reflejar los cambios de inmediato
                    load_data.clear()
                    st.session_state.reset_edit = True
                    st.success("¡Registro eliminado correctamente!")
                    st.rerun()