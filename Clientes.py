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

# Cargar credenciales y limpiar el formato de la clave privada de los secretos de Streamlit
creds_dict = dict(st.secrets["gcp_service_account"])
if "\\n" in creds_dict["private_key"]:
    creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")

creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
client = gspread.authorize(creds)

sheet = client.open('Clientes y Proveedores').sheet1

def load_data():
    data = sheet.get_all_values()
    if not data:
        return pd.DataFrame()
    df = pd.DataFrame(data[1:], columns=data[0])
    return df

# Diccionario para convertir números de mes a nombre en español con formato espaciado
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

def reorganizar_con_meses_en_sheet(df_actual):
    registros = []
    for _, row in df_actual.iterrows():
        fact = str(row.get("FACTURA", "")).strip()
        # Ignorar filas de meses o filas de totales guardadas previamente
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
        t_sub = sum(float(r.get("SUBTOTAL", 0) or 0) for r in regs_mes)
        t_iva = sum(float(r.get("IVA", 0) or 0) for r in regs_mes)
        t_isr = sum(float(r.get("ISR", 0) or 0) for r in regs_mes)
        t_tot = sum(float(r.get("TOTAL", 0) or 0) for r in regs_mes)
        
        fila_tot = {col: "" for col in df_actual.columns}
        # Colocamos las etiquetas en las columnas correspondientes
        if "FACTURA" in df_actual.columns:
            fila_tot["FACTURA"] = "TOTALES DEL MES"
        if "SUBTOTAL" in df_actual.columns:
            fila_tot["SUBTOTAL"] = f"{t_sub:.2f}"
        if "IVA" in df_actual.columns:
            fila_tot["IVA"] = f"{t_iva:.2f}"
        if "ISR" in df_actual.columns:
            fila_tot["ISR"] = f"{t_isr:.2f}"
        if "TOTAL" in df_actual.columns:
            fila_tot["TOTAL"] = f"{t_tot:.2f}"
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
st.title("Inventario de Clientes y Proveedores")

df = load_data()
st.dataframe(df, use_container_width=True)

# --- INICIALIZAR ESTADOS DE LIMPIEZA PARA ALTA ---
if "val_factura" not in st.session_state:
    st.session_state.val_factura = ""
if "val_cliente" not in st.session_state:
    st.session_state.val_cliente = ""
if "val_descripcion" not in st.session_state:
    st.session_state.val_descripcion = ""
if "val_fecha" not in st.session_state:
    st.session_state.val_fecha = datetime.today()
if "val_subtotal" not in st.session_state:
    st.session_state.val_subtotal = 0.0

if "reset_edit" in st.session_state and st.session_state.reset_edit:
    st.session_state.select_edit = "-- Selecciona un registro --"
    st.session_state.reset_edit = False

