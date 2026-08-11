import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# --- CONFIGURACION DE GOOGLE SHEETS ---
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']

creds_dict = dict(st.secrets["gcp_service_account"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

sheet = client.open('Clientes y Proveedores').sheet1

def load_data():
    data = sheet.get_all_values()
    if not data:
        return pd.DataFrame()
    df = pd.DataFrame(data[1:], columns=data[0])
    return df

# Diccionario para convertir números de mes a nombre en español
meses_nombres = {
    1: "E N E R O",
    2: "F E B R E R O",
    3: "M A R Z O",
    4: "A B R I L",
    5: "M A Y O",
    6: "J U N I O",
    7: "J U L I O",
    8: "A G O S T O",
    9: "S E P T I E M B R E",
    10: "O C T U B R E",
    11: "N O V I E M B R E",
    12: "D I C I E M B R E"
}

def procesar_vista_por_meses(df):
    if df.empty:
        return df
    
    # Asegurar que la columna FECHA existe
    if "FECHA" not in df.columns:
        return df
        
    filas_procesadas = []
    mes_actual = None
    
    for _, row in df.iterrows():
        fecha_str = str(row["FECHA"]).strip()
        # Intentar parsear la fecha en diferentes formatos comunes
        dt = None
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"):
            try:
                dt = datetime.strptime(fecha_str.split(" ")[0], fmt)
                break
            except ValueError:
                continue
                
        if dt:
            mes_fila = dt.month
            if mes_fila != mes_actual:
                mes_actual = mes_fila
                nombre_mes = meses_nombres.get(mes_actual, "")
                # Fila divisoria abarcando todo el ancho (la primera columna con el mes, las demás vacías)
                fila_divisoria = {col: "" for col in df.columns}
                fila_divisoria[df.columns[1] if len(df.columns) > 1 else df.columns[0]] = f"--- {nombre_mes} ---"
                filas_procesadas.append(fila_divisoria)
                
        filas_procesadas.append(row.to_dict())
        
    return pd.DataFrame(filas_procesadas)

# --- INTERFAZ STREAMLIT ---
st.set_page_config(layout="wide")
st.title("Inventario de Clientes y Proveedores")

# Cargar datos y aplicar la división visual por meses
df = load_data()
df_visual = procesar_vista_por_meses(df)
st.dataframe(df_visual, use_container_width=True)

# --- FORMULARIO DE ALTA (SIDEBAR) ---
st.sidebar.header("Dar de alta nuevo registro")
with st.sidebar.form("alta_form"):
    factura = st.text_input("FACTURA", key="factura")
    cliente = st.text_input("CLIENTES", key="cliente")
    descripcion = st.text_input("DESCRIPCION", key="descripcion")
    fecha = st.date_input("FECHA")
    subtotal = st.number_input("SUBTOTAL", min_value=0.0, format="%.2f")
    
    submitted = st.form_submit_button("Guardar")
    
    if submitted:
        if factura and cliente and descripcion and fecha and subtotal:
            iva = subtotal * 0.16
            isr = subtotal * 0.0125
            total = subtotal + iva + isr
            
            new_row = [factura, cliente, descripcion, str(fecha), f"{subtotal:.2f}", f"{iva:.2f}", f"{isr:.2f}", f"{total:.2f}", "PENDIENTE"]
            sheet.append_row(new_row)
            st.success("Datos guardados correctamente")
            st.rerun()
        else:
            st.error("Por favor completa todos los campos obligatorios.")

# --- EDITAR O ELIMINAR REGISTROS ---
st.markdown("---")
with st.expander("✏️ Editar o Eliminar Registros"):
    if df.empty or len(df) <= 1:
        st.info("No hay registros suficientes para editar.")
    else:
        opciones_registros = []
        indices_reales = []
        
        for idx, row in df.iterrows():
            if row['FACTURA'] and "---" not in str(row['FACTURA']) and row['FACTURA'] != "ENERO":
                label = f"Fila {idx + 2} - Factura: {row['FACTURA']} | Cliente: {row['CLIENTES']}"
                opciones_registros.append(label)
                indices_reales.append(idx + 2)
                
        if opciones_registros:
            seleccion = st.selectbox("Selecciona el registro a modificar", options=opciones_registros)
            
            if seleccion:
                idx_seleccionado = indices_reales[opciones_registros.index(seleccion)]
                fila_actual = sheet.row_values(idx_seleccionado)
                
                while len(fila_actual) < 9:
                    fila_actual.append("")
                
                with st.form("edit_form"):
                    e_factura = st.text_input("Factura", value=fila_actual[0])
                    e_cliente = st.text_input("Clientes", value=fila_actual[1])
                    e_descripcion = st.text_input("Descripción", value=fila_actual[2])
                    e_fecha = st.text_input("Fecha", value=fila_actual[3])
                    
                    try:
                        sub_val = float(fila_actual[4])
                    except:
                        sub_val = 0.0
                        
                    e_subtotal = st.number_input("Subtotal", value=sub_val, format="%.2f")
                    e_estatus = st.selectbox("Estatus", options=["PENDIENTE", "PAGADA"], index=0 if fila_actual[8] != "PAGADA" else 1)
                    
                    col1, col2 = st.columns(2)
                    actualizar = col1.form_submit_button("Actualizar Registro")
                    eliminar = col2.form_submit_button("Eliminar Registro")
                    
                    if actualizar:
                        e_iva = e_subtotal * 0.16
                        e_isr = e_subtotal * 0.0125
                        e_total = e_subtotal + e_iva + e_isr
                        
                        updated_row = [e_factura, e_cliente, e_descripcion, e_fecha, f"{e_subtotal:.2f}", f"{e_iva:.2f}", f"{e_isr:.2f}", f"{e_total:.2f}", e_estatus]
                        
                        sheet.update(f"A{idx_seleccionado}:I{idx_seleccionado}", [updated_row])
                        st.success("¡Registro actualizado correctamente!")
                        st.rerun()
                        
                    if eliminar:
                        sheet.delete_rows(idx_seleccionado)
                        st.success("¡Registro eliminado correctamente!")
                        st.rerun()
        else:
            st.warning("No se encontraron registros válidos para modificar.")