# --- FORMULARIO DE ALTA (SIDEBAR) ---
st.sidebar.header("Dar de alta nuevo registro")
with st.sidebar.form("alta_form"):
    factura = st.text_input("FACTURA", value=st.session_state.val_factura)
    cliente = st.text_input("CLIENTES", value=st.session_state.val_cliente)
    descripcion = st.text_input("DESCRIPCION", value=st.session_state.val_descripcion)
    fecha = st.date_input("FECHA", value=st.session_state.val_fecha)
    
    subtotal = st.number_input("SUBTOTAL", min_value=0.0, value=st.session_state.val_subtotal, format="%.2f")
    
    calc_iva = f"{subtotal * 0.16:.2f}"
    calc_isr = f"{subtotal * 0.0125:.2f}"
    
    iva_input = st.text_input("IVA (Opcional, por defecto 16%)", value=calc_iva)
    isr_input = st.text_input("ISR (Opcional, por defecto 1.25%)", value=calc_isr)
    
    submitted = st.form_submit_button("Guardar")
    
    if submitted:
        if factura and cliente and descripcion and fecha and subtotal >= 0:
            facturas_existentes = [str(row.get("FACTURA", "")).strip() for _, row in df.iterrows() if str(row.get("FACTURA", "")).strip() and not str(row.get("FACTURA", "")).startswith("---") and not str(row.get("FACTURA", "")).startswith("TOTALES")]
            if factura.strip() in facturas_existentes:
                st.error(f"¡Error! El número de factura '{factura}' ya existe en la base de datos para otro cliente.")
            else:
                try:
                    iva = float(iva_input) if iva_input.strip() != "" else subtotal * 0.16
                except ValueError:
                    iva = 0.0

                try:
                    isr = float(isr_input) if isr_input.strip() != "" else subtotal * 0.0125
                except ValueError:
                    isr = 0.0

                total = subtotal + iva + isr
                
                new_row = {
                    "FACTURA": factura.strip(),
                    "CLIENTES": cliente.strip(),
                    "DESCRIPCION": descripcion.strip(),
                    "FECHA": str(fecha),
                    "SUBTOTAL": f"{subtotal:.2f}",
                    "IVA": f"{iva:.2f}",
                    "ISR": f"{isr:.2f}",
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
                reorganized = reorganizar_con_meses_en_sheet(temp_df)
                
                headers = list(df.columns) if not df.empty else list(new_row.keys())
                sheet_data = [headers]
                for r in reorganized:
                    sheet_data.append([r.get(h, "") for h in headers])
                    
                sheet.clear()
                sheet.update("A1", sheet_data)
                
                st.session_state.val_factura = ""
                st.session_state.val_cliente = ""
                st.session_state.val_descripcion = ""
                st.session_state.val_fecha = datetime.today()
                st.session_state.val_subtotal = 0.0
                
                st.success("Datos guardados y organizados por mes correctamente")
                st.rerun()
        else:
            st.error("Por favor completa todos los campos obligatorios.")

# --- EDITAR O ELIMINAR REGISTROS ---
st.markdown("---")
with st.expander("✏️ Editar o Eliminar Registros"):
    if df.empty:
        st.info("No hay registros suficientes para editar.")
    else:
        opciones_registros = ["-- Selecciona un registro --"]
        indices_reales = [None]
        
        for idx, row in df.iterrows():
            fact = str(row.get('FACTURA', '')).strip()
            # Filtrar filas vacías, de meses o de totales
            if fact and not fact.startswith("---") and not fact.startswith("TOTALES"):
                label = f"Factura: {fact} | Cliente: {row.get('CLIENTES', '')}"
                opciones_registros.append(label)
                indices_reales.append(idx + 2)
                
        if "select_edit" not in st.session_state:
            st.session_state.select_edit = "-- Selecciona un registro --"

        seleccion = st.selectbox("Selecciona el registro a modificar", options=opciones_registros, key="select_edit")
        
        if seleccion == "-- Selecciona un registro --":
            st.info("👆 Por favor, selecciona una factura del menú desplegable para habilitar la edición.")
        else:
            idx_seleccionado = indices_reales[opciones_registros.index(seleccion)]
            fila_df = df.iloc[idx_seleccionado - 2]
            
            if "last_edit_selection" not in st.session_state or st.session_state.last_edit_selection != seleccion:
                st.session_state.last_edit_selection = seleccion
                st.session_state.e_fact = str(fila_df.get("FACTURA", ""))
                st.session_state.e_cli = str(fila_df.get("CLIENTES", ""))
                st.session_state.e_desc = str(fila_df.get("DESCRIPCION", ""))
                st.session_state.e_fec = str(fila_df.get("FECHA", ""))
                try:
                    st.session_state.e_sub = float(fila_df.get("SUBTOTAL", 0))
                except ValueError:
                    st.session_state.e_sub = 0.0
                st.session_state.e_est_idx = 0 if str(fila_df.get("ESTATUS", "PENDIENTE")) != "PAGADA" else 1

            with st.form("form_editar_factura"):
                e_factura = st.text_input("Factura", key="e_fact")
                e_cliente = st.text_input("Clientes", key="e_cli")
                e_descripcion = st.text_input("Descripción", key="e_desc")
                e_fecha = st.text_input("Fecha (YYYY-MM-DD)", key="e_fec")
                
                # Al cambiar el subtotal aquí dentro, Streamlit reactivará el cálculo automático
                e_subtotal = st.number_input("Subtotal", format="%.2f", key="e_sub")
                
                # Operaciones automáticas en tiempo real al modificar el subtotal
                calc_e_iva = e_subtotal * 0.16
                calc_e_isr = e_subtotal * 0.0125
                calc_e_total = e_subtotal + calc_e_iva + calc_e_isr
                
                # Mostramos los valores calculados dinámicamente como texto informativo o inputs editables
                e_iva_input = st.text_input("IVA (16% automático)", value=f"{calc_e_iva:.2f}")
                e_isr_input = st.text_input("ISR (1.25% automático)", value=f"{calc_e_isr:.2f}")
                
                st.info(f"Total estimado: ${calc_e_total:.2f}")

                e_estatus = st.selectbox("Estatus", options=["PENDIENTE", "PAGADA"], index=st.session_state.get("e_est_idx", 0), key="e_est")
                
                col1, col2 = st.columns(2)
                actualizar = col1.form_submit_button("Actualizar Registro")
                eliminar = col2.form_submit_button("Eliminar Registro")
                
                if actualizar:
                    facturas_existentes = []
                    for i, r in df.iterrows():
                        if (i + 2) != idx_seleccionado:
                            f_val = str(r.get("FACTURA", "")).strip()
                            if f_val and not f_val.startswith("---") and not f_val.startswith("TOTALES"):
                                facturas_existentes.append(f_val)
                                
                    if e_factura.strip() in facturas_existentes:
                        st.error(f"¡Error! El número de factura '{e_factura}' ya pertenece a otro registro.")
                    else:
                        try:
                            e_iva = float(e_iva_input) if e_iva_input.strip() != "" else e_subtotal * 0.16
                        except ValueError:
                            e_iva = 0.0

                        try:
                            e_isr = float(e_isr_input) if e_isr_input.strip() != "" else e_subtotal * 0.0125
                        except ValueError:
                            e_isr = 0.0

                        e_total = e_subtotal + e_iva + e_isr
                        
                        updated_row = {
                            "FACTURA": e_factura.strip(),
                            "CLIENTES": e_cliente.strip(),
                            "DESCRIPCION": e_descripcion.strip(),
                            "FECHA": e_fecha.strip(),
                            "SUBTOTAL": f"{e_subtotal:.2f}",
                            "IVA": f"{e_iva:.2f}",
                            "ISR": f"{e_isr:.2f}",
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
                        reorganized = reorganizar_con_meses_en_sheet(temp_df)
                        
                        headers = list(df.columns)
                        sheet_data = [headers]
                        for r in reorganized:
                            sheet_data.append([r.get(h, "") for h in headers])
                            
                        sheet.clear()
                        sheet.update("A1", sheet_data)
                        
                        st.session_state.reset_edit = True
                        st.success("¡Registro actualizado correctamente con sus cálculos y totales!")
                        st.rerun()
                    
                if eliminar:
                    sheet.delete_rows(idx_seleccionado)
                    st.session_state.reset_edit = True
                    st.success("¡Registro eliminado correctamente!")
                    st.rerun()